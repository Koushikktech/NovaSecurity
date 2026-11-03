# Audit closure evidence

The target is a stronger, assessable submission. A judging score is not an implementation acceptance criterion.

## Implemented repairs

- Exact tool contracts now distinguish symbol lookup, resolved references and literal text search. Natural-language symbol questions return an error and bounded snapshot symbol suggestions. Qualified `path::name` lookup is supported. Investigation instructions describe actual tool semantics.
- Changed-signature model comments consolidate only when they cite the deterministic caller site and its callee and match one compatible anchor. Original model finding IDs, assessments and evidence are retained. Separate call sites remain separate repair work.
- Standard frontend lint excludes generated `.next-*` builds.
- Benchmark CLI supports explicit Codex/Gemini selection, model, reasoning, call/deadline budgets and configuration-checked resume. Source files retain nested paths. Incremental reports retain completed work.
- Human alignment validates the corpus hash, reviewer relationship, complete case coverage, written evidence and expected issue IDs. Findings still require separate explicit human adjudication.
- `evals/audit_workbench.py` prepares alignment/adjudication templates and execution summaries without inventing judgments. The scorer reports duplicate noise and review completion states.

## Current evidence and limits

The 24-case static heldout run completed. Its raw output is `evals/results/audit-static-heldout.json`; it has not been independently scored.

The supplied `Downloads/independent-labels.json` contains 36 verdicts: 12 issue, 22 clean and 2 uncertain. All 14 issue/uncertain entries lack required evidence notes. The importer rejected it rather than quietly treating those verdicts as validated ground truth. The original export and existing blinded packet were preserved. Reviewer relationship also requires clarification.

No volunteer developers are available, as confirmed by the user. Measured developer time savings and independent acceptance remain unproven. No simulated users or AI judgments will be labeled human research.

## Human handoff

1. Complete evidence notes in the existing blinded packet and export again.
2. Identify whether its reviewer built the project.
3. Import using `evals/import_annotations.py`.
4. Resolve uncertainty/disagreement and fill `evals/annotation/audit/label-alignment.template.json` with actual issue-level judgments. Changes to ground truth require versioning rather than editing the frozen corpus in place.
5. Fill finding adjudications for each result. Run `evals/adjudicate.py --corpus ... --results ... --adjudications ... --label-review ...`.
6. Report all completion states, duplicate comments, quality denominators, latency and usage. Failures remain in coverage reporting.

## Completed offline adjudication and comparison

The user explicitly requested that Codex do the annotations. AI-assisted builder evidence was written separately, imported successfully for all 36 cases, and used for transparent preliminary finding adjudication. This does not convert the original incomplete human export into independent evidence. See `audit-results.md` for the completed 72 case/configuration attempts, post-hoc secondary-label extension, preserved quota failures, residual duplicates and actual contract checks. Live inference stopped when the subscription limit was reached. No time-saving or independent accuracy claim is made.
