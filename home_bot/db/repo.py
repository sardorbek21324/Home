"""Repository helpers on top of SQLAlchemy sessions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Iterator, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from . import Base, SessionLocal, engine
from .models import (
    Dispute,
    DisputeState,
    Report,
    ScoreEvent,
    TaskFrequency,
    TaskInstance,
    TaskKind,
    TaskStatus,
    TaskTemplate,
    User,
    Vote,
    VoteValue,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_user(session: Session, tg_id: int, name: str, username: str | None) -> User:
    user = session.scalar(select(User).where(User.tg_id == tg_id))
    if user:
        user.name = name
        user.username = username
        return user

    user = User(tg_id=tg_id, name=name, username=username)
    session.add(user)
    session.flush()
    return user


def list_users(session: Session) -> Sequence[User]:
    return session.scalars(select(User).order_by(User.id)).all()


def get_user_by_tg(session: Session, tg_id: int) -> User | None:
    return session.scalar(select(User).where(User.tg_id == tg_id))


def add_score_event(session: Session, user: User, delta: int, reason: str, *, task_instance: TaskInstance | None = None) -> None:
    event = ScoreEvent(user=user, delta=delta, reason=reason, task_instance=task_instance)
    user.score += delta
    session.add(event)
    session.flush()


def reset_month(session: Session, season_label: str) -> User | None:
    users = session.scalars(select(User)).all()
    if not users:
        return None
    winner = max(users, key=lambda u: u.score)
    for user in users:
        if user.score:
            session.add(
                ScoreEvent(
                    user=user,
                    delta=-user.score,
                    reason=f"Season {season_label}: reset",
                    season=season_label,
                )
            )
            user.score = 0
    return winner


def seed_templates(session: Session, payload: Iterable[dict[str, object]]) -> None:
    existing_codes = {code for (code,) in session.execute(select(TaskTemplate.code))}
    for entry in payload:
        code = str(entry["code"])
        if code in existing_codes:
            continue
        template = TaskTemplate(
            code=code,
            title=str(entry["title"]),
            base_points=int(entry["base_points"]),
            frequency=TaskFrequency(str(entry["frequency"])),
            max_per_day=int(entry["max_per_day"]) if entry.get("max_per_day") else None,
            sla_minutes=int(entry["sla_minutes"]),
            claim_timeout_minutes=int(entry["claim_timeout_minutes"]),
            kind=TaskKind(str(entry["kind"])),
            nobody_claimed_penalty=int(entry.get("nobody_claimed_penalty", 0)),
            deferral_penalty_pct=int(entry.get("deferral_penalty_pct", 20)),
        )
        session.add(template)


def create_instance(
    session: Session,
    template: TaskTemplate,
    *,
    day: date,
    slot: int,
    status: TaskStatus = TaskStatus.open,
) -> TaskInstance:
    now = datetime.now(timezone.utc)
    next_check_at = None
    if template.claim_timeout_minutes:
        next_check_at = now + timedelta(minutes=template.claim_timeout_minutes)
    instance = TaskInstance(
        template=template,
        day=day,
        slot=slot,
        status=status,
        created_at=now,
        round_no=0,
        next_check_at=next_check_at,
    )
    session.add(instance)
    session.flush()
    return instance


def upcoming_instances(session: Session, *, from_dt: datetime) -> Sequence[TaskInstance]:
    return session.scalars(
        select(TaskInstance)
        .where(TaskInstance.created_at >= from_dt)
        .order_by(TaskInstance.created_at)
    ).all()


def find_open_instances(session: Session) -> Sequence[TaskInstance]:
    return session.scalars(
        select(TaskInstance)
        .where(TaskInstance.status.in_([TaskStatus.open, TaskStatus.reserved]))
        .order_by(TaskInstance.created_at)
    ).all()


def reserve_instance(
    session: Session,
    instance: TaskInstance,
    user: User,
    *,
    defer: bool,
    defer_minutes: int,
    explicit_deferrals: int | None = None,
) -> datetime:
    now = datetime.utcnow()
    instance.status = TaskStatus.reserved
    instance.assigned_to = user.id
    if explicit_deferrals is not None:
        instance.deferrals_used = min(max(explicit_deferrals, 0), 2)
    elif defer:
        instance.deferrals_used = min(instance.deferrals_used + 1, 2)
    else:
        instance.deferrals_used = 0
    extra_minutes = defer_minutes if defer else 0
    deadline_minutes = instance.template.sla_minutes + extra_minutes
    instance.reserved_until = now + timedelta(minutes=deadline_minutes)
    instance.attempts += 1
    session.flush()
    return instance.reserved_until


def submit_report(session: Session, instance: TaskInstance, user: User, file_id: str) -> Report:
    report = Report(task_instance=instance, user=user, photo_file_id=file_id)
    instance.status = TaskStatus.report_submitted
    session.add(report)
    session.flush()
    return report


def register_vote(session: Session, instance: TaskInstance, voter: User, value: VoteValue) -> Vote:
    vote = Vote(task_instance=instance, voter=voter, value=value)
    session.add(vote)
    session.flush()
    return vote


def votes_summary(session: Session, instance: TaskInstance) -> tuple[int, int]:
    counts = session.execute(
        select(Vote.value, func.count()).where(Vote.task_instance_id == instance.id).group_by(Vote.value)
    ).all()
    yes = next((count for value, count in counts if value == VoteValue.yes), 0)
    no = next((count for value, count in counts if value == VoteValue.no), 0)
    return yes, no


def open_dispute(session: Session, instance: TaskInstance, opened_by: User, note: str | None = None) -> Dispute:
    dispute = Dispute(task_instance=instance, opened_by=opened_by.id, note=note)
    instance.status = TaskStatus.rejected
    session.add(dispute)
    session.flush()
    return dispute


def resolve_dispute(session: Session, dispute: Dispute, resolved_by: User, note: str, *, approve: bool) -> None:
    dispute.state = DisputeState.resolved
    dispute.resolved_by = resolved_by.id
    dispute.resolved_at = datetime.utcnow()
    dispute.note = note
    instance = dispute.task_instance
    instance.status = TaskStatus.approved if approve else TaskStatus.rejected
    session.flush()


def pending_vote_instances(session: Session) -> Sequence[TaskInstance]:
    return session.scalars(
        select(TaskInstance)
        .where(TaskInstance.status == TaskStatus.report_submitted)
        .order_by(TaskInstance.created_at)
    ).all()


def available_templates(session: Session, *, kind: TaskKind | None = None) -> Sequence[TaskTemplate]:
    stmt = select(TaskTemplate).order_by(TaskTemplate.title)
    if kind:
        stmt = stmt.where(TaskTemplate.kind == kind)
    return session.scalars(stmt).all()


def todays_history(session: Session, user: User) -> Sequence[ScoreEvent]:
    today = datetime.utcnow().date()
    return session.scalars(
        select(ScoreEvent)
        .where(
            and_(
                ScoreEvent.user_id == user.id,
                func.date(ScoreEvent.created_at) == today,
            )
        )
        .order_by(ScoreEvent.created_at.desc())
    ).all()


def list_open_disputes(session: Session) -> Sequence[Dispute]:
    return session.scalars(
        select(Dispute)
        .where(Dispute.state == DisputeState.open)
        .order_by(Dispute.created_at.asc())
    ).all()


def get_dispute(session: Session, dispute_id: int) -> Dispute | None:
    return session.get(Dispute, dispute_id)
