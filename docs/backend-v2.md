# Advanced backend: current implementation

Proofline remains a single-operator code-review workspace, not a production-equivalent frontier service. The complete active scope and remaining gates are tracked in `advanced-roadmap.md`.

## Review runtime

RunConfig records resolved review/verifier/repair models, thinking settings, selected Gemini API, strategy, attempt limits, model/tool budgets and run deadline. Model transport retries are disabled; explicit application retries, per-call timeouts, provider quota cooldowns and optional proactive RPM pacing are recorded. Returned usage from incomplete output is included. SDK calls are measured; token usage absent from provider errors cannot be reconstructed.

Strategies support evaluation ablations: static, diff-only, selected context, investigation, investigation plus verification. The production default is investigation plus verification. Model calls, tools and execution remain separately bounded. This is a single-worker/threaded runtime, not a distributed job queue.

## Repository understanding

Python AST symbols and resolved call edges feed both initial context and investigation reference tools. JS/TS uses a virtual TypeScript compiler host for snapshot-local modules, path aliases, re-exports, selected semantic diagnostics and resolved calls. External dependency declarations and arbitrary framework builds remain limited. Changed/added symbols and deleted Python/JS/TS declarations are mapped conservatively; dynamic dispatch and shadowing can remain unresolved. Lexical references are explicitly marked as hints.

Python/JS parser artifacts persist under implementation/content/runtime/compiler-version keys. Deterministic analyzer stages are replayable only with matching source, tool versions and implementation. Reused observations retain original-run provenance and receive new finding/evidence IDs.

## Investigation and verification

Read-only tools: source ranges, literal search, symbol lookup, references, related tests and diff. They operate on the sealed inventory, not arbitrary host paths. Tool observations identify the snapshot and are redacted before model context. Project review batches receive investigation observations.

Independent verification prioritizes critical/high findings and processes candidates in batches of four. It reserves final assessment calls within the shared budget and may request its own evidence. Coverage records requested/assessed/unassessed IDs, errors and evidence outcomes. Empty responses or omitted candidates produce incomplete verification, not a silent success.

Assessments distinguish source-supported, refuted and insufficient evidence. Source quotations must match the cited snapshot range; an invalid quotation cannot refute a finding. Model disagreement preserves deterministic tool observations. Source-supported is not execution-proven. The UI exposes citations, uncertainty and verification coverage.

## Recovery and lifecycle

Source checkpoints store base/head inventories, scope metadata, diff and an integrity digest with operator-only file permissions. Resume creates a new run against that sealed source without fetching newer Git state and preserves the prior configuration. It can replay matching deterministic stages and successful typed model responses. It recomputes orchestration and does not resume an interrupted in-flight HTTP request.

Finding identities use path, containing symbol, rule and source line content to tolerate line movement. Comparable reviews track new/persisting findings and preserve dismissals. Missing AI findings are only 'not redetected'; static rules are marked resolved only with completed analyzer coverage and an in-scope source file. Identity is conservative and does not establish arbitrary semantic equivalence across rewritten code.

## Repository policy and GitHub workflow

`.proofline.yml` accepts focus, exclusions and a suggested verification profile; it cannot grant execution privileges. Change reviews use base policy so a PR cannot weaken its own review policy. Exclusions currently suppress findings, not privacy-sensitive source ingestion. Do not use exclusions as a data-sharing boundary.

Publication revalidates the PR head SHA and supports inline comments restricted to added reviewed lines, alongside a summary. Fix publication remains an explicit operator action. Live GitHub authorization/private access/publication still require environment validation; no external comments or PRs were published during development.

## Behavioral execution

Built-in Python, JavaScript and TypeScript contract profiles and an external operator-loaded application profile passed real Docker base/head/patched checks. Source is read-only, network disabled, user non-root, capabilities dropped, and CPU/memory/PID/time limits apply. Images are digest-pinned. The head must fail the designated assertion while unrelated tests pass, and base/patched checks must pass.

Trusted external profiles can configure application-specific oracles and commands in prepared dependency images. Repository or model instructions cannot create execution permissions. Missing dependencies, missing tests, unrelated failures and incomplete reports are inconclusive. See `operator-verification.md`; fixture successes do not establish universal project compatibility.

## Evaluation and known gates

The authored corpus has 12 development and 24 heldout cases, with explicit independent-review requirements. Public vendor-advisory cases pin vulnerable/fixed Requests and Werkzeug commits. Raw observations, latency, usage and traces are retained. No production accuracy is claimed without complete adjudication. Live Gemini structured output and tools worked; final full challenge validation is pending because of provider quota exhaustion. Actual Docker checks passed for all three built-in language fixtures and an external operator-loaded profile.

Latest checks: 170 backend tests passed, one opt-in test skipped; production frontend build and mocked evidence/recovery/mobile browser checks passed. Full goal completion remains unproven until the remaining roadmap gates are satisfied.

Artifact files are now created with owner-only permissions before writing and atomically replaced. Parser/model checkpoints verify payload digests; this detects corruption, not malicious modification by the trusted operator. Quota capacity is reserved under a shared lock across concurrent provider instances. Structured tool observations are recursively redacted before serialization, and outbound review text is redacted before GitHub publication.


## Gemini API compatibility

RunConfig v4 adds `api_mode`: `auto`, `interactions`, or `generate_content`. New auto runs use Interactions for modern models and generateContent for Gemini 2.5. Historic v1–v3 configurations without this field retain generateContent on resume and repair; an explicit override may switch it. API/folder requests, CLI `--api-mode`, UI debug controls, role models, model-cache keys and request activity preserve this selection. Operators may set `PROOFLINE_GEMINI_API_MODE` as their provider default.

Interactions uses JSON Schema, `store=false`, synchronous foreground responses, and `automatic_continuation=false`. No Google-hosted tool execution or automatic continuation is allowed. Only completed responses with valid final JSON pass. Thought content is not shown; returned thought-token counts are recorded separately. Existing deadline, retry, quota and attempt limits apply to either interface. Gemini 2.5 token thinking budgets require generateContent; unsupported combinations are rejected before contacting the provider.

The live four-call Interactions check (`evals/results/live-interactions-review.json`) completed the review stage and returned a finding proposal; investigation and final challenge timed out. This is transport integration evidence, not a successful independent-verification or accuracy result. See Google's [Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview) and [migration guide](https://ai.google.dev/gemini-api/docs/migrate-to-interactions).

Canonical duplicate handling merges only explicitly mapped equivalent rules at the same path, owner, category and source line. It retains analyzer/model signals, evidence and uncertainty. Conflicting verification remains disputed; a model cannot erase a static observation. Lifecycle identity version 2 avoids comparing incompatible historic identities. Request start/completion/checkpoint events retain the same digest identifier.
