"""Budgeted project review batches with honest source coverage."""

import time
from pathlib import Path

from analysis.languages import SUPPORTED, select_context
from ingestion.redactor import redact_secrets
from schemas.provider import ProviderResponse, ProviderUsage, ReviewCandidatesResult, StructuredGenerationRequest


def project_batches(files, depth, budget, max_calls):
    inventory = sorted(
        [f for f in files if Path(f["relative_path"]).suffix in SUPPORTED], key=lambda f: f["relative_path"]
    )
    if depth == "quick":
        text, coverage = select_context(inventory, set(), budget)
        selected = [p for p in coverage["selected"] if p not in coverage["omitted"]]
        return [(text, selected)] if selected else [], sorted(
            set(f["relative_path"] for f in inventory) - set(selected)
        )
    batches = []
    chunks = []
    paths = []
    used = 0
    omitted = []
    for f in inventory:
        block = (
            "File: "
            + f["relative_path"]
            + "\n"
            + "\n".join(f"{i + 1}: {line}" for i, line in enumerate(f["content"].splitlines()))
        )
        if len(block) > budget:
            omitted.append(f["relative_path"])
            continue
        if chunks and used + len(block) > budget:
            batches.append(("\n\n".join(chunks), paths))
            chunks = []
            paths = []
            used = 0
        chunks.append(block)
        paths.append(f["relative_path"])
        used += len(block)
    if chunks:
        batches.append(("\n\n".join(chunks), paths))
    for _, excluded in batches[max_calls:]:
        omitted.extend(excluded)
    return batches[:max_calls], omitted


def review_project(
    provider,
    run_id,
    files,
    depth,
    budget,
    max_calls,
    instruction,
    event=None,
    deadline_seconds=180,
    supplemental_context="",
):
    batches, omitted = project_batches(files, depth, budget, max_calls)
    data = ReviewCandidatesResult()
    usage = ProviderUsage()
    errors = []
    reviewed = []
    deadline = time.monotonic() + deadline_seconds
    for i, (text, paths) in enumerate(batches):
        if time.monotonic() >= deadline:
            errors.append("Project review deadline reached; remaining batches omitted")
            break
        if event:
            event(i + 1, len(batches))
        safe, _ = redact_secrets(text)
        response = provider.generate_structured(
            StructuredGenerationRequest(
                run_id=run_id,
                stage="project_review",
                model_role="review",
                system_instruction=instruction
                + "\nReview this project snapshot, not an invented diff. Describe module-level correctness, security and maintainability. All citations require supplied line numbers.",
                context=safe + "\nSUPPLEMENTAL INVESTIGATION:\n" + supplemental_context[:30000],
                deadline_ms=max(1, min(45000, int((deadline - time.monotonic()) * 1000))),
            ),
            ReviewCandidatesResult,
        )
        usage.prompt_tokens += response.usage.prompt_tokens
        usage.candidate_tokens += response.usage.candidate_tokens
        usage.total_tokens += response.usage.total_tokens
        usage.thought_tokens += response.usage.thought_tokens
        usage.cached_content_token_count += response.usage.cached_content_token_count
        if response.success and response.data:
            reviewed.extend(paths)
            data.findings.extend(response.data.findings)
            if response.data.review_summary:
                data.review_summary += "\n" + response.data.review_summary
        else:
            errors.append(response.error or "Batch failed")
    coverage = {
        "depth": depth,
        "batches": len(batches),
        "reviewed_files": reviewed,
        "omitted_files": sorted(set(omitted) | {p for _, paths in batches for p in paths if p not in reviewed}),
        "supported_files": sum(Path(f["relative_path"]).suffix in SUPPORTED for f in files),
        "limitations": "Model inspected bounded source batches; no guarantee of exhaustive repository reasoning",
    }
    if not batches:
        errors.append("No supported source fits the configured context budget")
    return ProviderResponse(
        success=not errors,
        data=data,
        model_id=getattr(provider, "default_model", "unavailable"),
        usage=usage,
        error="; ".join(errors) or None,
    ), coverage
