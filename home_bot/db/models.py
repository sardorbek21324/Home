"""SQLAlchemy models for the bot domain."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class TaskFrequency(str, PyEnum):
    daily = "daily"
    weekly = "weekly"
    every_2days = "every_2days"
    custom = "custom"


class TaskKind(str, PyEnum):
    house = "house"
    mini = "mini"
    outside = "outside"


class TaskStatus(str, PyEnum):
    open = "open"
    reserved = "reserved"
    report_submitted = "report_submitted"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    missed = "missed"


class VoteValue(str, PyEnum):
    yes = "yes"
    no = "no"


class DisputeState(str, PyEnum):
    open = "open"
    resolved = "resolved"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    username: Mapped[Optional[str]] = mapped_column(String(64))
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    score: Mapped[int] = mapped_column(Integer, default=0)

    reports: Mapped[list["Report"]] = relationship(back_populates="user")
    events: Mapped[list["ScoreEvent"]] = relationship(back_populates="user")


class FamilyMember(Base):
    __tablename__ = "family_members"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    base_points: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[TaskFrequency] = mapped_column(Enum(TaskFrequency))
    max_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_minutes: Mapped[int] = mapped_column(Integer)
    claim_timeout_minutes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[TaskKind] = mapped_column(Enum(TaskKind))
    nobody_claimed_penalty: Mapped[int] = mapped_column(Integer, default=0)
    deferral_penalty_pct: Mapped[int] = mapped_column(Integer, default=20)

    instances: Mapped[list["TaskInstance"]] = relationship(back_populates="template")


class TaskInstance(Base):
    __tablename__ = "task_instances"
    __table_args__ = (
        UniqueConstraint("template_id", "day", name="uq_instance_template_day"),
        UniqueConstraint("template_id", "day", "slot", name="uq_instance_template_day_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("task_templates.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.open, index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    deferrals_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_announce_at: Mapped[datetime | None] = mapped_column(DateTime)
    round_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    template: Mapped[TaskTemplate] = relationship(back_populates="instances")
    report: Mapped[Optional["Report"]] = relationship(back_populates="task_instance", uselist=False)
    votes: Mapped[list["Vote"]] = relationship(back_populates="task_instance")
    dispute: Mapped[Optional["Dispute"]] = relationship(back_populates="task_instance", uselist=False)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_instance_id: Mapped[int] = mapped_column(ForeignKey("task_instances.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    photo_file_id: Mapped[str] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task_instance: Mapped[TaskInstance] = relationship(back_populates="report")
    user: Mapped[User] = relationship(back_populates="reports")


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("task_instance_id", "voter_id", name="uq_vote_unique"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_instance_id: Mapped[int] = mapped_column(ForeignKey("task_instances.id"), index=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    value: Mapped[VoteValue] = mapped_column(Enum(VoteValue))
    voted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task_instance: Mapped[TaskInstance] = relationship(back_populates="votes")
    voter: Mapped[User] = relationship()


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    task_instance_id: Mapped[int | None] = mapped_column(ForeignKey("task_instances.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    season: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped[User] = relationship(back_populates="events")
    task_instance: Mapped[Optional[TaskInstance]] = relationship()


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_instance_id: Mapped[int] = mapped_column(ForeignKey("task_instances.id"), index=True)
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[DisputeState] = mapped_column(Enum(DisputeState), default=DisputeState.open, index=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    task_instance: Mapped[TaskInstance] = relationship(back_populates="dispute")


class TaskBroadcast(Base):
    __tablename__ = "task_broadcasts"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_broadcast"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task_instances.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chat_id: Mapped[int] = mapped_column(Integer)
    message_id: Mapped[int] = mapped_column(Integer)


