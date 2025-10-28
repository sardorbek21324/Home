"""Utilities for calculating rewards and penalties."""

from __future__ import annotations

from datetime import datetime
from math import floor

from ..domain.constants import (
    FIRST_DEFER_PENALTY,
    MISS_PENALTY_MULTIPLIER,
    SECOND_DEFER_PENALTY,
)
from ..db.models import TaskInstance, TaskKind, TaskTemplate


def calc_task_reward(template: TaskTemplate) -> int:
    """Derive effective reward for template using simple rule-based heuristics."""

    base = template.base_points
    stats = getattr(template, "_scoring_stats", {}) or {}
    recent_completions = int(stats.get("recent_completions", 0) or 0)
    last_completed = stats.get("last_completed")
    oldest_open = stats.get("oldest_open")
    reward = base

    is_quick = template.kind == TaskKind.mini or template.sla_minutes <= 45
    if is_quick and recent_completions > 1:
        reward -= min(recent_completions - 1, max(base // 3, 1))

    now = datetime.utcnow()
    anchor = oldest_open or last_completed
    if anchor:
        idle_hours = max((now - anchor).total_seconds() / 3600, 0)
        if idle_hours >= 12:
            reward += min(6, int(idle_hours // 12))
    else:
        reward += 2

    return max(1, reward)


def penalty_for_skip(skips: int) -> int:
    """Return penalty points for deferring/skip actions."""

    if skips <= 0:
        return 0
    return min(5, skips)


def bonus_for_first_taker(is_first: bool) -> int:
    return 1 if is_first else 0


def reward_for_completion(instance: TaskInstance) -> int:
    penalty_pct = 0.0
    if instance.deferrals_used >= 1:
        penalty_pct += FIRST_DEFER_PENALTY
    if instance.deferrals_used >= 2:
        penalty_pct += SECOND_DEFER_PENALTY
    base = instance.effective_points or instance.template.base_points
    return max(0, floor(base * (1 - penalty_pct)))


def missed_penalty(template: TaskTemplate) -> int:
    return -abs(template.base_points * MISS_PENALTY_MULTIPLIER)
