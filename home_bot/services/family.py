"""In-memory helpers for managing family member ids."""

from __future__ import annotations

import logging
from typing import Iterable, List

from ..config import settings
from ..db.repo import (
    add_family_member_entry,
    list_family_member_ids,
    remove_family_member_entry,
    session_scope,
)

logger = logging.getLogger(__name__)

_family_ids: set[int] = set()
_initialized = False


def _apply(ids: Iterable[int]) -> List[int]:
    values = sorted({int(value) for value in ids})
    _family_ids.clear()
    _family_ids.update(values)
    settings.set_family_ids(values)
    return values


def ensure_loaded(*, log: bool = False) -> List[int]:
    global _initialized
    if _initialized:
        return get_family_ids()

    with session_scope() as session:
        stored = list_family_member_ids(session)
        if not stored:
            defaults = list(settings.FAMILY_IDS)
            if defaults:
                for item in defaults:
                    add_family_member_entry(session, int(item))
                session.flush()
                stored = list_family_member_ids(session)
            if log:
                logger.info("Seeded %s default family members", len(stored))
    values = _apply(stored)
    _initialized = True
    if log:
        logger.info("Family cache initialised with %s ids", len(values))
    return values


def get_family_ids() -> List[int]:
    if not _initialized:
        return ensure_loaded()
    return sorted(_family_ids)


def add_family_member(tg_id: int) -> bool:
    ensure_loaded()
    with session_scope() as session:
        created = add_family_member_entry(session, tg_id)
        if not created:
            return False
        session.flush()
    _family_ids.add(int(tg_id))
    settings.set_family_ids(get_family_ids())
    logger.info("Added family member %s", tg_id)
    return True


def remove_family_member(tg_id: int) -> bool:
    ensure_loaded()
    with session_scope() as session:
        removed = remove_family_member_entry(session, tg_id)
        if not removed:
            return False
    if tg_id in _family_ids:
        _family_ids.remove(tg_id)
        settings.set_family_ids(get_family_ids())
    logger.info("Removed family member %s", tg_id)
    return True
