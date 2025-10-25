from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

def parse_quiet_hours(s: str):
    a, b = s.split("-")
    h1, m1 = map(int, a.split(":"))
    h2, m2 = map(int, b.split(":"))
    return time(h1, m1), time(h2, m2)

def in_quiet_hours(now: datetime, quiet: tuple[time, time]) -> bool:
    start, end = quiet
    t = now.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end

def now_tz(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def next_allowed_moment(now: datetime, quiet: tuple[time, time]) -> datetime:
    """Return the next moment outside of quiet hours."""

    start, end = quiet
    if start == end:
        return now

    tzinfo = now.tzinfo
    if tzinfo is None:
        raise ValueError("Datetime must be timezone-aware for quiet hours calculations")

    today = now.date()
    start_dt = datetime.combine(today, start, tzinfo=tzinfo)
    end_dt = datetime.combine(today, end, tzinfo=tzinfo)

    if start <= end:
        if start_dt <= now < end_dt:
            return end_dt
        return now

    # Quiet hours wrap across midnight
    if now >= start_dt:
        return datetime.combine(today + timedelta(days=1), end, tzinfo=tzinfo)
    if now < end_dt:
        return end_dt
    return now
