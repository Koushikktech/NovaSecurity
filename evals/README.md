# Review evaluation

`pipeline.py` is an ten-case static integration smoke test. `scorer.py` is a legacy snippet heuristic, not a system/model benchmark. Do not cite either as general review accuracy.

## Authored review corpus

`corpus/authored-v1.json` contains 12 development and 24 heldout cases split by issue family. The SHA-256 file freezes the exact version. Cases cover Python, JavaScript and TypeScript with bug/clean pairs. Labels are self-authored and require independent review. Some behavioral expectations require domain assumptions: adjudicators must reject or clarify ambiguous cases before publishing scores. This is not an independent public benchmark, and no accuracy claim is made.

Run the real pipeline, without sending labels to the model:

```sh
PYTHONPATH=backend ../.venv/bin/python evals/review_benchmark.py --variant static --split development --output evals/results/static-development.json
PYTHONPATH=backend ../.venv/bin/python evals/review_benchmark.py --variant verified --split development --limit 1 --output evals/results/live-one.json
```

Variants: `static` (no model), `diff` (diff-only model), `context` (bounded preselected context), `investigate` (tool investigation without challenge), `verified` (investigation plus independent challenge). All use identical deterministic analyzers. Output records raw findings, state, latency, usage and trace. A partial run is not silently treated as a successful complete review. No live variant should be called a production accuracy estimate.

Human adjudication is explicit: JSON rows `{ "finding_id": "...", "issue_id": "expected issue ID or null", "reviewer": "name", "reason": "evidence-based decision" }`. The scorer rejects missing judgments, duplicate rows and a corpus hash mismatch. Additional real bugs require versioning/reannotating the corpus, not counting them as false positives without investigation. Duplicate comments on the same expected issue count as noise.

```sh
../.venv/bin/python evals/adjudicate.py --corpus evals/corpus/authored-v1.json --results evals/results/static-development.json --adjudications judgments.json
```

Metrics include finding-level precision/recall, clean-change false-positive rate, localization and descriptive uncertainty intervals. Raw reports include elapsed time and usage for cost/latency comparisons. Independent human annotations, public pinned-history cases and actual live ablation runs remain required before the evaluation phase is complete. Never tune prompts on heldout cases and then report them as untouched holdout results.

## Public historical cases

`corpus/public-history-v1.json` pins vendor-advisory-backed Requests and Werkzeug cases to vulnerable and fixed SHAs. `public_history.py --case CVE-2024-49766 --revision vulnerable --output results.json` performs static snapshot review without executing project code. Use the corresponding fixed snapshot as a control. The fix commit is a repair, not a newly introduced vulnerability. Werkzeug CVE-2024-49766 applies specifically to older Python on Windows; Linux execution must not be presented as reproduction. Upstream evidence and exact commits are linked in the manifest. Raw static observations exist for both Werkzeug revisions and vulnerable Requests; issue-level quality remains unadjudicated.

## Independent label-review packet

Open `annotation/review.html` in a browser. It shuffles cases and omits original IDs and expected labels. A reviewer records demonstrable issues or uncertainty, with source evidence and assumptions. Progress stays in local browser storage; export creates a JSON file. `annotation/blind-map.json` is kept separately for reconciliation; reviewers should not inspect it while annotating. This packet prepares independent review but does not itself supply independent labels. Cases marked uncertain must be clarified or excluded under a documented protocol before quality claims.

Import an exported independent packet without rewriting existing labels:

```sh
../.venv/bin/python evals/import_annotations.py --annotations /absolute/path/independent-labels.json --output evals/annotation/independent-review.json
```

The importer validates corpus identity and blind-case mapping, records disagreement/uncertainty, and preserves the original corpus. Agreement that an issue exists is not automatically treated as agreement about the same issue: positive cases still need issue-level alignment before model-finding adjudication. Incomplete reviews remain explicitly incomplete. Automated browser smoke exports are synthetic tests and must never be used as independent reviewer evidence.

## Audit comparison workflow

`review_benchmark.py` now accepts `--provider codex_cli|gemini`, `--model`, `--reasoning`, `--max-calls`, `--deadline` and `--resume`. Resume requires the same corpus, variant, split and requested configuration, and skips recorded cases including failures. Native CLI launches are distinct from unobservable internal HTTP retries.

The frozen audit protocol is `results/audit-protocol.json`. Static, diff-only and verified variants share deterministic analyzers. The model receives source, not expected labels. Additional full-workflow compute is recorded rather than assumed free. Heldout outcomes must not be used to tune the frozen run.

`audit_workbench.py --results RESULTS... --output DIRECTORY` prepares explicit alignment and finding-decision templates plus execution metrics. Empty retrieval counts are diagnostic, not proof of a defective query or of missing code. `finding_packet.py --results RESULTS... --output packet.html` creates an offline, variant-blinded finding adjudication UI with source snapshots and local save/export. Do not confuse its judgments with initial blind label review.

For final scoring, supply `adjudicate.py --label-review aligned-labels.json` in addition to results and finding judgments. Label alignment requires the corpus hash, declared builder/independent relationship, complete case coverage, written evidence, confirmed decisions and matching issue IDs. Uncertainty or different ground truth must be resolved and versioned explicitly. Supplied template files contain no completed judgments.
