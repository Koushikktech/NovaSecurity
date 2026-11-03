"""Proofline Remediation Shim — Deprecated.

Active remediation and verified repair loop logic lives in:
- backend/remediation/patcher.py (Patcher)
- backend/verification/runner.py (VerificationRunner)
"""
from __future__ import annotations

from remediation.patcher import Patcher, apply_edits_to_text

__all__ = ["Patcher", "apply_edits_to_text"]
