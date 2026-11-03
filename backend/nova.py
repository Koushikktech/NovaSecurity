"""Proofline Provider Shim — Deprecated.

All active LLM capabilities in Proofline are natively powered by Google Gemini
via backend/providers/gemini.py using the official google-genai SDK.
"""
from __future__ import annotations

from providers.fake import FakeLLMProvider
from providers.gemini import GeminiProvider

__all__ = ["GeminiProvider", "FakeLLMProvider"]
