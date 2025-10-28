"""Home Bot package initialisation."""

from __future__ import annotations

import os


os.environ.setdefault("BOT_TOKEN", os.environ.get("BOT_TOKEN", "placeholder-token"))
