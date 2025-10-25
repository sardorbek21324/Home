"""Utilities for calculating rewards and penalties."""

from __future__ import annotations

from math import floor

from ..domain.constants import (
    FIRST_DEFER_PENALTY,
    SECOND_DEFER_PENALTY,
    MISS_PENALTY_MULTIPLIER,
)
from ..db.models import TaskTemplate


def reward_for_completion(template: TaskTemplate, deferrals_used: int) -> int:
    penalty_pct = 0.0
    if deferrals_used >= 1:
        penalty_pct += FIRST_DEFER_PENALTY
    if deferrals_used >= 2:
        penalty_pct += SECOND_DEFER_PENALTY
    base = template.base_points
    return max(0, floor(base * (1 - penalty_pct)))


def missed_penalty(template: TaskTemplate) -> int:
    return -abs(template.base_points * MISS_PENALTY_MULTIPLIER)
