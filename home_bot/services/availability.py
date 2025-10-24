from ..db.models import User, Status
from datetime import datetime

def is_available(u: User, now: datetime) -> bool:
    if u.status == Status.available:
        return True
    if u.status == Status.busy_until and u.busy_until and now >= u.busy_until:
        return True
    return False

def eligible_recipients(all_users: list[User], exclude_user_id: int | None, now: datetime) -> list[User]:
    result = []
    for u in all_users:
        if exclude_user_id is not None and u.id == exclude_user_id:
            continue
        if u.status.name in ("day_off", "vacation"):
            continue
        if is_available(u, now):
            result.append(u)
    return result
