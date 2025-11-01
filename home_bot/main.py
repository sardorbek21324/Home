"""Compatibility entry point for environments expecting :mod:`home_bot.main`."""
from __future__ import annotations

import asyncio

from main import main as _root_main


async def main() -> None:
    """Delegate execution to the project's async :func:`main` function."""
    await _root_main()


if __name__ == "__main__":  # pragma: no cover - convenience for manual runs
    asyncio.run(main())
