from __future__ import annotations

import ast
import difflib
import os
import uuid
from pathlib import Path

from pydantic import BaseModel

from ingestion.redactor import redact_secrets
from providers import BaseLLMProvider
from review.prompts import PATCH_SYSTEM_INSTRUCTION
from schemas.contracts import FileEdit, Finding, Patch, PatchStatus
from schemas.provider import PatchProposalResult, StructuredGenerationRequest

PROTECTED_PATH_PATTERNS = [
    ".github/",
    ".circleci/",
    "tests/",
    "verification/",
    "Makefile",
    "docker-compose.yml",
    "compose.yaml",
]


class PatchGenerationResult(BaseModel):
    success: bool
    patch: Patch | None = None
    error: str | None = None


def apply_edits_to_text(file_content: str, edits: list[FileEdit]) -> tuple[str, str | None]:
    """Apply atomic string replacements to file content."""
    modified = file_content
    for edit in edits:
        if not edit.old_content:
            return file_content, "Empty old_content in edit"
        if edit.old_content == edit.replacement:
            return file_content, "No-op edit detected (old_content equals replacement)"
        if modified.count(edit.old_content) != 1:
            return (
                file_content,
                f"Target content not found uniquely in file (stale or ambiguous base). Target:\n{edit.old_content[:100]}",
            )

        # Replace first occurrence
        modified = modified.replace(edit.old_content, edit.replacement, 1)

    return modified, None


class Patcher:
    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    def propose_patch(
        self,
        finding: Finding,
        workspace_head_dir: Path,
        relevant_context: str = "",
    ) -> PatchGenerationResult:
        """Call LLM to propose structured surgical edits for finding."""
        target_path = finding.primary_location.path.strip().lstrip("/")
        full_path = (workspace_head_dir / target_path).resolve()
        if not full_path.is_relative_to(workspace_head_dir.resolve()):
            return PatchGenerationResult(success=False, error="Target escapes workspace")

        if not full_path.exists():
            return PatchGenerationResult(
                success=False,
                error=f"Target file {target_path} not found in workspace",
            )

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            file_content = f.read()

        context_lines = [
            f"Review Finding: {finding.title}",
            f"Category: {finding.category.value}",
            f"Rule ID: {finding.rule_id}",
            f"File: {target_path}",
            f"Line Range: {finding.primary_location.start_line}-{finding.primary_location.end_line}",
            f"Explanation: {finding.explanation}",
            f"Proposed Remedy: {finding.proposed_remedy or 'Fix the issue surgically'}",
            "\nTarget File Full Content:\n```"
            + {".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".jsx": "jsx"}.get(
                full_path.suffix, "text"
            ),
            redact_secrets(file_content)[0],
            "```",
        ]
        if relevant_context:
            context_lines.extend(["\nRelated Context:\n", relevant_context])

        req = StructuredGenerationRequest(
            run_id=finding.run_id,
            stage="patch",
            deadline_ms=int(getattr(self.provider, "request_timeout_seconds", 45) * 1000),
            model_role="patch",
            system_instruction=PATCH_SYSTEM_INSTRUCTION,
            context=redact_secrets("\n".join(context_lines))[0],
        )

        resp = self.provider.generate_structured(req, PatchProposalResult)
        if not resp.success or not resp.data:
            return PatchGenerationResult(
                success=False,
                error=f"Patch generation failed: {resp.error}",
            )

        edits = [
            FileEdit(
                path=e.path if e.path else target_path,
                old_content=e.old_content,
                replacement=e.replacement,
                rationale=e.rationale,
            )
            for e in resp.data.edits
        ]

        # Validate edits
        for edit in edits:
            norm = os.path.normpath(edit.path)
            if norm != target_path or not (workspace_head_dir / norm).resolve().is_relative_to(
                workspace_head_dir.resolve()
            ):
                return PatchGenerationResult(success=False, error="Patch must modify only the cited target file")
            for protected in PROTECTED_PATH_PATTERNS:
                if norm.startswith(protected):
                    return PatchGenerationResult(
                        success=False,
                        error=f"Patch attempted to modify protected file: {norm}",
                    )

        if not edits:
            return PatchGenerationResult(success=False, error="Empty patch")

        # Apply edits in-memory and compute diff
        modified_content, apply_err = apply_edits_to_text(file_content, edits)
        if apply_err:
            return PatchGenerationResult(success=False, error=apply_err)

        # Check Python syntax validity
        if target_path.endswith(".py"):
            try:
                ast.parse(modified_content)
            except SyntaxError as e:
                return PatchGenerationResult(
                    success=False,
                    error=f"Patch produced invalid Python syntax: {e}",
                )

        if full_path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            from analysis.languages import javascript_analysis

            parse_findings, _, coverage = javascript_analysis(
                [{"relative_path": target_path, "content": modified_content}], finding.run_id
            )
            if coverage["status"] == "failed":
                return PatchGenerationResult(
                    success=False,
                    error="Cannot validate JavaScript/TypeScript patch syntax: trusted parser unavailable",
                )
            syntax_errors = [item for item in parse_findings if item.rule_id == "js:syntax"]
            if syntax_errors:
                return PatchGenerationResult(
                    success=False,
                    error="Patch produced invalid JavaScript/TypeScript syntax: " + syntax_errors[0].explanation,
                )

        # Compute unified diff
        diff_lines = list(
            difflib.unified_diff(
                file_content.splitlines(keepends=True),
                modified_content.splitlines(keepends=True),
                fromfile=f"a/{target_path}",
                tofile=f"b/{target_path}",
            )
        )
        unified_diff_text = "".join(diff_lines)

        short_id = str(uuid.uuid4())[:8]
        branch_name = f"proofline/fix/{short_id}"

        patch_obj = Patch(
            id=str(uuid.uuid4()),
            finding_id=finding.id,
            run_id=finding.run_id,
            branch_name=branch_name,
            status=PatchStatus.PROPOSED,
            edits=edits,
            diff=unified_diff_text,
        )

        return PatchGenerationResult(success=True, patch=patch_obj)
