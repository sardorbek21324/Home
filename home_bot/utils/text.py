"""Text formatting helpers."""

from __future__ import annotations

from html import escape as _html_escape


def escape_html(value: str | None) -> str:
    """Return HTML-escaped text safe for Telegram parse mode."""

    if value is None:
        return ""
    return _html_escape(value, quote=False)
