"""Operator-local immutable source checkpoints used to resume without refetching Git."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ingestion.source_policy import sensitive_source_path
from storage import atomic_json


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save_snapshot(root: Path, metadata, head_files, base_files, diff):
    payload = {"metadata": metadata, "head": head_files, "base": base_files, "diff": diff}
    document = {"version": 1, "digest": _digest(payload), "payload": payload}
    root.mkdir(parents=True, exist_ok=True)
    path = root / "snapshot.json"
    atomic_json(path, document)
    return document["digest"]


def load_snapshot(root: Path):
    path = root / "snapshot.json"
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Oversized source checkpoint")
    document = json.loads(path.read_text())
    if (
        not isinstance(document, dict)
        or document.get("version") != 1
        or "payload" not in document
        or document.get("digest") != _digest(document["payload"])
    ):
        raise ValueError("Source checkpoint integrity check failed")
    payload = document["payload"]
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("metadata"), dict)
        or not isinstance(payload.get("diff"), str)
    ):
        raise ValueError("Invalid source checkpoint structure")
    for side in ("head", "base"):
        files = payload.get(side)
        if not isinstance(files, list) or len(files) > 2000:
            raise ValueError("Invalid source checkpoint inventory")
        for item in files:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("relative_path"), str)
                or not isinstance(item.get("content"), str)
            ):
                raise ValueError("Invalid source checkpoint entry")
            if sensitive_source_path(item["relative_path"]):
                raise ValueError("Saved source includes an excluded credential path; start a new review")
    return payload, document["digest"]


def materialize(files, destination):
    for item in files:
        relative = item["relative_path"]
        target = (destination / relative).resolve()
        if (
            not target.is_relative_to(destination.resolve())
            or Path(relative).is_absolute()
            or ".git" in Path(relative).parts
            or sensitive_source_path(relative)
        ):
            raise ValueError("Invalid snapshot path")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError("Symlink in restore workspace")
        target.write_text(item["content"])
