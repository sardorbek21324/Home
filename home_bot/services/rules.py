from ..db.models import Task, TaskInstance, InstanceState, User
from ..db.repo import save_history
from sqlalchemy.orm import Session

def compute_reward(task: Task, defer_count: int, repeats_penalty_steps: int = 0) -> int:
    base = task.base_points
    if defer_count == 1:
        base = int(round(base * 0.7))
    elif defer_count >= 2:
        base = int(round(base * 0.5))
    base = max(base - repeats_penalty_steps, int(round(task.base_points * 0.6)))
    base = max(task.min_points, min(task.max_points, base))
    return base

def penalty_no_one_took(session: Session, users: list[User], instance_id: int):
    for u in users:
        save_history(session, u.id, instance_id, -2, "NO_ONE_TOOK")

def penalty_not_done_now(session: Session, user: User, instance_id: int, penalty_multiplier: int = 0):
    save_history(session, user.id, instance_id, -3 - penalty_multiplier, "NOT_DONE_NOW")

def penalty_not_done_deferred(session: Session, user: User, instance_id: int, penalty_multiplier: int = 0):
    save_history(session, user.id, instance_id, -6 - penalty_multiplier, "NOT_DONE_DEFERRED")

def penalty_dispute_abuse(session: Session, user: User, instance_id: int):
    save_history(session, user.id, instance_id, -1, "DISPUTE_PENALTY")

def penalty_late_cancel(session: Session, user: User, instance_id: int):
    save_history(session, user.id, instance_id, -2, "LATE_CANCEL")

def penalty_autoconfirm_idle(session: Session, user: User, instance_id: int):
    save_history(session, user.id, instance_id, -1, "AUTOCONFIRM_IDLE")

def reward_done(session: Session, user: User, instance_id: int, points: int):
    save_history(session, user.id, instance_id, points, "DONE")
