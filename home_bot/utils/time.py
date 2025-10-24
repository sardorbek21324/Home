from datetime import time, datetime
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
