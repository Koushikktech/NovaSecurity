"""Ordinary tests never opt into the operator's live subscription provider."""

import pytest

from config import settings


@pytest.fixture(autouse=True)
def disable_live_codex_by_default(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "codex_cli_enabled", False)
