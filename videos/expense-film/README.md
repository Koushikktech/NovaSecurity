# Proofline — Beyond the happy path

The revised Neural Storm film: 120 seconds, 1920×1080, 30 fps, with a quiet credited music bed and no voice-over. Use `NARRATION.md` to record your narration. `UPLOAD-DESCRIPTION.md` includes the required attribution. The previous checkout film remains available in `../proofline-commercial`.

The film follows a multi-file authored expense app: SQL injection causes cross-user expense disclosure; an async `forEach` returns before writes complete. Actual bounded local Codex review found both issues. Separate model patch requests produced the repairs. Protected local SQLite/Python and Node contracts pass on the original, fail on the changed version, and pass on the repaired version.

## Evidence

- `evals/results/expense-story.json`: recorded review, findings, patches and model activity. The initial patch attempts exhausted the review provider's invocation budget; separate fresh bounded patch requests succeeded. The initial errors are retained.
- `evals/results/expense-story-execution.json`: raw subprocess output and return codes for all three versions.
- `evals/results/expense-story-graph.json`: actual Python symbols/imports and resolution limits. This fixture uses dynamic receiver dispatch, so no Python call edges were statically resolved. The film's dashed relationships are source-assessed illustrative links, not an engine-produced taint trace.
- `fixtures/expense-story`: reviewed snapshots, model-repaired snapshot and external protected contracts. Reviewed files contain no vulnerability-label comments or test answers.

The screen cards and report summary are original illustrative graphics. The film does not claim that AI authored the bugs, that it records an uninterrupted app session, or that one case establishes general accuracy. The graph is emphasized as an investigation aid, not a complete taint-analysis engine.

## Reproduce

From this folder, use `npm run check`, then `npm run render -- --quality delivery --fps 30 --output proofline-beyond-happy-path.mp4`. Media and fonts are local. HyperFrames is pinned at 0.9.9.

From repository root, run `PYTHONPATH=backend ../.venv/bin/python scripts/verify-expense-story.py` to repeat execution checks without model calls. `scripts/build-expense-story.py --live` explicitly authorizes a new review and patch generation; it requires the configured local Codex provider and may consume subscription quota. Artifacts reflect the recorded run, not a guarantee that model output will be identical on a rerun.
