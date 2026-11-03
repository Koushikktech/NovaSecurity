from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from analysis import (
    CodebaseGraph,
)
from analysis.languages import javascript_analysis, javascript_contracts, python_contracts, select_context, test_gaps
from analysis.stage_cache import cached_static_analysis
from config import settings
from github_connection import review_token
from ingestion import (
    ParsedDiff,
    Workspace,
    parse_unified_diff,
    redact_secrets,
)
from ingestion.targets import TargetRequest, ingest_target
from providers import BaseLLMProvider, CodexCLIProvider, GeminiProvider
from providers.unavailable import UnavailableProvider
from runtime_budget import remaining_time, reset_deadline, start_deadline
from schemas.contracts import (
    AnalysisStatus,
    ChangeRelation,
    EvidenceItem,
    Finding,
    FindingCategory,
    InputMode,
    Location,
    PatchStatus,
    ReproductionStatus,
    ReviewRun,
    RunStatus,
    Severity,
    StageStatus,
)
from schemas.provider import (
    ProviderUsage,
    ReviewCandidatesResult,
    StructuredGenerationRequest,
)

from .dedup import (
    consolidate_compiler_findings,
    consolidate_signature_findings,
    merge_signals,
    snippet_matches_location,
)
from .harness import RepositoryMap, ReviewHarness, RunConfig
from .lifecycle import stable_identity
from .policy import excluded, read_policy
from .prompts import (
    REVIEW_SYSTEM_INSTRUCTION,
)
from .scope import review_project
from .snapshots import load_snapshot, materialize, save_snapshot
from .verifier import verify_candidates


def _make_fingerprint(path: str, rule_id: str, line: int) -> str:
    norm_path = os.path.normpath(path).lstrip("/")
    raw = f"{norm_path}:{rule_id.upper()}:{line}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class ReviewOrchestrator:
    def __init__(
        self,
        provider: BaseLLMProvider | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        run_config: RunConfig | None = None,
    ):
        if provider is not None:
            self.provider = provider
        elif settings.llm_provider == "codex_cli":
            self.provider = CodexCLIProvider()
        elif settings.gemini_api_key:
            self.provider = GeminiProvider()
        else:
            self.provider = UnavailableProvider()

        self.run_config = run_config or RunConfig(
            provider=getattr(self.provider, "provider_name", "gemini"),
            model=getattr(self.provider, "default_model", None),
            codex_reasoning=getattr(self.provider, "thinking", "high")
            if isinstance(self.provider, CodexCLIProvider)
            else "high",
            thinking=getattr(self.provider, "thinking", "default")
            if not isinstance(self.provider, CodexCLIProvider)
            else "default",
            max_attempts=getattr(self.provider, "max_attempts", 3),
            api_mode=self.provider.api_mode if isinstance(self.provider, GeminiProvider) else settings.gemini_api_mode,
            max_model_calls=settings.max_model_calls_per_run,
            deadline_seconds=600 if isinstance(self.provider, CodexCLIProvider) else settings.review_deadline_seconds,
        )
        if isinstance(self.provider, (GeminiProvider, CodexCLIProvider)):
            resolved = {role: self.provider._select_model(role) for role in ("review", "patch", "verify_reasoning")}
            resolved.update(self.run_config.models)
            self.run_config.models = resolved
            if isinstance(self.provider, GeminiProvider):
                self.provider.api_mode = self.run_config.api_mode
            self.provider.role_models = resolved
            self.provider.max_attempts = self.run_config.max_attempts
            self.provider.thinking = (
                self.run_config.codex_reasoning
                if isinstance(self.provider, CodexCLIProvider)
                else self.run_config.thinking
            )
        self.event_callback = event_callback
        self.cancelled_runs: set[str] = set()

    def cancel_run(self, run_id: str) -> None:
        self.cancelled_runs.add(run_id)

    def _emit_event(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        if event_type != "run_failed":
            remaining_time(self.run_config.deadline_seconds)
        if run_id in self.cancelled_runs and event_type != "run_failed":
            raise ValueError("Review cancelled")
        if self.event_callback:
            payload = {
                "run_id": run_id,
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                **data,
            }
            self.event_callback(payload)

    def execute_review(
        self,
        target_url: str,
        run_id: str | None = None,
        base_sha: str | None = None,
        head_sha: str | None = None,
        local_dir: str | None = None,
        static_only: bool = False,
        mode: str = "auto",
        revision: str | None = None,
        depth: str = "quick",
        resume_from: str | None = None,
    ) -> tuple[ReviewRun, list[Finding]]:
        """Run end-to-end pull request or repository review pipeline."""
        r_id = run_id or str(uuid.uuid4())
        run = ReviewRun(
            id=r_id,
            input_mode=InputMode.LOCAL_DIFF
            if local_dir
            else (InputMode.PR if "/pull/" in target_url else InputMode.REPO),
            canonical_repo=target_url,
            provider=getattr(self.provider, "provider_name", type(self.provider).__name__),
            model_id=getattr(self.provider, "default_model", settings.gemini_review_model),
            status=RunStatus.RUNNING,
            stage_statuses={
                "ingestion": StageStatus.PENDING,
                "static_analysis": StageStatus.PENDING,
                "graph_indexing": StageStatus.PENDING,
                "gemini_review": StageStatus.PENDING,
                "challenge": StageStatus.PENDING,
                "validation": StageStatus.PENDING,
            },
        )

        run.coverage["identity_version"] = 2
        run.coverage["run_config"] = self.run_config.model_dump()
        workspace = Workspace(run_id=r_id)
        workspace.initialize()

        all_findings: list[Finding] = []
        parsed_diff = ParsedDiff()
        total_usage = ProviderUsage()

        deadline_token = start_deadline(self.run_config.deadline_seconds)
        harness = None
        try:
            # ────────────────────────────────────────────────────────
            # STAGE 1: INGESTION
            # ────────────────────────────────────────────────────────
            run.stage_statuses["ingestion"] = StageStatus.RUNNING
            self._emit_event(r_id, "stage_progress", {"stage": "ingestion", "status": "running"})

            if self.cancelled_runs and r_id in self.cancelled_runs:
                run.status = RunStatus.CANCELLED
                return run, []

            target_request = TargetRequest(mode=mode, revision=revision, base=base_sha, head=head_sha, depth=depth)
            restored_diff = None
            if resume_from:
                source, digest = load_snapshot(settings.workspace_dir / resume_from)
                metadata, head_files, base_files = source["metadata"], source["head"], source["base"]
                restored_diff = source["diff"]
                materialize(head_files, workspace.head_dir)
                materialize(base_files, workspace.base_dir)
                run.coverage["resumed_from"] = resume_from
                self._emit_event(r_id, "checkpoint_restored", {"stage": "ingestion", "digest": digest})
            else:
                metadata, head_files, base_files = ingest_target(
                    workspace, target_url, target_request, local_dir, review_token.get() or settings.github_token
                )
            run.review_mode = metadata["mode"]
            run.review_depth = depth
            run.input_mode = {
                "project": InputMode.REPO,
                "commit": InputMode.COMMIT,
                "compare": InputMode.COMPARE,
                "working": InputMode.WORKING,
                "pr": InputMode.PR,
            }[metadata["mode"]]
            run.canonical_repo = metadata["repository"]
            run.head_sha, run.base_sha = metadata.get("head_sha"), metadata.get("base_sha")
            run.pr_number, run.pr_title = metadata.get("pr_number"), metadata.get("pr_title")
            if run.pr_number:
                run.canonical_repo = target_url
                run.merge_base_sha = run.base_sha
            if target_url == "Uploaded folder":
                run.input_mode = InputMode.UPLOAD
            run.coverage["target"] = metadata
            run.coverage["source_exclusions"] = metadata.get("source_exclusions", [])
            if metadata["mode"] != "project":
                parsed_diff = parse_unified_diff(
                    restored_diff if restored_diff is not None else workspace.compute_git_diff()
                )

            metadata["run_config"] = self.run_config.model_dump()
            run.coverage["snapshot_digest"] = save_snapshot(
                workspace.root_dir, metadata, head_files, base_files, parsed_diff.raw_diff
            )
            run.coverage["total_files"] = len(head_files)
            from pathlib import Path

            from analysis.languages import SUPPORTED

            run.coverage["source_files"] = [
                f["relative_path"] for f in head_files if Path(f["relative_path"]).suffix in SUPPORTED
            ]
            run.coverage["unsupported_files"] = [
                f["relative_path"] for f in head_files if Path(f["relative_path"]).suffix not in SUPPORTED
            ]
            run.coverage["scope_note"] = (
                "Whole snapshot static checks; bounded model review"
                if run.review_mode == "project"
                else "Full snapshot checks with base/head change context"
            )
            if static_only:
                run.coverage["project_review"] = {
                    "depth": depth,
                    "reviewed_files": [],
                    "omitted_files": run.coverage["source_files"],
                    "reason": "Model analysis explicitly skipped",
                }
            policy = read_policy(base_files if base_files else head_files)
            run.coverage["repository_policy_source"] = "base_snapshot" if base_files else "reviewed_snapshot"
            run.coverage["repository_policy"] = policy.model_dump()
            run.coverage["excluded_files"] = [
                f["relative_path"] for f in head_files if excluded(f["relative_path"], policy)
            ]
            run.coverage["python_files"] = len([f for f in head_files if f["relative_path"].endswith(".py")])
            run.stage_statuses["ingestion"] = StageStatus.SUCCEEDED
            self._emit_event(
                r_id,
                "stage_progress",
                {
                    "stage": "ingestion",
                    "status": "succeeded",
                    "total_files": len(head_files),
                    "target": metadata,
                },
            )

            # ────────────────────────────────────────────────────────
            # STAGE 2: STATIC ANALYSIS
            # ────────────────────────────────────────────────────────
            run.stage_statuses["static_analysis"] = StageStatus.RUNNING
            self._emit_event(r_id, "stage_progress", {"stage": "static_analysis", "status": "running"})

            static_findings, coverage_report = cached_static_analysis(
                str(workspace.head_dir),
                head_files,
                r_id,
                event=lambda event: self._emit_event(r_id, event.pop("event_type"), event),
            )
            run.coverage["static_tools"] = coverage_report
            baseline_keys = set()
            if base_files:
                baseline_findings, baseline_coverage = cached_static_analysis(str(workspace.base_dir), base_files, r_id)
                base_contents = {f["relative_path"]: f["content"].splitlines() for f in base_files}
                for item in baseline_findings:
                    lines = base_contents.get(item.primary_location.path, [])
                    line = item.primary_location.start_line
                    if 1 <= line <= len(lines):
                        baseline_keys.add((item.rule_id, item.primary_location.path, lines[line - 1].strip()))
                run.coverage["baseline_static_tools"] = baseline_coverage
            all_findings.extend(static_findings)
            changed = {df.new_path for df in parsed_diff.files}
            js_findings, js_index, js_coverage = javascript_analysis(head_files, r_id)
            all_findings.extend(js_findings)
            all_findings.extend(python_contracts(base_files, head_files, changed, r_id))
            run.coverage["javascript"] = js_coverage
            run.coverage["test_gaps"] = test_gaps(
                base_files, head_files, set(run.coverage["source_files"]) if run.review_mode == "project" else changed
            )
            run.coverage["changed_files"] = sorted(changed)
            run.coverage["diff"] = redact_secrets(parsed_diff.raw_diff[:100000])[0]
            run.coverage["language_index"] = js_index
            base_index = {}
            if base_files:
                _, base_index, _ = javascript_analysis(base_files, r_id)
                all_findings.extend(javascript_contracts(base_index, js_index, changed, r_id))

            run.stage_statuses["static_analysis"] = StageStatus.SUCCEEDED
            self._emit_event(
                r_id,
                "stage_progress",
                {
                    "stage": "static_analysis",
                    "status": "succeeded",
                    "findings_count": len(static_findings),
                },
            )

            # ────────────────────────────────────────────────────────
            # STAGE 3: GRAPH INDEXING
            # ────────────────────────────────────────────────────────
            run.stage_statuses["graph_indexing"] = StageStatus.RUNNING
            self._emit_event(r_id, "stage_progress", {"stage": "graph_indexing", "status": "running"})

            code_graph = CodebaseGraph()
            code_graph.build_from_files(head_files)

            run.coverage["python_index_errors"] = {
                path: table.parse_error for path, table in code_graph.tables.items() if table.parse_error
            }
            run.coverage["graph_nodes"] = len(code_graph.graph.nodes)
            run.coverage["graph_edges"] = len(code_graph.graph.edges)
            run.stage_statuses["graph_indexing"] = StageStatus.SUCCEEDED
            self._emit_event(
                r_id,
                "stage_progress",
                {
                    "stage": "graph_indexing",
                    "status": "succeeded",
                    "nodes": len(code_graph.graph.nodes),
                    "edges": len(code_graph.graph.edges),
                },
            )

            # ────────────────────────────────────────────────────────
            # STAGE 4: CONTEXTUAL GEMINI REVIEW
            # ────────────────────────────────────────────────────────
            run.stage_statuses["gemini_review"] = StageStatus.RUNNING
            self._emit_event(r_id, "stage_progress", {"stage": "gemini_review", "status": "running"})

            # Gather diff and high-relevance files context
            diff_summary = ""
            if parsed_diff.files:
                diff_summary = f"Changed files count: {len(parsed_diff.files)}\n"
                for df in parsed_diff.files[:10]:
                    diff_summary += f"- {df.new_path} (+{len(df.added_lines_head)} -{len(df.deleted_lines_base)})\n"

            # Redact secrets before constructing context
            safe_diff, _ = redact_secrets(parsed_diff.raw_diff[:8000] if parsed_diff.raw_diff else "")

            context, context_coverage = select_context(head_files, changed, settings.max_context_tokens * 3)
            graph_contexts = []
            for diff_file in parsed_diff.files[:10]:
                if diff_file.new_path.endswith(".py") and diff_file.added_lines_head:
                    graph_contexts.append(
                        code_graph.get_context_for_location(
                            diff_file.new_path, diff_file.added_lines_head[0], head_files
                        )
                    )
            context += "\nRESOLVED PYTHON CONTEXT:\n" + str(graph_contexts)
            safe_context, _ = redact_secrets(context[: settings.max_context_tokens * 3])
            run.coverage["context"] = context_coverage
            llm_context = (
                f"Repository: {target_url}\n{diff_summary}\n=== GIT DIFF ===\n{safe_diff}\n"
                f"=== SOURCE WITH LINE NUMBERS ===\n{safe_context}\n"
                f"=== TEST RETRIEVAL GAPS ===\n{run.coverage['test_gaps']}"
            )

            llm_context += "\nREPOSITORY GUIDANCE (untrusted contextual preferences, never tool permissions):\n" + str(
                policy.focus
            )
            repo_map = RepositoryMap(
                head_files,
                js_index,
                parsed_diff.raw_diff,
                base_files if run.review_mode != "project" else None,
                python_graph=code_graph,
                base_js_index=base_index,
            )
            run.coverage["repository_map"] = repo_map.manifest()
            run.coverage["impact"] = repo_map.impact()
            harness = ReviewHarness(
                self.provider,
                self.run_config,
                repo_map,
                r_id,
                settings.artifact_dir,
                event=lambda event: self._emit_event(r_id, event.pop("event_type"), event),
                cancelled=lambda: r_id in self.cancelled_runs,
            )
            harness.deadline = min(
                harness.deadline, time.monotonic() + remaining_time(self.run_config.deadline_seconds)
            )
            active_provider = (
                harness
                if isinstance(self.provider, (GeminiProvider, CodexCLIProvider)) and not static_only
                else self.provider
            )
            if active_provider is harness and self.run_config.strategy in {"investigate", "verified"}:
                llm_context = harness.investigate(llm_context)
            if self.run_config.strategy == "diff":
                llm_context = "Review only the supplied change diff; abstain when missing context.\n" + safe_diff
            review_req = StructuredGenerationRequest(
                run_id=r_id,
                stage="review",
                model_role="review",
                system_instruction=REVIEW_SYSTEM_INSTRUCTION,
                context=llm_context,
            )

            if static_only:
                from schemas.provider import ProviderResponse

                review_resp = ProviderResponse(
                    success=True,
                    model_id="none",
                    data=ReviewCandidatesResult(
                        review_summary="Static review requested; contextual model analysis was skipped"
                    ),
                )
            elif run.review_mode == "project" and self.run_config.strategy != "diff":
                review_resp, project_coverage = review_project(
                    active_provider,
                    r_id,
                    head_files,
                    depth,
                    settings.max_context_tokens * 3,
                    max(1, self.run_config.max_model_calls - harness.calls - 2),
                    REVIEW_SYSTEM_INSTRUCTION,
                    lambda batch, total: self._emit_event(
                        r_id,
                        "stage_progress",
                        {"stage": "gemini_review", "status": "running", "batch": batch, "batches": total},
                    ),
                    deadline_seconds=settings.review_deadline_seconds,
                    supplemental_context=llm_context,
                )
                run.coverage["project_review"] = project_coverage
            else:
                review_resp = active_provider.generate_structured(review_req, ReviewCandidatesResult)
            if review_resp.usage:
                total_usage.prompt_tokens += review_resp.usage.prompt_tokens
                total_usage.candidate_tokens += review_resp.usage.candidate_tokens
                total_usage.total_tokens += review_resp.usage.total_tokens
                total_usage.thought_tokens += review_resp.usage.thought_tokens
                total_usage.cached_content_token_count += review_resp.usage.cached_content_token_count

            llm_findings: list[Finding] = []
            if review_resp.data:
                for cand in review_resp.data.findings:
                    cat_map = {
                        "security": FindingCategory.SECURITY,
                        "bug": FindingCategory.BUG,
                        "style": FindingCategory.STYLE,
                    }
                    sev_map = {
                        "critical": Severity.CRITICAL,
                        "high": Severity.HIGH,
                        "medium": Severity.MEDIUM,
                        "low": Severity.LOW,
                        "info": Severity.INFO,
                    }

                    review_source = "codex_cli_review" if self.run_config.provider == "codex_cli" else "gemini_review"
                    ev = EvidenceItem(
                        kind=review_source,
                        tool_or_profile=review_resp.model_id,
                        output_snippet=cand.trigger_condition or cand.explanation,
                    )

                    f = Finding(
                        run_id=r_id,
                        stable_fingerprint=_make_fingerprint(
                            cand.primary_location.path,
                            cand.rule_id,
                            cand.primary_location.start_line,
                        ),
                        category=cat_map.get(cand.category, FindingCategory.BUG),
                        rule_id=f"proofline:{cand.rule_id}",
                        cwe_id=cand.cwe_id,
                        title=cand.title,
                        explanation=cand.explanation,
                        user_impact=cand.user_impact,
                        severity=sev_map.get(cand.severity, Severity.MEDIUM),
                        primary_location=Location(
                            path=cand.primary_location.path,
                            start_line=cand.primary_location.start_line,
                            end_line=cand.primary_location.end_line,
                            side="head",
                            snippet=cand.primary_location.snippet,
                        ),
                        analysis_sources=[review_source],
                        analysis_status=AnalysisStatus.CONTEXTUAL_ASSESSMENT,
                        reproduction_status=ReproductionStatus.NOT_ATTEMPTED,
                        patch_status=PatchStatus.NOT_REQUESTED,
                        evidence_items=[ev],
                        assumptions=cand.assumptions,
                        limitations=cand.limitations,
                        proposed_remedy=cand.proposed_remedy,
                    )
                    llm_findings.append(f)

            all_findings.extend(llm_findings)
            run.stage_statuses["gemini_review"] = StageStatus.SUCCEEDED if review_resp.success else StageStatus.FAILED
            if static_only:
                run.stage_statuses["gemini_review"] = StageStatus.SKIPPED
            run.coverage["model_review_error"] = review_resp.error if not review_resp.success else None
            run.coverage["review_summary"] = (
                review_resp.data.review_summary
                if review_resp.data and review_resp.data.review_summary
                else "Static-only review: model analysis unavailable"
            )
            self._emit_event(
                r_id,
                "stage_progress",
                {
                    "stage": "gemini_review",
                    "status": run.stage_statuses["gemini_review"].value,
                    "llm_findings": len(llm_findings),
                },
            )

            # ────────────────────────────────────────────────────────
            # STAGE 5: CHALLENGE (Adversarial False-Positive Filter)
            # ────────────────────────────────────────────────────────
            run.stage_statuses["challenge"] = StageStatus.RUNNING
            self._emit_event(r_id, "stage_progress", {"stage": "challenge", "status": "running"})

            # Select findings for challenge (security and high-severity bugs)
            candidates_to_challenge = [
                f for f in all_findings if f.category in (FindingCategory.SECURITY, FindingCategory.BUG)
            ]

            skip_challenge = static_only or self.run_config.strategy != "verified"
            verification = {"complete": True, "requested": 0, "assessed": 0, "unassessed_ids": [], "errors": []}
            if candidates_to_challenge and not skip_challenge:
                verification, challenge_usage = verify_candidates(
                    active_provider,
                    candidates_to_challenge,
                    head_files,
                    r_id,
                    investigator=harness if active_provider is harness else None,
                )
                for field in (
                    "prompt_tokens",
                    "candidate_tokens",
                    "total_tokens",
                    "cached_content_token_count",
                    "thought_tokens",
                ):
                    setattr(total_usage, field, getattr(total_usage, field) + getattr(challenge_usage, field))
                if not verification["complete"]:
                    run.coverage["challenge_error"] = (
                        "; ".join(verification["errors"]) or "Some candidates were not assessed"
                    )
            run.coverage["verification_coverage"] = verification
            run.stage_statuses["challenge"] = (
                StageStatus.SKIPPED
                if skip_challenge
                else (StageStatus.SUCCEEDED if verification["complete"] else StageStatus.FAILED)
            )

            self._emit_event(
                r_id, "stage_progress", {"stage": "challenge", "status": run.stage_statuses["challenge"].value}
            )

            # ────────────────────────────────────────────────────────
            # STAGE 6: VALIDATION & CANONICAL DEDUPE
            # ────────────────────────────────────────────────────────
            run.stage_statuses["validation"] = StageStatus.RUNNING
            self._emit_event(r_id, "stage_progress", {"stage": "validation", "status": "running"})

            rejections = []
            run.coverage["validation_rejections"] = rejections
            validated_findings: list[Finding] = []
            seen_fingerprints: dict[str, Finding] = {}
            file_paths_set = {f["relative_path"] for f in head_files}
            file_line_counts = {f["relative_path"]: f["lines"] for f in head_files}

            for finding in all_findings:
                if excluded(finding.primary_location.path, policy):
                    continue
                # 1. Strict Citation Validation: File must exist
                p_path = finding.primary_location.path
                if p_path not in file_paths_set:
                    rejections.append(
                        {
                            "finding_id": finding.id,
                            "path": p_path,
                            "reason": "Location is outside the reviewed snapshot",
                        }
                    )
                    continue
                matched_file = p_path
                loc = finding.primary_location
                if not (1 <= loc.start_line <= loc.end_line <= file_line_counts[p_path]):
                    rejections.append(
                        {"finding_id": finding.id, "path": p_path, "reason": "Line range is outside the reviewed file"}
                    )
                    continue
                actual = next(f["content"] for f in head_files if f["relative_path"] == p_path)
                if (
                    any(source in finding.analysis_sources for source in ("gemini_review", "codex_cli_review"))
                    and loc.snippet
                    and not snippet_matches_location(loc.snippet, actual, loc.start_line, loc.end_line)
                ):
                    rejections.append(
                        {
                            "finding_id": finding.id,
                            "path": p_path,
                            "reason": "Quotation does not match its cited source range",
                        }
                    )
                    continue

                # 2. Determine Change Relation
                if parsed_diff.files:
                    is_intro = parsed_diff.is_line_introduced(matched_file, finding.primary_location.start_line)
                    finding.change_relation = ChangeRelation.CHANGED_CONTEXT if is_intro else ChangeRelation.UNKNOWN
                else:
                    finding.change_relation = ChangeRelation.UNKNOWN

                if base_files and finding.analysis_sources and finding.analysis_sources[0] in {"ruff", "bandit"}:
                    source_lines = actual.splitlines()
                    key = (finding.rule_id, matched_file, source_lines[loc.start_line - 1].strip())
                    finding.change_relation = (
                        ChangeRelation.PRE_EXISTING if key in baseline_keys else ChangeRelation.INTRODUCED
                    )
                finding.primary_location.commit_sha = run.head_sha
                for evidence in finding.evidence_items:
                    evidence.input_revision = run.head_sha
                finding.stable_fingerprint = stable_identity(finding, repo_map.files, repo_map.symbols)
                # 3. Deduplication by fingerprint
                fp = finding.stable_fingerprint
                if fp in seen_fingerprints:
                    existing = seen_fingerprints[fp]
                    merge_signals(existing, finding)
                else:
                    seen_fingerprints[fp] = finding
                    validated_findings.append(finding)

            validated_findings = consolidate_compiler_findings(consolidate_signature_findings(validated_findings))

            # Sort deterministically: Critical > High > Medium > Low > Info
            severity_order = {
                Severity.CRITICAL: 0,
                Severity.HIGH: 1,
                Severity.MEDIUM: 2,
                Severity.LOW: 3,
                Severity.INFO: 4,
            }
            validated_findings.sort(
                key=lambda f: (
                    severity_order.get(f.severity, 5),
                    0 if f.change_relation == ChangeRelation.INTRODUCED else 1,
                    f.primary_location.path,
                    f.primary_location.start_line,
                )
            )

            # Populate findings count
            counts = {"total": len(validated_findings), "security": 0, "bug": 0, "style": 0}
            for f in validated_findings:
                if f.category == FindingCategory.SECURITY:
                    counts["security"] += 1
                elif f.category == FindingCategory.BUG:
                    counts["bug"] += 1
                elif f.category == FindingCategory.STYLE:
                    counts["style"] += 1
            run.findings_count = counts

            run.coverage["investigation"] = {
                "model_calls": harness.calls,
                "tool_calls": harness.tools,
                "trace": harness.trace,
            }
            run.usage = (harness.usage if active_provider is harness else total_usage).model_dump()
            run.stage_statuses["validation"] = StageStatus.FAILED if rejections else StageStatus.SUCCEEDED
            if (
                any(v.get("status") == "failed" for v in coverage_report.values())
                or js_coverage.get("status") == "failed"
            ):
                run.stage_statuses["static_analysis"] = StageStatus.FAILED
            if r_id in self.cancelled_runs:
                run.status = RunStatus.CANCELLED
            else:
                run.status = (
                    RunStatus.PARTIAL if StageStatus.FAILED in run.stage_statuses.values() else RunStatus.COMPLETED
                )
            run.completed_at = datetime.now(UTC).isoformat()

            self._emit_event(
                r_id,
                "stage_progress",
                {
                    "stage": "validation",
                    "status": run.stage_statuses["validation"].value,
                    "final_findings_count": len(validated_findings),
                },
            )

            return run, validated_findings

        except Exception as exc:
            if harness is not None:
                run.coverage["investigation"] = {
                    "model_calls": harness.calls,
                    "tool_calls": harness.tools,
                    "trace": harness.trace,
                }
                run.usage = harness.usage.model_dump()
            run.status = RunStatus.CANCELLED if r_id in self.cancelled_runs else RunStatus.FAILED
            run.errors.append(str(exc))
            run.completed_at = datetime.now(UTC).isoformat()
            self._emit_event(r_id, "run_failed", {"error": str(exc)})
            return run, all_findings
        finally:
            reset_deadline(deadline_token)
