"""Asynchronous helper functions for database access."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from household_bot.db.models import Challenge, Task, TaskStatus, User, Vote


class DBRepository:
    """Tiny repository helper around SQLAlchemy queries."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_user(self, telegram_id: int) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def ensure_user(self, telegram_id: int, username: str | None, first_name: str | None) -> User:
        user = await self.get_user(telegram_id)
        if user:
            return user
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_user_score(self, telegram_id: int, delta: int) -> None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return
        user.monthly_score = (user.monthly_score or 0) + delta
        await self._session.commit()

    async def apply_group_penalty(self, penalty: int) -> None:
        result = await self._session.execute(select(User))
        users = result.scalars().all()
        for user in users:
            user.monthly_score = (user.monthly_score or 0) + penalty
        await self._session.commit()

    async def list_users_by_score(self) -> list[User]:
        result = await self._session.execute(
            select(User).order_by(User.monthly_score.desc())
        )
        return list(result.scalars())

    async def create_task(self, name: str, category: str) -> Task:
        task = Task(name=name, category=category)
        self._session.add(task)
        await self._session.commit()
        await self._session.refresh(task)
        return task

    async def get_task(self, task_id: int) -> Optional[Task]:
        result = await self._session.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def assign_task(self, task_id: int, assignee_id: int) -> None:
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(status=TaskStatus.ASSIGNED, assignee_id=assignee_id)
        )
        await self._session.commit()

    async def update_task_status(self, task_id: int, status: TaskStatus) -> None:
        await self._session.execute(
            update(Task).where(Task.id == task_id).values(status=status)
        )
        await self._session.commit()

    async def record_vote(self, task_id: int, user_id: int, decision: bool) -> Vote:
        vote = Vote(task_id=task_id, user_id=user_id, decision=decision)
        self._session.add(vote)
        await self._session.commit()
        await self._session.refresh(vote)
        return vote

    async def increment_challenge(self, user_id: int, week_number: int) -> None:
        result = await self._session.execute(
            select(Challenge).where(
                Challenge.user_id == user_id,
                Challenge.week_number == week_number,
            )
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            challenge = Challenge(
                user_id=user_id,
                week_number=week_number,
                theme="general",
                tasks_completed=1,
            )
            self._session.add(challenge)
        else:
            challenge.tasks_completed = (challenge.tasks_completed or 0) + 1
        await self._session.commit()
