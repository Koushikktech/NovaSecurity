# Proofline implementation status

Updated 2026-11-01. The authoritative phase audit is [completion-audit.md](completion-audit.md); the active goal is not complete.

## Implemented

- Repository, branch/tag, PR, commit, comparison, folder and CLI working-tree scopes with explicit snapshot metadata.
- Simplified ivory/charcoal/orange workspace: category/severity/search filters, selected finding inspector, source highlights, colored diffs, change impact, independent evidence citations, coverage/test gaps and review history.
- Python Ruff/Bandit/AST graph analysis; JS/TS parser rules, virtual-project selected type checks and compiler-resolved references; persistent content/implementation/tool-version caches.
- Stateless Gemini Interactions and compatible generateContent transport, selectable in API/CLI/UI with historic resume preservation.
- Native Gemini structured review with bounded read tools, independent batched verification, citation checks, explicit uncertainty, model-role settings, measured retries/usage and quota-aware scheduling.
- Shared review deadlines across subprocesses and model calls; API/CLI source-pinned resume and checkpoint replay; worker slot cleanup on initialization and persistence failures.
- Minimal proposed repairs, exact/stale replacement validation, protected oracle paths, patch downloads and explicit GitHub publication.
- Operator-approved Docker execution: digest-pinned images, no network, non-root/read-only/resource limits; base passes, intended head assertion fails, repaired head and happy path pass.
- Repository policy without execution privileges; base-policy protection for change reviews; conservative finding lifecycle; trusted-base static CI workflow with pinned actions.
- Authored 12-development/24-heldout corpus, blinded annotation packet/importer, finding adjudication scorer and advisory-backed public-history cases. No model-quality metric is published without adjudication.

## Verified

170 backend tests passed, one opt-in test skipped. Lint, frontend type/ESLint checks, production build and mocked GitHub/evidence/impact/recovery/mobile browser checks passed. Standalone real Docker checks passed for all three language fixtures and a custom externally registered operator profile. Real Gemini structured output and tool calls succeeded; full challenge runs were partial because of provider errors, quota exhaustion and timeouts. The new Interactions transport completed a live review stage; its challenge timed out and remains explicitly unverified.

## Pending gates and limits

Independent label export and adjudication, full live ablations/challenge, actual GitHub authorization/private access, an authorized publication test and real Actions run remain unverified. Dynamic dispatch, full framework/dependency compilation, arbitrary-project test discovery, production multi-tenancy and general whole-program taint proof are not claimed. Test hints are not measured coverage. Source-based model support is not execution proof. Redaction is best effort and exclusions are not a privacy boundary. See the phase audit for exact evidence and completion conditions.

Latest hardening: source credential/output exclusions with visible reasons; analyzer path normalization, operator-owned configuration, explicit failure coverage and conservative lint categories; browser reducer/reconnect/stale-response protection; bounded same-item publication and uncertain-result reconciliation; private worker results, bounded output/files and DTD rejection. Actual local container and browser checks passed; no public service was deployed.

2026-11-02: Optional localhost Codex CLI provider implemented with native ChatGPT authentication, account model discovery, high reasoning, structured output, bounded/cancellable processes, provider-specific logs and saved configuration. Real transport and complete four-invocation review/challenge passed. See `local-codex.md`.
