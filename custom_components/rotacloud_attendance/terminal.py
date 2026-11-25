"""Offline-testable terminal logic. The transport must authenticate callers."""
import asyncio
from collections import deque
from dataclasses import dataclass, replace
import secrets
import time
from .api import ApiError, Employee
from .model import Attendance

class TerminalError(Exception):
    pass

@dataclass(frozen=True, slots=True)
class Session:
    device: str
    employee: Employee
    active: Attendance | None
    shift_ids: tuple[int, ...]
    expires: float

def describe(active, now):
    if active is None:
        return {"state":"out","actions":["clock_in"]}
    return {"state":active.state,"actions":list(active.allowed_actions),
            "clock_in":active.clock_in,"clock_out":active.clock_out,
            "scheduled_end":active.scheduled_end,
            "active_break_start":active.active_break.start if active.active_break else None,
            "shift_seconds":active.shift_seconds(now),"break_seconds":active.break_seconds(now)}

class Terminal:
    def __init__(self, client, eligible, shifts_for, on_change, *, monotonic=time.monotonic, wall=time.time,
                 scheduled_end_for=lambda active: active.scheduled_end):
        self.client = client
        self.eligible, self.shifts_for, self.on_change = eligible, shifts_for, on_change
        self.monotonic, self.wall = monotonic, wall
        self.scheduled_end_for = scheduled_end_for
        self.sessions = {}
        self.attempts = deque()
        self.lock = asyncio.Lock()

    async def _active(self, uid):
        try:
            rows = await self.client.clocked_in()
        except (ApiError, ValueError, TypeError, AttributeError):
            raise TerminalError("Clocking unavailable. Use the RotaCloud terminal.") from None
        matches = [a for a in rows if a.user_id == uid]
        if len(matches) > 1 or any(a.clock_out is not None for a in matches):
            raise TerminalError("Attendance needs reconciliation. Use the RotaCloud terminal.")
        return replace(matches[0], scheduled_end=self.scheduled_end_for(matches[0])) if matches else None

    async def identify(self, device, pin):
        async with self.lock:
            now = self.monotonic()
            self.sessions = {k:v for k,v in self.sessions.items() if v.expires>now and v.device!=device}
            while self.attempts and self.attempts[0] <= now-60:
                self.attempts.popleft()
            if len(self.attempts)>=8:
                raise TerminalError("Too many attempts. Use the RotaCloud terminal if needed.")
            self.attempts.append(now)
            try:
                person = await self.client.identify(pin)
            except (ApiError,ValueError) as exc:
                if isinstance(exc,ApiError) and exc.status not in (400,403,404):
                    raise TerminalError("Clocking unavailable. Use the RotaCloud terminal.") from None
                raise TerminalError("PIN not recognised or not authorised.") from None
            finally:
                pin = None
            if not self.eligible(device,person.id):
                raise TerminalError("PIN not recognised or not authorised.")
            active = await self._active(person.id)
            shifts = tuple(self.shifts_for(device,person.id,int(self.wall()))) if active is None else ()
            token = secrets.token_urlsafe(32)
            self.sessions[token] = Session(device,person,active,tuple(s.id for s in shifts),self.monotonic()+20)
            return {"session":token,"name":person.first_name,**describe(active,int(self.wall())),
                    "shifts":[{"id":s.id,"start":s.start,"end":s.end} for s in shifts]}

    async def act(self,device,token,action,shift_id=None):
        async with self.lock:
            session = self.sessions.get(token)
            if not session or session.device!=device or session.expires<=self.monotonic():
                raise TerminalError("Session expired. Enter your PIN again.")
            self.sessions.pop(token)
            uid = session.employee.id
            if not self.eligible(device,uid):
                raise TerminalError("Not authorised.")
            # One read before writing protects against an action taken in RotaCloud since PIN entry.
            current = await self._active(uid)
            if not self.eligible(device,uid):
                raise TerminalError("Not authorised.")
            if current != session.active:
                raise TerminalError("Attendance changed. Enter your PIN again.")
            allowed = ("clock_in",) if current is None else current.allowed_actions
            if action not in allowed:
                raise TerminalError("Action not available.")
            if action=="clock_in":
                fresh = tuple(self.shifts_for(device,uid,int(self.wall())))
                ids = tuple(s.id for s in fresh)
                if ids != session.shift_ids or (ids and shift_id not in ids) or (not ids and shift_id is not None):
                    raise TerminalError("Shift selection changed or is required. Enter your PIN again.")
            elif shift_id is not None:
                raise TerminalError("Unexpected shift selection.")
            try:
                if action=="clock_in":
                    result = await self.client.clock_in(uid,shift_id)
                    if result.user_id != uid or result.clock_out is not None:
                        raise ApiError(None, uncertain=True)
                    if shift_id is not None:
                        selected = next(s for s in fresh if s.id == shift_id)
                        result = replace(result, scheduled_end=selected.end)
                elif action=="clock_out":
                    result = await self.client.clock_out(uid)
                    if result.user_id != uid or result.clock_out is None or result.clock_out < result.clock_in:
                        raise ApiError(None, uncertain=True)
                    # Initial API response can omit breaks. Preserve known breaks for provisional display.
                    if current.breaks and not result.breaks:
                        result = replace(result,breaks=tuple(replace(b,end=result.clock_out) if b.end is None else b for b in current.breaks))
                else:
                    b = await self.client.set_break(uid,action)
                    if action == "start_break" and (b.end is not None or b.start < current.clock_in):
                        raise ApiError(None, uncertain=True)
                    if action == "end_break" and (current.active_break is None or b.start != current.active_break.start or b.end is None or b.end < b.start):
                        raise ApiError(None, uncertain=True)
                    breaks = current.breaks + (b,) if action=="start_break" else tuple(b if x.end is None and x.start==b.start else x for x in current.breaks)
                    result = replace(current,breaks=breaks)
            except ApiError as exc:
                if exc.uncertain:
                    try:
                        await self.on_change(uid,None)
                    except Exception:
                        pass
                    raise TerminalError("Outcome unknown. Check RotaCloud before trying again.") from None
                raise TerminalError("Clocking failed. Use the RotaCloud terminal.") from None
            # Update local state from confirmed response, not an additional full read.
            # The callback must reconcile provisional clock-out data asynchronously and never
            # convert an already confirmed mutation into a retryable UI error.
            try:
                await self.on_change(uid,result)
            except Exception:
                # Attendance has already been written: never invite a duplicate write.
                pass
            response = {"action":action,**describe(result,int(self.wall()))}
            if action in ("start_break","end_break"):
                response["last_break_seconds"] = b.seconds(int(self.wall()))
                response["last_break_start"] = b.start
            if action=="clock_out":
                response["provisional_break_total"] = True
            return response
