"""Database models used by the bot."""
from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum as PgEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String)
    first_name = Column(String)
    monthly_score = Column(Integer, default=0)


class TaskStatus(enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    FAILED = "failed"
    MISSED = "missed"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    status = Column(PgEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    assignee_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assignee = relationship("User")


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    decision = Column(Boolean)


class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True)
    week_number = Column(Integer, nullable=False, index=True)
    theme = Column(String, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    tasks_completed = Column(Integer, default=0)
