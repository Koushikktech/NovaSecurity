# Frozen audit comparison

The three variants reviewed the same 24 authored heldout changes (12 bug/clean pairs). The AI variants used account-discovered GPT-5.6 Sol, high reasoning, one attempt, at most four model requests per case and a 600-second deadline. Static analyzers were shared. Prompts and review logic were frozen before the run; no detector tuning used these outcomes.

## Results on the original 12 target issues

| Variant | Original targets detected | Completion | Duplicate comments | Median / p95 latency |
|---|---:|---|---:|---|
| Static | 2/12 | 24 complete | 0 | 0.16 / 0.88 seconds |
| Static + diff-only AI | 12/12 | 24 complete | 2 | 8.01 / 17.11 seconds |
| Full investigation + challenge | 10/12 | 18 complete; 6 partial | 2 | 17.11 / 42.20 seconds |

The full workflow hit subscription quota near the end. The all-attempt latency statistics include quick quota failures and therefore understate healthy full-review latency. Partial runs were retained; the two target misses must not both be attributed to quota: the dictionary-deletion case completed without a finding, while the monetary-precision case was quota-affected. Assignment mismatch was still found statically despite quota. No claim that the full strategy outperforms the cheaper baseline follows from this experiment.

No comments appeared on the 12 clean changes in these runs. Three full-workflow clean cases were quota-affected, so this is not evidence that all 12 received a complete AI review. This small sample does not establish a production false-positive rate.

## Adjudication provenance

At the user's request, the implementing Codex assistant reviewed the source and returned comments. This is **AI-assisted builder adjudication**, not an independent human benchmark. The supplied human export had missing issue/uncertainty notes and was not silently repaired or credited as independent review. The original corpus, original export and raw inference reports remain unchanged.

The source review identified three valid secondary issues absent from the original labels: non-list iterable input lost by `.sort()`, synchronous task results broken by unconditional `.catch`, and numeric-string inputs lost by the monetary conversion change. `authored-v1-ai-reviewed.json` is a clearly marked post-hoc label extension. All variants are scored against the same extension; source code and model predictions are unchanged. These extended scores are exploratory, not untouched-label results.

| Variant | Extended TP / duplicate-noise FP / FN | Precision penalizing duplicates | Recall |
|---|---|---:|---:|
| Static | 2 / 0 / 13 | 100% (only 2 comments) | 13.3% |
| Diff-only AI | 15 / 2 / 0 | 88.2% | 100% |
| Full workflow | 12 / 2 / 3 | 85.7% | 80.0% |

All FP counts here are redundant comments about already-detected issues, not independently incorrect accusations. Descriptive Wilson intervals, denominators and localization are retained in `evals/results/audit-ai-adjudicated-summary.json`. Families are correlated and sample sizes are small. The full workflow's quota failures make strategy superiority comparisons inappropriate.

## Additional execution evidence

`evals/verify_authored_contracts.py` permits execution only of the exact inspected corpus hash and tests explicit baseline behavior on all 24 heldout changes. Its 48 base/change checks produced the expected outcomes. These are operator-authored contract checks, not Docker sandbox tests or independent labels, and cannot run arbitrary repositories. Examples include empty-input behavior, list return semantics, Promise handling, null handling, zero defaults and monetary truncation.

The original recorded signature example was replayed through conservative consolidation: three comments became two issues while retaining evidence and original model finding identity. See `audit-consolidation-replay.json`; this is deterministic replay, not a new live model result.

## Reproduce and inspect

- Frozen code/config hashes: `evals/results/audit-protocol.json`. The evaluated runner is archived at `evals/results/code-snapshots/review_benchmark.py.txt`; the only later runner maintenance was import ordering, not inference behavior.
- Raw reports: `audit-static-heldout.json`, `audit-diff-heldout.json`, `audit-verified-heldout.json`.
- Label extension and provenance: `evals/corpus/authored-v1-ai-reviewed.json`.
- Written case evidence and finding decisions: `evals/annotation/audit/ai-extended-alignment.json` and `*-ai-adjudications.json`.
- Score views retain original corpus/report hashes and unchanged predictions. Example: `../.venv/bin/python evals/adjudicate.py --corpus evals/corpus/authored-v1-ai-reviewed.json --results evals/results/audit-diff-ai-label-view.json --adjudications evals/annotation/audit/diff-ai-adjudications.json --label-review evals/annotation/audit/ai-extended-alignment.json`.
- Offline variant-blinded finding packet: `evals/annotation/audit/finding-review.html`.

## Remaining limits

Independent human adjudication, a developer time/acceptance study, broad real-project generalization and quota-unaffected strategy comparisons are not established. No volunteer developers are available. Future engine changes need a new untouched test set; these cases are now observed evaluation material.

## Subsequent recovery and validator fix (separate from the frozen comparison)

Model access later recovered. A bounded transport probe succeeded, and all six originally quota-affected cases were retried into `audit-verified-quota-recovery.json`. All six completed. AI-assisted adjudication identified all five extended targets in that subset, with one duplicate assignment comment. These are repeat observations of known cases, not additional untouched holdout cases; the original six partial records remain unchanged.

Investigation of the dictionary-deletion omission found that the model had identified the issue and the challenge pass supported it. The final validator rejected a correctly uniformly dedented multiline snippet. The corrected validator compares against the declared source range and preserves relative indentation; invented text, wrong ranges and changed nesting remain rejected. Pipeline tests cover acceptance and rejection. Source-validation rejections are now recorded, mark the run partial and are visible in Coverage.

A separate live regression retest, `audit-postfix-dict-retest.json`, completed and retained the dictionary finding. This post-fix known-case retest is not substituted into the original 10/12 score. Written AI decisions and score views accompany both subsequent runs. Residual compiler/model duplicate comments remain a documented limitation.

The Codex adapter now stops later requests within the same review after a terminal quota/authentication failure. An explicit new review/provider instance can retry after recovery; no automatic provider switching or global permanent lockout is introduced. Tests prove that a quota failure results in one native invocation even when a later verification role requests work.

A subsequent compiler-duplicate fix recognizes a small explicit set of known TypeScript model rule aliases only when one compiler observation has the same category and exact file/line span. It retains original IDs and evidence. Unknown same-line findings and different locations are not merged. A deterministic post-hoc replay reduces each recorded null/type-assignment pair from two comments to one, stored in `audit-postfix-compiler-replay.json`; the original benchmark scores are not rewritten. Model-only comments about different consequences are retained. This remains conservative fusion, not universal semantic deduplication.

The continuation passes 180 backend regression tests (one opt-in Docker test skipped). New tests include same-run quota stopping, indentation-aware source grounding, partial-status reporting of rejected quotations and conservative compiler alias fusion. The continuation source hashes are recorded separately from the original frozen comparison.

## Unified flagship checkout demonstration

The previous review and execution examples are now complemented by one actual complete authored checkout run: pricing loses its default discount, an unchanged caller fails, the model generates an explicit zero-discount caller edit, and the same trusted Docker oracle produces original pass / changed assertion failure / repaired pass. The explicit-discount happy path stays green. Raw evidence is `evals/results/flagship-checkout.json`, reproducible with `scripts/build-flagship-demo.py --live` and the approved `checkout_contract` profile. The saved `/showcase` UI uses that same run and generated patch throughout six chapters. Its checkout button replays a recorded outcome and is labeled accordingly.

The 120-second silent walkthrough is `videos/checkout-film/checkout-walkthrough.mp4`, built from actual app captures for the user to narrate. It contains no audio and does not pretend to show uninterrupted live model or container execution. Final backend validation passes 181 tests, with one opt-in Docker test skipped; the actual flagship Docker run is recorded separately.
