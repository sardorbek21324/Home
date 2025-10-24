from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum
from datetime import datetime, date
import enum
from . import Base

class Role(str, enum.Enum):
    admin = "admin"
    member = "member"

class Status(str, enum.Enum):
    available = "available"
    busy_until = "busy_until"
    day_off = "day_off"
    vacation = "vacation"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(Enum(Role), default=Role.member)
    status: Mapped[str] = mapped_column(Enum(Status), default=Status.available)
    busy_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    vacation_from: Mapped[date | None] = mapped_column(nullable=True)
    vacation_to: Mapped[date | None] = mapped_column(nullable=True)
    monthly_points: Mapped[int] = mapped_column(Integer, default=0)
    penalty_multiplier: Mapped[int] = mapped_column(Integer, default=0)
    missed_checks_streak: Mapped[int] = mapped_column(Integer, default=0)

class TaskKind(str, enum.Enum):
    main = "main"
    mini = "mini"
    external = "external"

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(Enum(TaskKind))
    base_points: Mapped[int] = mapped_column(Integer)
    freq: Mapped[str] = mapped_column(String(64))
    response_window_minutes: Mapped[int] = mapped_column(Integer)
    execution_window_minutes: Mapped[int] = mapped_column(Integer)
    min_points: Mapped[int] = mapped_column(Integer, default=1)
    max_points: Mapped[int] = mapped_column(Integer, default=20)

class InstanceState(str, enum.Enum):
    announced = "announced"
    taken_now = "taken_now"
    taken_later = "taken_later"
    awaiting_proof = "awaiting_proof"
    awaiting_check = "awaiting_check"
    disputed = "disputed"
    done = "done"
    failed = "failed"
    expired = "expired"

class TaskInstance(Base):
    __tablename__ = "task_instances"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    state: Mapped[str] = mapped_column(Enum(InstanceState), default=InstanceState.announced)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    defer_count: Mapped[int] = mapped_column(Integer, default=0)
    reward_points_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retries_today: Mapped[int] = mapped_column(Integer, default=0)
    last_announce_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_instance_id: Mapped[int] = mapped_column(ForeignKey("task_instances.id"))
    photo_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    video_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    first_vote_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    votes_yes: Mapped[int] = mapped_column(Integer, default=0)
    votes_no: Mapped[int] = mapped_column(Integer, default=0)
    voter1_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voter1_vote: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 'yes'/'no'
    voter2_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voter2_vote: Mapped[str | None] = mapped_column(String(8), nullable=True)
    awaiting_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class History(Base):
    __tablename__ = "history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task_instance_id: Mapped[int | None] = mapped_column(ForeignKey("task_instances.id"), nullable=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AIPatch(Base):
    __tablename__ = "ai_patches"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patch_json: Mapped[str] = mapped_column(String, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
