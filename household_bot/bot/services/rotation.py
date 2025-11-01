"""Simple round-robin rotation helpers."""
from __future__ import annotations

import itertools
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from household_bot.core.config import settings

_ROTATION_STATE: Dict[str, itertools.cycle] = {}


async def get_next_in_rotation(session: AsyncSession, category: str) -> int:
    """Return the next participant for the given task category."""
    del session  # rotation is purely configuration based for now
    if category not in _ROTATION_STATE:
        participants = [*settings.PARTICIPANT_IDS]
        _ROTATION_STATE[category] = itertools.cycle(participants)
    return next(_ROTATION_STATE[category])
