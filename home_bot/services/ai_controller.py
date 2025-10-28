"""AI-driven reward controller for adaptive task scoring."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Callable

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..db.models import AISettings, TaskInstance, TaskStatus, User
from ..db.repo import ensure_ai_settings


@dataclass(slots=True)
class UserRewardStats:
    """Aggregated statistics for adaptive rewards."""

    user_id: int
    tg_id: int | None
    name: str
    taken: int
    completed: int
    skipped: int
    coefficient: float


class AIController:
    """Encapsulates dynamic reward coefficient logic."""

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory: Callable[[], Session] = session_factory or SessionLocal

    def _collect_raw_stats(self, session: Session) -> dict[int, tuple[int, int]]:
        taken_case = func.count(TaskInstance.id)
        completed_case = func.sum(
            case((TaskInstance.status == TaskStatus.approved, 1), else_=0)
        )
        stmt = (
            select(
                TaskInstance.assigned_to.label("user_id"),
                taken_case.label("taken"),
                completed_case.label("completed"),
            )
            .where(TaskInstance.assigned_to.isnot(None))
            .group_by(TaskInstance.assigned_to)
        )
        stats: dict[int, tuple[int, int]] = {}
        for row in session.execute(stmt):
            user_id = int(row.user_id)
            taken = int(row.taken or 0)
            completed = int(row.completed or 0)
            stats[user_id] = (taken, completed)
        return stats

    def _calculate_coefficient(
        self,
        settings_row: AISettings,
        *,
        taken: int,
        completed: int,
    ) -> float:
        skipped = max(taken - completed, 0)
        coeff = (
            settings_row.default_coefficient
            + skipped * settings_row.penalty_step
            - completed * settings_row.bonus_step
        )
        coeff = min(settings_row.max_coefficient, max(settings_row.min_coefficient, coeff))
        return round(coeff, 4)

    def _ensure_settings(self, session: Session) -> AISettings:
        return ensure_ai_settings(session)

    def get_user_stats(self, session: Session) -> list[UserRewardStats]:
        """Return reward coefficients and task history per user."""

        users = {user.id: user for user in session.scalars(select(User))}
        if not users:
            return []

        settings_row = self._ensure_settings(session)
        raw_stats = self._collect_raw_stats(session)
        stats: list[UserRewardStats] = []
        for user_id, user in users.items():
            taken, completed = raw_stats.get(user_id, (0, 0))
            skipped = max(taken - completed, 0)
            coeff = self._calculate_coefficient(
                settings_row, taken=taken, completed=completed
            )
            stats.append(
                UserRewardStats(
                    user_id=user_id,
                    tg_id=user.tg_id if user else None,
                    name=user.name if user else f"#{user_id}",
                    taken=taken,
                    completed=completed,
                    skipped=skipped,
                    coefficient=coeff,
                )
            )
        stats.sort(key=lambda item: item.name.lower())
        return stats

    def average_coefficient(self, session: Session) -> float:
        """Return the average coefficient across all users."""

        users = session.scalars(select(User)).all()
        if not users:
            settings_row = self._ensure_settings(session)
            return settings_row.default_coefficient
        settings_row = self._ensure_settings(session)
        raw_stats = self._collect_raw_stats(session)
        coeffs: list[float] = []
        for user in users:
            taken, completed = raw_stats.get(user.id, (0, 0))
            coeffs.append(
                self._calculate_coefficient(
                    settings_row, taken=taken, completed=completed
                )
            )
        if not coeffs:
            return settings_row.default_coefficient
        return float(round(mean(coeffs), 4))

    def apply_to_points(self, session: Session, base_points: int) -> int:
        """Calculate effective points for a template using current coefficient."""

        coefficient = self.average_coefficient(session)
        return max(1, int(round(base_points * coefficient)))

    def get_config(self, session: Session) -> AISettings:
        return self._ensure_settings(session)

    def update_config(
        self,
        session: Session,
        *,
        penalty_step: float | None = None,
        bonus_step: float | None = None,
        min_coefficient: float | None = None,
        max_coefficient: float | None = None,
        default_coefficient: float | None = None,
    ) -> AISettings:
        settings_row = self._ensure_settings(session)
        if penalty_step is not None:
            settings_row.penalty_step = penalty_step
        if bonus_step is not None:
            settings_row.bonus_step = bonus_step
        if min_coefficient is not None:
            settings_row.min_coefficient = min_coefficient
        if max_coefficient is not None:
            settings_row.max_coefficient = max_coefficient
        if default_coefficient is not None:
            settings_row.default_coefficient = default_coefficient
        session.flush()
        return settings_row

    def healthcheck(self, session: Session | None = None) -> str:
        """Return a brief textual status of the AI controller."""

        close_session = False
        if session is None:
            session = self._session_factory()
            close_session = True
        try:
            settings_row = self._ensure_settings(session)
            avg = self.average_coefficient(session)
            return f"ok (avg={avg:.2f}, steps={settings_row.penalty_step}/{settings_row.bonus_step})"
        finally:
            if close_session:
                session.close()

    def stats_snapshot(self) -> list[UserRewardStats]:
        """Convenience helper that opens its own session."""

        with self._session_factory() as session:
            return self.get_user_stats(session)

    def config_snapshot(self) -> AISettings:
        with self._session_factory() as session:
            return self._ensure_settings(session)
