"""Minimal attendance model; never retain raw personal information."""
from dataclasses import dataclass
from typing import Mapping, Any


def _timestamp(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _actual(record: Mapping[str, Any], key: str) -> int | None:
    value = _timestamp(record.get(key + '_clocked'))
    return value if value is not None else _timestamp(record.get(key))


@dataclass(frozen=True, slots=True)
class Break:
    start: int
    end: int | None

    def seconds(self, now: int) -> int:
        return max(0, (now if self.end is None else self.end) - self.start)


@dataclass(frozen=True, slots=True)
class Attendance:
    user_id: int
    clock_in: int
    clock_out: int | None
    breaks: tuple[Break, ...]
    shift_id: int | None = None
    scheduled_end: int | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> 'Attendance':
        start = _actual(record, 'in_time')
        end = _actual(record, 'out_time')
        if start is None or type(record.get('user')) is not int:
            raise ValueError('Missing attendance identity or clock-in time')
        breaks = []
        for item in record.get('breaks_clocked') or []:
            b_start = _timestamp(item.get('start_time'))
            if b_start is not None:
                b_end = _timestamp(item.get('end_time'))
                # Completed records must never show a running break.
                breaks.append(Break(b_start, end if b_end is None and end is not None else b_end))
        shift = record.get('shift')
        return cls(record['user'], start, end, tuple(breaks),
                   _timestamp(shift.get('id') if isinstance(shift, dict) else shift),
                   _timestamp(shift.get('end_time')) if isinstance(shift, dict) else None)

    @property
    def active_break(self) -> Break | None:
        return next((b for b in reversed(self.breaks) if b.end is None), None) if self.clock_out is None else None

    @property
    def state(self) -> str:
        return 'gone' if self.clock_out is not None else 'break' if self.active_break else 'here'

    @property
    def allowed_actions(self) -> tuple[str, ...]:
        return {'gone': ('clock_in',), 'here': ('start_break', 'clock_out'),
                'break': ('end_break', 'clock_out')}[self.state]

    def shift_seconds(self, now: int) -> int:
        """Gross elapsed clock duration, independent of all breaks."""
        return max(0, (now if self.clock_out is None else self.clock_out) - self.clock_in)

    def break_seconds(self, now: int) -> int:
        return sum(b.seconds(now if self.clock_out is None else self.clock_out) for b in self.breaks)
