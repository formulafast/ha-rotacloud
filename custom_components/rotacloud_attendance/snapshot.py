"""Pure attendance/status logic. No HA or network dependency."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from .model import Attendance
from .roster import Shift

@dataclass(frozen=True, slots=True)
class Staff:
    user_id: int
    name: str
    status: str
    shifts: tuple[Shift, ...]
    attendance: Attendance | None
    scheduled: Shift | None
    completed_break_seconds: int
    active_break_start: int | None
    clock_in_delta_seconds: int | None
    clock_out_delta_seconds: int | None

def day_bounds(now: datetime, tz: ZoneInfo):
    day = now.astimezone(tz).date()
    return tuple(int(datetime.combine(day + timedelta(days=i), time.min, tzinfo=tz).timestamp()) for i in (-1,0,1))

def snapshot(employees, shifts, active, completed, now, today, tomorrow, late=0, leaving=15):
    """All scheduled or actually present today; include overnight overlap."""
    by_shift = {s.id:s for s in shifts}
    today_shifts = [s for s in shifts if s.start < tomorrow and s.end > today]
    history = [a for a in completed if a.clock_out is not None and a.clock_out >= today and a.clock_in < tomorrow]
    live = {a.user_id:a for a in active}
    # A completed response may race the live response; prefer the newer completed record for the same clock-in.
    for a in history:
        current = live.get(a.user_id)
        if current and current.clock_in == a.clock_in and a.clock_out > current.clock_in:
            live.pop(a.user_id)
    result = {}
    ids = set(live) | {s.user for s in today_shifts} | {a.user_id for a in history}
    for uid in sorted(ids):
        person = employees.get(uid)
        name = (" ".join((person.first_name, person.last_name)).strip() if person else "") or f"Employee {uid}"
        roster = tuple(sorted((s for s in today_shifts if s.user == uid), key=lambda s:(s.start,s.id)))
        past = sorted((a for a in history if a.user_id == uid), key=lambda a:(a.clock_in,a.clock_out))
        current = live.get(uid)
        latest = current or (past[-1] if past else None)
        linked = {a.shift_id for a in past if a.shift_id is not None}
        pending = [s for s in roster if s.id not in linked and s.end > now]
        scheduled = by_shift.get(latest.shift_id) if latest and latest.shift_id is not None else None
        if scheduled and scheduled.user != uid:
            scheduled = None
        if current:
            status = "break" if current.active_break else "leaving" if scheduled and now >= scheduled.end - leaving*60 else "here"
        elif pending:
            status = "late" if now > pending[0].start + late*60 else "due"
        elif past:
            status = "gone"
        elif roster:
            # No attendance and shift already ended: still late/missed, never pretend they were present.
            status = "late"
        else:
            continue
        if not current and pending:
            scheduled = pending[0]
        associated = latest and scheduled and latest.shift_id == scheduled.id
        completed_seconds = sum(b.seconds(now) for a in past + ([current] if current else [])
                                for b in a.breaks if b.end is not None)
        active_start = current.active_break.start if current and current.active_break else None
        result[uid] = Staff(uid,name,status,roster,latest,scheduled,completed_seconds,active_start,
                            latest.clock_in - scheduled.start if associated else None,
                            latest.clock_out - scheduled.end if associated and latest.clock_out is not None else None)
    return result
