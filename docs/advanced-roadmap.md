# Active completion checklist

The user authorized completing all phases of the backend advancement plan, including developer workflow and evaluation. The goal is active; the project is not yet complete. Existing tests are regression evidence, not proof of production accuracy.

## Implemented foundations

- A: shared RunConfig, typed request/tool events, call/time/attempt limits; content/config/schema-addressed model checkpoints; immutable ingestion checkpoints; API/UI resume against pinned source without Git refetch.
- B: Python AST call graph and bounded in-memory content cache; JS/TS compiler-parser symbols and selected named-import references; changed-symbol map; bounded ranked lexical context retrieval.
- C: read-only investigation tools and trace with snapshot hashes; separate review and verifier tool loops.
- D: typed source-supported/refuted/insufficient assessment; exact source quotation validation; preserve disputed static evidence; challenge all bug/security candidates rather than silently truncating to six.
- E: trusted Python/Node/TypeScript fixture oracles; base/head/patched differential execution; resource-constrained Docker runner.
- F: repository `.proofline.yml` focus/exclusion/profile guidance (no execution privileges); pinned-SHA publication guard; inline comments restricted to reviewed added lines; UI source/diff/evidence/trace/resume.

## Required work remaining

- Request deadlines, transport retry disabling, explicit retries, quota cooldowns, returned usage accounting and resolved role models are implemented and tested. Remaining: final cross-operation budget audit and sustained-load tests.
- Static analyzer-stage replay now includes content/tool/implementation keys and original-run provenance; pinned source/model/parse checkpoint recovery is implemented. Remaining: complete recovery integration and concurrency audits.
- Persistent parser caches and initial TypeScript alias/re-export/reference/selected type analysis are implemented and tested. Python resolved graph references and added/deleted declarations are now integrated. Default/namespace references and snapshot-supplied external declarations now have explicit tests; a default-export naming defect was corrected. Remaining: broader dependency environments and deeper semantic change mapping.
- Batched verification, reserved assessment budgets, explicit per-candidate coverage, quotation validation and static-evidence preservation are implemented and tested. Remaining: full live challenge and larger-run quality evaluation.
- Operator-profile loading and Python/JS/TS real Docker differential checks are implemented. External operator-profile loading passed real Docker base/head/patched checks. Broader dependency environments still need application-specific validation.
- Initial finding lifecycle, line-movement identity and conservative resolution semantics are implemented and tested. Policy tests, pinned API resume and mocked evidence/repair/profile/resume/mobile UI checks now pass; live GitHub integration remains pending.
- 12 development + 24 heldout authored cases and five-variant runner are implemented; static development run completed. Remaining: independent annotation, public pinned-history cases, full live ablations, and adjudicated quality metrics.
- Live Gemini structured output and tool trajectories now observed; two complete single-case attempts ended partial under transient provider errors. Remaining: a successful full live review/challenge, GitHub authorization/private access and publication; requires reachable services. Do not publish externally without explicit authorization for an actual target.
- Updated architecture, limitations, setup docs and demo package consistent with authoritative implementation.

## Latest verified result

157 backend regression tests passed, one opt-in test skipped. Actual Python/JS/TS and custom-profile Docker checks passed. Next.js 16.4.3 builds, mocked recovery/workflow checks and a real local container walkthrough passed. Local crash/restart, queue saturation and warm repeated reviews passed. Source boundaries and analyzer failure behavior were audited through dogfooding. The authoritative current evidence and remaining acceptance gates are in `completion-audit.md`; older continuation notes below are historical.

## Project-analysis continuation

Virtual TypeScript compiler host resolves snapshot-local modules, root tsconfig aliases and re-exports; selected semantic checks catch argument/return/assignment/nullability problems. Repository-supplied boolean strictness flags are respected. External dependency missing-module diagnostics are not emitted as findings. Python/JS analysis artifacts are cached by implementation, content and runtime/compiler version, with integrity checks and atomic writes. Finding history records new/persisting/resolved-static-rule/not-redetected states and retains dismissals. Tests prove cross-file alias resolution, an argument regression, no invented dependency finding, line-shift continuity and conservative model absence handling.

## Evaluation and execution continuation

Frozen authored corpus and explicit human-adjudication scorer are under `evals/`; no precision/recall score is claimed without adjudication. Static 12-case development report, live successful connectivity, two partial live review reports and successful differential execution results are retained in `evals/results`. Model accounting includes investigation usage. Repository policy for change reviews comes from base to prevent a reviewed PR from weakening exclusions. Docker was started locally and two verification images built; no images were published.

## Runtime and historical evidence continuation

Provider transport retries are disabled in favor of explicit measured retries; request timeouts respect remaining deadlines; returned token metadata from incomplete responses is counted. Per-model quota pacing and provider retry windows defer requests that cannot fit the deadline. The configured account reached a long quota cooldown during live recovery, so full live challenge remains unverified. No repeated calls should be made against that exhausted model until its quota recovers. Three public pinned snapshots were statically reviewed: Werkzeug vulnerable and fixed (272 files each), Requests vulnerable (78 files). Counts are observations, not CVE detection scores. `public-history-v1.json` records advisory URLs, exact vulnerable/fixed commits and platform constraints.

## Verification and integration continuation

Prioritized batches replace the single unbounded challenge request. Missing assessments are recorded explicitly. A custom externally loaded orders verification profile passed actual Docker checks. Independent source citations, configurable model roles, dynamic approved-profile selection and pinned resume passed the browser interaction check; a selector accessibility defect found by the check was corrected. API recovery proves source remains unchanged after original upload mutation. No live Gemini calls were attempted during the known quota cooldown.

## Security and independent-review continuation

The user agreed to independently review the blinded packet. Packet save/export/mobile behavior passed an isolated browser check; no synthetic smoke annotations are used as evaluation evidence. The importer validates hashes, case identities, reviewer presence and disagreement status without rewriting labels or inferring accuracy. Independent export is pending. Source/model/analysis artifact writes now use owner-only atomic files; concurrent write and quota-reservation tests pass. Quota reservations are made atomically across parallel providers. Redaction now covers quoted secret fields, URL userinfo, authorization strings and additional token prefixes; nested tool strings are redacted before JSON escaping, and outbound review publication has a final redaction pass. These are best-effort patterns, not a guarantee of finding every secret.

## Completion audit continuation

`completion-audit.md` now maps the original requirements to inspected source/tests and remaining acceptance evidence. Impact view, whole-project inventory, CLI role/budget settings and pinned CLI recovery are implemented and checked. Runtime events are validated models. Deadlines span ingestion/analyzer/model stages and reset across runs. Initialization/storage failures release worker slots. CI uses a trusted base engine and immutable official Action commits. Both vulnerable/fixed snapshots of Requests and Werkzeug completed static review. The alternate Gemini 3.8 Flash check made four calls and produced an AI finding, but challenge remained partial under overload/deadline failures; it is not a successful full verification result. Application default was not changed. User independent annotation is pending.
