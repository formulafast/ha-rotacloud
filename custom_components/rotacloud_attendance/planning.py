"""Small, privacy-minimised planning projections. No network or HA dependency."""
from dataclasses import dataclass
from datetime import date, time


def age_band(dob, today):
    try:
        born = date.fromisoformat(dob)
    except (ValueError, TypeError):
        return None
    if born > today:
        return None
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return "under18" if years < 18 else "adult"


def break_warning(attendance, band, options, now):
    if attendance is None or band not in ("under18", "adult"):
        return False
    key = "break_" + band + "_"
    minimum = options.get(key + "minimum_minutes", 0) * 60
    qualifying = (options.get(key + "qualifying_hours", 0) * 60 + options.get(key + "qualifying_minutes", 0)) * 60
    after = (options.get(key + "warning_hours", 0) * 60 + options.get(key + "warning_minutes", 0)) * 60
    elapsed = attendance.shift_seconds(now)
    breaks = attendance.break_seconds(now)
    # Eligibility is actual work in this clocking, excluding its recorded breaks.
    return minimum > 0 and max(0, elapsed - breaks) >= qualifying and elapsed >= after and breaks < minimum


def break_seconds_today(records, today, tomorrow, now):
    return sum(max(0, min(b.end if b.end is not None else now, tomorrow) - max(b.start, today))
               for a in records for b in a.breaks)


@dataclass(frozen=True, slots=True)
class Window:
    user: int
    kind: str
    label: str


def _time_label(start, end):
    if start == "00:00" and end in ("00:00", "24:00"):
        return "All Day"
    try:
        time.fromisoformat(start)
        time.fromisoformat("00:00" if end == "24:00" else end)
    except (ValueError, TypeError):
        return None
    return start[:5] + " – " + end[:5] + (" (+1 day)" if end < start else "")


def availability_windows(rows, day):
    result = []
    for row in rows:
        uid = row.get("user")
        if type(uid) is not int:
            continue
        for item in row.get("dates") or []:
            if item.get("date") != day:
                continue
            for span in item.get("available") or []:
                label = _time_label(span.get("start_time"), span.get("end_time"))
                if label:
                    result.append(Window(uid, "available", label))
    return tuple(dict.fromkeys(result))


def leave_windows(rows, day):
    result = []
    for row in rows:
        uid = row.get("user")
        if type(uid) is not int or row.get("deleted") or row.get("status") != "approved":
            continue
        for item in row.get("dates") or []:
            if item.get("date") != day:
                continue
            start = item.get("start_time", row.get("start_time"))
            end = item.get("end_time", row.get("end_time"))
            label = _time_label(start, end) if isinstance(start, str) and isinstance(end, str) else None
            if label is None:
                first = row.get("start_am_pm") if day == row.get("start_date") else "am"
                last = row.get("end_am_pm") if day == row.get("end_date") else "pm"
                days = item.get("days")
                if days == 1 or (days is None and first == "am" and last == "pm"):
                    label = "All Day"
                elif first == last and first in ("am", "pm"):
                    label = first.upper() + " · exact times not provided"
                else:
                    label = "Part Day · exact times not provided"
            result.append(Window(uid, "on_leave", label))
    return tuple(dict.fromkeys(result))
