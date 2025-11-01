"""Tests for application configuration behaviour."""

import pytest

from household_bot.core.config import Settings


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_TOKEN", "token")
    monkeypatch.setenv("GROUP_CHAT_ID", "1")


def test_participant_ids_accepts_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma separated participant IDs should be parsed into integers."""

    _base_env(monkeypatch)
    monkeypatch.setenv("PARTICIPANT_IDS", "1, 2,3")

    settings = Settings(_env_file=None)

    assert settings.PARTICIPANT_IDS == [1, 2, 3]


def test_participant_ids_handles_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid JSON should still be supported for participant IDs."""

    _base_env(monkeypatch)
    monkeypatch.setenv("PARTICIPANT_IDS", "[4,5,6]")

    settings = Settings(_env_file=None)

    assert settings.PARTICIPANT_IDS == [4, 5, 6]
