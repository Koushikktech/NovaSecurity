from __future__ import annotations

import re
import shlex
from typing import Literal

from pydantic import BaseModel, Field


class DiffHunkLine(BaseModel):
    origin: Literal["+", "-", " ", "\\"]  # + = add, - = del, ' ' = context, \ = no newline
    content: str
    old_line_no: int | None = None
    new_line_no: int | None = None


class DiffHunk(BaseModel):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = ""
    lines: list[DiffHunkLine] = Field(default_factory=list)


class DiffFile(BaseModel):
    old_path: str
    new_path: str
    status: Literal["added", "deleted", "modified", "renamed"]
    is_binary: bool = False
    hunks: list[DiffHunk] = Field(default_factory=list)
    added_lines_head: list[int] = Field(default_factory=list)
    deleted_lines_base: list[int] = Field(default_factory=list)


class ParsedDiff(BaseModel):
    files: list[DiffFile] = Field(default_factory=list)
    raw_diff: str = ""
    total_additions: int = 0
    total_deletions: int = 0

    def get_file(self, path: str) -> DiffFile | None:
        norm = path.strip().lstrip("/")
        for f in self.files:
            if f.new_path.strip().lstrip("/") == norm or f.old_path.strip().lstrip("/") == norm:
                return f
        return None

    def is_line_introduced(self, path: str, line_no: int) -> bool:
        df = self.get_file(path)
        if not df:
            return False
        return line_no in df.added_lines_head


HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$")


def parse_unified_diff(raw_diff: str) -> ParsedDiff:
    """Robust parser for unified git diff output."""
    parsed = ParsedDiff(raw_diff=raw_diff)
    if not raw_diff or not raw_diff.strip():
        return parsed

    lines = raw_diff.splitlines()
    i = 0
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    old_line_cursor = 0
    new_line_cursor = 0

    while i < len(lines):
        line = lines[i]

        # Check for diff header: diff --git a/file b/file
        if line.startswith("diff --git "):
            # Save previous hunk and file
            if current_hunk and current_file:
                current_file.hunks.append(current_hunk)
                current_hunk = None
            if current_file:
                parsed.files.append(current_file)

            parts = shlex.split(line)
            old_p = parts[2].replace("a/", "", 1) if len(parts) > 2 else "unknown"
            new_p = parts[3].replace("b/", "", 1) if len(parts) > 3 else old_p

            current_file = DiffFile(
                old_path=old_p,
                new_path=new_p,
                status="modified",
            )
            i += 1
            continue

        if current_file is None:
            i += 1
            continue

        # File status metadata
        if line.startswith("new file mode"):
            current_file.status = "added"
        elif line.startswith("deleted file mode"):
            current_file.status = "deleted"
        elif line.startswith("similarity index"):
            current_file.status = "renamed"
        elif line.startswith("rename from "):
            current_file.old_path = line[len("rename from ") :].strip()
        elif line.startswith("rename to "):
            current_file.new_path = line[len("rename to ") :].strip()
        elif line.startswith("Binary files "):
            current_file.is_binary = True

        # Hunk header
        match = HUNK_HEADER_RE.match(line)
        if match:
            if current_hunk:
                current_file.hunks.append(current_hunk)

            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1
            header_desc = match.group(5).strip()

            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header=header_desc,
            )
            old_line_cursor = old_start
            new_line_cursor = new_start
            i += 1
            continue

        # Inside hunk
        if current_hunk is not None:
            if line.startswith("+"):
                h_line = DiffHunkLine(
                    origin="+",
                    content=line[1:],
                    old_line_no=None,
                    new_line_no=new_line_cursor,
                )
                current_file.added_lines_head.append(new_line_cursor)
                parsed.total_additions += 1
                new_line_cursor += 1
                current_hunk.lines.append(h_line)
            elif line.startswith("-"):
                h_line = DiffHunkLine(
                    origin="-",
                    content=line[1:],
                    old_line_no=old_line_cursor,
                    new_line_no=None,
                )
                current_file.deleted_lines_base.append(old_line_cursor)
                parsed.total_deletions += 1
                old_line_cursor += 1
                current_hunk.lines.append(h_line)
            elif line.startswith(" "):
                h_line = DiffHunkLine(
                    origin=" ",
                    content=line[1:],
                    old_line_no=old_line_cursor,
                    new_line_no=new_line_cursor,
                )
                old_line_cursor += 1
                new_line_cursor += 1
                current_hunk.lines.append(h_line)
            elif line.startswith("\\"):
                # "\ No newline at end of file"
                h_line = DiffHunkLine(origin="\\", content=line[1:])
                current_hunk.lines.append(h_line)

        i += 1

    # Append trailing hunk and file
    if current_hunk and current_file:
        current_file.hunks.append(current_hunk)
    if current_file:
        parsed.files.append(current_file)

    return parsed
