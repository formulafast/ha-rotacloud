"""Read-only roster adapter. Only retain names, IDs and scheduling data."""
from dataclasses import dataclass
from .api import ApiError, Client, Employee
from .model import Attendance

@dataclass(frozen=True, slots=True)
class Shift:
    id: int
    user: int
    start: int
    end: int

class RosterClient:
    def __init__(self, client: Client):
        self.client = client

    async def _list(self, path, params=None):
        rows = []
        offset = 0
        while True:
            page, headers = await self.client._request("GET", path, params={**(params or {}), "limit": 100, "offset": offset})
            if not isinstance(page, list) or any(not isinstance(r, dict) for r in page):
                raise ApiError(None)
            rows.extend(page)
            offset += len(page)
            total = next((v for k,v in headers.items() if k.lower() == "x-total-count"), None)
            if total is None or offset >= int(total):
                return rows
            if not page:
                raise ApiError(None)

    async def employees(self):
        rows = await self._list("/users", {"include_deleted": "false"})
        return {r["id"]: Employee(r["id"], str(r.get("first_name") or ""), str(r.get("last_name") or ""))
                for r in rows if not r.get("deleted") and type(r.get("id")) is int}

    async def shifts(self, start, end):
        rows = await self._list("/shifts", {"start":start,"end":end,"published":"true","include_deleted":"false"})
        return tuple(Shift(r["id"],r["user"],r["start_time"],r["end_time"]) for r in rows
                     if not r.get("deleted") and not r.get("open") and r.get("published") is not False
                     and all(type(r.get(k)) is int for k in ("id","user","start_time","end_time")) and r["user"]>0)

    async def completed(self, start, end):
        rows = await self._list("/attendance", {"start":start,"end":end,"include_deleted":"false"})
        return tuple(Attendance.from_record(r) for r in rows if not r.get("deleted") and r.get("out_time") is not None)
