"""Compatibility package aliasing :mod:`household_bot`."""

from household_bot import *  # noqa: F401,F403

__all__ = [name for name in globals() if not name.startswith("_")]
