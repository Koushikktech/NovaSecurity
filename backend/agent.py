"""Proofline Agent Shim — Deprecated.

Active pipeline orchestration lives in backend/review/orchestrator.py.
"""
from __future__ import annotations

from review.orchestrator import ReviewOrchestrator

__all__ = ["ReviewOrchestrator"]
