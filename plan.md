# Proofline — executable engineering and submission plan

Status: implementation specification, not a claim that these capabilities already exist.
Prepared: 2026-10-31. Event timezone: Asia/Kolkata (IST).
Canonical plan: this file. Existing source: `./NovaSecurity/` relative to this file.
If this file is moved into the repository, treat the directory containing `backend/` and `frontend/` as the project root.

## 0. Instructions to the implementing AI

Build **Proofline**, a Python-first, evidence-backed pull-request reviewer using the **Google Gemini API**. Evolve the existing repository; do not discard functioning infrastructure or build a disconnected replacement. This is a new hackathon submission, not an Amazon Nova project.

Read this entire plan and applicable AGENTS.md files before changing code. Inspect the current checkout and user changes; the audit below is a starting point, not permission to overwrite subsequent work. Implement in milestone order. Maintain `docs/implementation-status.md` with requirements completed, verification commands, actual results, limitations, and next actions. Do not mark functionality complete because a button, mock response, or prompt exists.

The user wants exceptional technical implementation and real usability. Translate that into reproducible correctness, useful context, reliable integrations, and clear evidence—not agent count, inflated claims, or unnecessary infrastructure. No score or placement is guaranteed.

Implementation rules:

- Reuse the current checkout. Do not rewrite Git history, delete attribution, rename the remote GitHub repository, or move the physical checkout as part of a branding change.
- Implement the rename throughout active application code, configuration, docs, package metadata, UI, and generated content. Keep historical Git objects and legally required attribution intact.
- Use Gemini for all new live LLM work. Do not silently fall back to the previous provider or replay fixtures as live output.
- Do not ask the user to choose routine architecture details already specified here. Missing credentials block only live integration checks; implement and test adapters with explicit fakes while waiting for credentials.
- Do not fabricate credentials, benchmark numbers, user testimonials, execution logs, deployment links, or successful verification.
- Source code, repository comments, uploaded files, and model output are untrusted data. They cannot authorize shell commands, network requests, publishing, or reading host secrets.
- Runtime verification is restricted to approved test profiles in an isolated worker. The model cannot invent executable shell commands for the host.
- Creating patches is separate from publishing them. Never automatically merge, push to a user branch, or post a review without an explicit UI action/authorized CI policy.
- Do not deploy publicly, publish a GitHub review, or change repository settings merely because this plan describes those deliverables. Prepare and test locally; use the user's existing authorization or obtain any needed final approval for external changes.
- A feature is complete only when its behavior, failure path, and integration are verified. Update documentation to match actual behavior.
- Preserve a working vertical slice at every milestone. If time runs short, cut P2 first, then optional P1 items. Never cut truthful evidence states or isolation to preserve spectacle.

## 1. Context, event requirements, and success criteria

### Hackathon

- Event: **Neural Storm 2026**, November 2–4, 2026.
- Track: Future Tech. Statement: **FT-05 — AI-Powered Automated Code Review**.
- Official task: analyze repositories for bugs, security vulnerabilities, and style issues with context-aware suggestions.
- Python must be the primary AI/ML language. A TypeScript frontend is acceptable.
- User reports organizer permission to begin early. Treat that as given; do not misrepresent when work was done.
- Submission opens November 2 at 20:00 IST; closes November 4 at 20:00 IST. Target upload by November 4 at 18:00 IST.
- Public repository required; deployment strongly recommended; one submission per team, editable before deadline.
- README must contain title/statement number, team/member names, problem/approach, stack, setup, local run instructions, screenshots/GIF, performance results where applicable, and AI-tool disclosure.
- Supplied awards: winner INR 10,000; first runner-up INR 5,000; second runner-up INR 3,000; third runner-up INR 2,000; certificates. No confirmed special or track-specific awards.
- Registrations estimated by user at 150–170 teams. Do not infer winning odds from this.
- Brief source on original machine: `/Users/koushikk/Downloads/Neural Strom.pdf`.

### Actual judging rubric

| Criterion | Weight | Required evidence in this implementation |
|---|---:|---|
| Technical implementation | 35% | Real PR ingestion; contextual analysis; typed pipeline; independent verification; tests; measured accuracy and reliability |
| Impact and usefulness | 25% | Developer workflow; low-noise findings; actionable patches; CI; real user feedback if available |
| README and documentation | 20% | Fresh-clone setup; architecture; reproducible results; screenshots; limitations |
| Demo and presentation | 20% | Stable deployed/recorded experience; clear before/after; exact revisions; honest fallback |

### Product definition

**Proofline: review the change, inspect the evidence, verify the repair.**

Primary user: a developer reviewing a Python pull request in a small team without a dedicated security reviewer.
Primary workflow: paste PR URL → inspect prioritized findings → inspect evidence and code context → generate a minimal patch → run approved checks → export/publish after review.

Hero demonstration: a realistic small API PR introduces a cross-file flaw. Proofline identifies it, cites relevant functions, reproduces the incorrect behavior using an independent regression test, proposes a patch, shows the same test passing while ordinary behavior remains intact, and prepares a GitHub review. A safe counterpart produces no unnecessary warning. Bug, security, and style categories are all visible.

Do not position Proofline as proving an entire repository secure, replacing humans, or outperforming commercial tools without direct evidence. A successful test proves only the behavior and environment exercised.

## 2. Existing project audit and migration inventory

Baseline reviewed: `a4511e38ffacb122a309cd1ecee9a2736eab00fa` in `Koushikktech/NovaSecurity`.
Stack: FastAPI, Python, LangGraph, tree-sitter-python, NetworkX, GitPython; Next.js 16 / React 19 / TypeScript / Tailwind; optional Supabase. Verify current versions before installation and use committed lockfiles.

### Preserve and evolve

- `backend/api.py`: REST/SSE integration and existing state transitions; split into smaller services/routes as needed.
- `backend/indexer.py`: Python symbol extraction, prioritization, context formatting.
- `backend/graph.py`: candidate call/source/sink relationships; do not treat current paths as proven taint flow.
- `backend/agent.py`: orchestration and targeted/indexed analysis concepts.
- `backend/remediation.py`: isolated edit workspace, allowed-path checks, diff generation.
- `frontend/app/components/report/`: finding cards and diff viewer.
- Existing frontend hooks: retain useful lifecycle behavior, fix cancellation/stale-response issues through tests.
- Existing demo fixtures: quarantine as legacy artifacts until reproduced; never present as Gemini runs.

### Confirmed defects/limitations to address

1. Graph connects inputs to functions and functions to sinks, without establishing argument-level propagation. Four direct graph probes all produced unsanitized paths: constant SQL unrelated to input; parameterized SQL; escaped value in a constant template; genuinely concatenated SQL. These probes did not run the final LLM scanner.
2. Sanitizer nodes are outgoing function edges, not reliable value-flow transforms; broad names such as `clean`, `encode`, and `validate` are not universal sanitizers.
3. Cross-file lookup uses bare function names and can collide across modules/classes. Nested scopes and import aliases need qualified identities.
4. Red-team success comes from a model `exploit_feasible` boolean, not actual execution.
5. Hand-weighted confidence reaches the old “Confirmed” threshold at 0.60 with LLM confidence 0.5, targeted-scan membership, no exploit success, and no defense dispute. Skipped/failed defensive analysis incorrectly contributes positive confidence.
6. `api.py` selects `after_validation or all_findings`; an intentionally empty filtered result resurrects rejected findings.
7. Remediation commits generated code and stores `tests_to_run`; it does not execute those checks before claiming completion.
8. Ingestion accepts a repository URL, not incoming PR/base/head semantics. Creating a remediation PR is not PR review support.
9. Python gets AST analysis; other languages receive generic metadata. Some reasoning stages receive only Python files, even for non-Python findings.
10. Clone directories use repository basename and delete existing paths, causing same-name/concurrent-job collisions.
11. Jobs use in-memory dictionaries/threads; restarts lose active state and unrestricted submissions can multiply workers.
12. Repository URL checks are broad; clone/read size, destination restrictions, symlinks, secrets, and execution boundaries need hardening.
13. Provider logging uses thread-local storage and misses complete cross-worker usage aggregation.
14. Provider model configuration is inconsistent between hardcoded and environment-based stages.
15. Model call exhaustion may look like no findings unless stage failure is explicitly propagated.
16. README claims compiler-grade taint tracking, proven exploitation, a force-directed graph, Git worktrees, and very fast scans beyond established implementation/evidence. Current workspace preparation copies the repository. Current report code exposes graph counts rather than the advertised graph UI.
17. No dedicated automated test/evaluation suite was found in the audited checkout. Recheck before adding replacements.

## 3. Branding and complete Gemini migration [P0]

### New identity

- Product: **Proofline**. Technical slug: `proofline`.
- Title: `Proofline | Evidence-backed AI Code Review`.
- Tagline: `Review the change. Verify the repair.`
- Repository display title: `Proofline — Neural Storm 2026 / FT-05`.
- Name is a working product identity, not a claim of trademark/domain availability.
- Design: precise developer tool; readable code, restrained colors, obvious evidence. Avoid theatrical hacker copy and long simulated terminal sequences.

### Rename checklist

- [ ] Remove NovaSecurity, NovaGuard, Amazon Nova, Bedrock and old sponsor/hackathon positioning from active product surfaces.
- [ ] Rename `backend/nova.py` to provider-neutral `backend/providers/gemini.py` or equivalent package module; update all imports.
- [ ] Replace `nova_call*`, `NOVA_*`, old model IDs, API URLs, placeholder API keys, old branch prefixes, backend title, console messages, package names, metadata, prompts, favicon/wordmark text, local-storage keys, screenshots and sample responses.
- [ ] Use `proofline/fix/<short-id>` for generated branches.
- [ ] Remove the OpenAI SDK if no longer used. Add the official **`google-genai`** Python SDK and pin the tested version in lockfiles. Do not use the deprecated older Gemini SDK or an OpenAI compatibility layer for this migration.
- [ ] Update `.env.example`, README, backend README, frontend README, scripts, deployment manifests, and tests together.
- [ ] Replace/re-record legacy fixtures with Gemini provenance. If retained for regression comparison, label them legacy and exclude from public default demos.
- [ ] Search tracked active text for `NovaSecurity|NovaGuard|Amazon|Bedrock|NOVA_|nova_call|api.nova|nova-2|nova/`; inspect each hit. This plan, migration notes, actual historical repository URLs, Git history, and legal attribution are permitted exceptions, not active product branding.
- [ ] Preserve Git remote and physical `NovaSecurity/` folder unless user separately requests renaming them.

### Provider contract

Implement a narrow provider interface so orchestration never knows vendor-specific response objects:

```python
class StructuredGenerationRequest(BaseModel):
    run_id: UUID
    stage: str
    model_role: Literal['review', 'verify_reasoning', 'patch']
    system_instruction: str
    context: str
    schema_version: str
    deadline_ms: int
    max_output_tokens: int

# Response contains validated domain data plus model, request ID if available,
# usage, timing, retries, finish reason, and an explicit error/abstention status.
# Schema type is supplied to the adapter, not serialized as arbitrary Python code.
```

Use `from google import genai` and the current documented structured-output API supported by the pinned SDK/model. Validate returned JSON again with Pydantic. Unsupported schema shapes, truncated output, blocked output, empty candidates, malformed JSON, and timeout are explicit typed failures. One bounded schema retry is acceptable; regex extraction must not convert arbitrary prose into a trusted successful review.

Do not blindly copy old API syntax: Google's current quickstart and model catalog evolve. At implementation time inspect official docs, choose one supported API surface, pin the SDK, and prove the actual response extraction with an opt-in live smoke test. No speculative SDK methods. Prefer simple non-agentic structured generation over provider-managed autonomous agents.

### Model selection and configuration

No model ID is assumed valid forever. List/verify available text models with the user's key where supported, check structured-output support, then select a stable cost-effective model for default review. Use a stronger configured model only for bounded escalation or patches if measured benefit justifies it. A single model for all roles is an acceptable initial implementation.

```dotenv
GEMINI_API_KEY=                        # server only; never NEXT_PUBLIC_*
PROOFLINE_GEMINI_REVIEW_MODEL=          # required for live mode; verified model ID
PROOFLINE_GEMINI_PATCH_MODEL=           # defaults to review model
PROOFLINE_GEMINI_REASONING_MODEL=       # defaults to review model
PROOFLINE_LLM_MAX_CONCURRENCY=2
PROOFLINE_LLM_REQUEST_TIMEOUT_SECONDS=45
PROOFLINE_REVIEW_DEADLINE_SECONDS=180
PROOFLINE_LLM_MAX_ATTEMPTS=3
PROOFLINE_MAX_MODEL_CALLS_PER_RUN=12
PROOFLINE_MAX_OUTPUT_TOKENS=4096
PROOFLINE_MAX_CONTEXT_TOKENS=24000
PROOFLINE_DATABASE_URL=sqlite:///./data/proofline.db
PROOFLINE_ARTIFACT_DIR=./data/artifacts
PROOFLINE_WORKSPACE_DIR=./data/workspaces
PROOFLINE_ALLOWED_ORIGINS=http://localhost:3000
PROOFLINE_EXECUTION_ENABLED=false
PROOFLINE_GITHUB_PUBLISH_ENABLED=false
GITHUB_TOKEN=                          # local/controlled integration only
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Values above are application budgets, not claims about Gemini service quotas. Validate them at startup; expose sanitized capabilities, never secrets. Fail live preflight if key/model missing; still allow recorded examples and static-only mode labeled correctly.

- Global semaphore/token budget across jobs, not just per-review worker pools.
- Bounded jittered exponential backoff on retryable errors; honor server guidance when present. Do not retry invalid credentials or unsupported models repeatedly.
- Account for SDK automatic retries; avoid multiplicative retry loops that violate deadlines.
- Track stage-level input/output usage, cache usage if supplied, model ID, prompt version, retries, and wall time. Cost is estimated only when a dated price configuration exists; otherwise show tokens and “cost unavailable.”
- Reasoning summaries are concise user-facing evidence explanations, not hidden chain-of-thought transcripts.
- Request-scoped aggregation replaces thread-local call logs.
- Cache validated results by tenant, repo revision, content/context hashes, rules/config hash, model ID, prompt/schema versions. No cross-user private-code cache sharing.
- Cache hits and replay artifacts are visible; they do not count as fresh inference latency in evaluation.
- Context caching, batch APIs, streaming structured output, and multi-model routing are optional optimization, never baseline dependencies.

Official references, checked during planning; recheck for implementation:

- https://ai.google.dev/gemini-api/docs/quickstart
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/troubleshooting

## 4. Scope and priorities

### P0: required integrated submission

Python-first repo/PR review; bug/security/style categories; deterministic analyzers; qualified cross-file context; honest evidence; minimal patches; isolated execution for approved demo profiles; GitHub review preparation/publication controls; stable web UI; CI/CLI; persisted reports; meaningful tests/evaluation; Gemini migration; complete documentation/demo.

### P1: add after the core gates pass

GitHub App installation/webhooks; stronger changed-symbol impact traversal; reusable suppression/config policy; annotated evidence-path UI; mutation/metamorphic evaluation; controlled user study; JS/TS static checks with explicit limits; SARIF where useful; selective model escalation justified by ablation.

### P2: future roadmap, not submission blockers

General Java/Go/Rust semantics, VS Code extension, enterprise multi-tenancy, billing, full-program custom taint compiler, arbitrary-repository autonomous execution, agent swarms, vector DB migration, Kubernetes, automatic merging, enterprise compliance claims.

Do not build a partial P2 feature while a P0 workflow is broken. P0 is the target plan, not permission to claim all work is feasible within remaining time; milestone gates govern scope reduction.

## 5. Target architecture

```text
Next.js review workspace
        | typed REST + resumable SSE
FastAPI routes / auth / validation
        | persisted job + event records
Bounded Python review worker
        |
        +-- GitHub metadata -> immutable base/head snapshots -> parsed diff
        +-- repository inventory -> qualified symbols + import/call context
        +-- Ruff + Bandit + selected pinned Semgrep rules
        +-- candidate normalization -> relevant context selection
        +-- Gemini structured contextual review / challenge
        +-- deterministic validation -> dedupe -> evidence + relevance ranking
        +-- persisted report + coverage + usage + export
        |
        +-- user requests patch -> structured edits -> isolated workspace
                  -> approved test worker -> immutable validation artifacts
                  -> preview/download -> separately authorized GitHub publish
```

Keep FastAPI and Next.js. Keep LangGraph only if it simplifies typed stage composition and partial failure; do not add another agent framework. Start with SQLite WAL and a single bounded worker process for hackathon deployment; atomic DB job claiming, leases/heartbeats and status recovery are required. A single web process may host the bounded worker initially, provided lifecycle/restart behavior is explicit. Use PostgreSQL/queue infrastructure only if deployment truly needs multiple instances.

Proposed organization (adapt import/package conventions to avoid breaking startup):

```text
backend/
  main.py
  api/                       # routes, auth, serialization, error mapping
  config.py
  schemas/                   # findings, runs, evidence, patches, provider contracts
  providers/gemini.py
  ingestion/                 # GitHub API, URL checks, snapshots, diff parser
  analysis/                  # static adapters, index, impact context, normalization
  review/                    # orchestration, prompts, ranking, dedupe, provenance
  verification/              # profile registry, runner protocol, results
  remediation/               # patch proposal/application, validation, publish
  persistence/               # models, migrations, jobs, event log
  cli.py
  tests/
frontend/app/
  components/review/          # summary, diff, evidence, patch, coverage
  hooks/
  lib/                       # generated API types/client, reducers
evals/                       # manifests, labeled cases, scorer, raw run artifacts
fixtures/demo-api/           # controlled Python app and review scenarios
verification/profiles/       # trusted profiles; not read from scanned PRs
docs/
scripts/
.github/workflows/
compose.yaml
Makefile
```

Avoid a disruptive directory rewrite before the first working slice. Extract one service at a time with compatibility imports/routes where useful, then remove obsolete code.

## 6. Domain contracts and evidence semantics

Use Pydantic models, enums and versioned JSON schemas. Generate frontend types from OpenAPI or a deterministic schema export; check drift in CI. UUIDs identify resources; IDs do not substitute for authorization.

### ReviewRun

Required fields: ID; owner/session; input mode (`repo`, `pr`, `local_diff`, `recorded`); canonical repository; PR number if applicable; base SHA/head SHA and merge-base SHA; configuration/ruleset/prompt/schema versions; provider/model IDs; timestamps; status; stage statuses; coverage; usage; artifact references; previous-run ID; error list.

Run states: `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`, `interrupted`. “Completed” means scheduled supported stages completed, not “repository is safe.” Stage states: `pending`, `running`, `succeeded`, `failed`, `skipped`, `cancelled`. Include skip/failure reason and affected coverage.

### Finding

```text
id, run_id, stable_fingerprint, category: security|bug|style
rule_id, optional CWE, title, explanation, user_impact
severity: critical|high|medium|low|info
primary_location: {path, start_line, end_line, side, commit_sha}
related_locations: [{path, lines, qualified_symbol, relationship}]
change_relation: introduced|pre_existing|changed_context|resolved|unknown
evidence_refs[], analysis_sources[], assumptions[], limitations[]
disposition: open|dismissed|accepted|fixed|superseded
verification_status, fixability, optional patch_id
```

No model-generated absolute paths. Validate each path against the snapshot inventory, line range against the exact file, and snippet against the real contents. Reject invalid citations or mark missing evidence; never silently substitute a different file or path index.

### Evidence and verification

Represent independent dimensions rather than one deceptive confidence score:

- `analysis_status`: static_match, contextual_assessment, disputed, insufficient_context.
- `reproduction_status`: not_attempted, reproduced, not_reproduced, inconclusive, unavailable, failed.
- `patch_status`: not_requested, proposed, applying, validation_running, checks_passed, checks_failed, inconclusive, stale.
- Evidence items: tool/rule or test profile; exact input revision; command/profile ID; environment/image digest; exit code; stdout/stderr artifact hashes; duration; originating stage; relevant source excerpts.

“Reproduced” requires an executed behavioral check with interpretable output. “Checks passed” requires recorded checks and names their scope. A generated PoC or model agreement is only contextual assessment. Timeout/missing dependencies are inconclusive, not “not vulnerable.” A negative reproduction result does not prove absence.

Do not expose hand-weighted scores as probabilities. Rank deterministically by user impact/severity, PR relevance, evidence strength and actionability. Keep style separate and nonblocking by default. Avoid auto-blocking a PR based solely on LLM opinion.

### Dedupe and suppression

- Normalize canonical issue types across analyzers; retain all evidence sources.
- Fingerprint normalized path, rule/CWE, qualified symbol and relevant code structure. Preserve identity through ordinary line shifts; changes to vulnerable code should invalidate inappropriate suppressions.
- Collapse duplicate reports of the same root cause while keeping distinct sinks/behaviors when actionable.
- Suppression records include reason, scope, creator, timestamp, optional expiry, and affected rule/fingerprint. Make suppressed findings inspectable.
- Disposition updates are versioned and authorized. No claim of learning from feedback until learning is actually implemented/evaluated.

## 7. Repository and PR ingestion [P0]

### Public GitHub first

Accept canonical HTTPS GitHub repository URLs and `/pull/<number>` URLs. Parse with a URL parser and explicit host/path validation. Reject embedded credentials, unsupported protocols, local paths, private network destinations, arbitrary redirects and internal clone endpoints. Use GitHub APIs to resolve repository and PR metadata; never interpolate remote strings into shell commands.

Pin immutable snapshots. For a PR use its base/head identities and merge-base semantics, supporting fork heads via resolved repository identities. Fetch required commits with bounded depth and a controlled fallback if merge base is unavailable. Record exact revisions in artifacts. Handle deleted branches and permission errors visibly.

Diff parser must handle added/deleted files, renames, multiple hunks, line insertions/deletions, missing trailing newline, binary changes, and files with no commentable hunk. Do not naïvely use new-file line numbers for removed lines. Truncation and omitted API files must be detected through pagination/limits and reflected in coverage.

### Isolation and limits

- Unique workspace per run, not basename. No cleanup of another active job's directory.
- Ignore `.git`, vendored dependencies, binaries, build output and generated/minified assets by policy. Record exclusions.
- Initial configurable limits: 100 changed files, 5,000 changed lines, 500 KiB text per file, 20 MiB total selected source, 60-second clone/fetch deadline. Document these as product limits, not security guarantees.
- No symlink traversal outside snapshot; reject dangerous relative paths and case/path collisions. Do not follow submodules or LFS downloads automatically.
- Clone/read does not execute repository hooks, setup scripts, package managers, Makefiles, or tests.
- Redact detected secret values before model submission and public artifacts; record only redacted evidence for secret findings.
- Use subprocess argument arrays, disable prompts, constrain Git config/protocols, terminate timed-out process groups.
- Cancellation cleans resources after workers stop; TTL cleanup is lease-aware and idempotent.

### PR relevance

Analyze changed functions plus bounded dependencies. To classify introduced/pre-existing, compare supported detector results on base and head and their context; do not classify solely by whether a line is inside a hunk. If baseline was not evaluated or context differs ambiguously, use `unknown`/`changed_context` rather than invent certainty.

## 8. Analysis and cross-file reasoning [P0/P1]

### Static adapters

- Ruff JSON output for style and selected bug rules; honor declarative configuration without executing project code.
- Bandit JSON for supported Python security candidates.
- Selected Semgrep Python rules pinned locally and licensed/attributed. Add only measured useful coverage; avoid downloading an unbounded remote rule catalog during the demo.
- Normalize all outputs to shared findings. Preserve tool versions, rulesets, severities and raw artifact references. Tool absence/failure is a coverage failure, not empty findings.
- Ruff fix suggestions must be labeled safe/unsafe according to the tool; never apply unsafe fixes silently.
- Add dependency/secret scanning only as P1 when core bug/security review is reliable. Never submit raw secrets to Gemini.

### Supported semantic cases

Build tests and honest adapters for SQL injection, command construction, path traversal, dangerous dynamic code/template use, mutable default state, boundary/empty-input errors, and selected exception-handling problems. Use one framework deeply (Flask recommended for the initial demo). Do not assert framework-wide coverage.

### Qualified context graph

- Symbol ID: module + lexical class/function scope + definition location; distinguish same-name methods/functions.
- Resolve explicit imports/aliases and straightforward call targets. Represent unresolved/dynamic calls as unresolved; do not connect by a matching last name alone.
- Use graph edges as context evidence (`imports`, `calls`, `reads_config`, `tested_by`) unless true data-flow semantics were implemented and tested.
- Select changed function, callers/callees within one/two hops, relevant configuration and existing tests. Stable deterministic ordering and token budgets.
- Add a small evidence path view: request handler → helper → sink, with each step opening actual code. Label inferred edges and unresolved links.
- Handle sanitizers per sink: SQL parameter binding differs from HTML escaping, shell argument handling, and path containment. A function called `sanitize` is not evidence by itself.
- Cache parse/index results by blob SHA and parser version; incremental invalidation must include dependent context when signatures/imports change.
- P1: bounded variable/argument summaries for a few supported patterns; no claim of general interprocedural taint analysis.

### Gemini review stages

1. Generate/contextualize candidates using diff, deterministic evidence and relevant code.
2. Challenge only high-impact or ambiguous candidates, looking for guards, parameterization, framework behavior and contradicting tests.
3. Validate references and normalize output deterministically.
4. Rank and dedupe.

Use independent evidence, not a fictional voting system. Two prompts to the same model are correlated judgments. Show assumptions and uncertainty. Prompt versioning and bounded context are mandatory; embeddings/vector storage are not mandatory when symbol retrieval is sufficient.

Prompt output must include category, concrete triggering condition, causal explanation, affected behavior, exact code citations, proposed remedy and limitations. Avoid generic “add error handling” advice. Repo-provided instructions may inform coding conventions only through a constrained declarative policy; they cannot change system policy or execution permissions.

## 9. Verified repair loop [P0 flagship]

### Patch generation

- User selects one actionable finding. Pin source head SHA and finding fingerprint.
- Gather relevant complete functions plus essential imports/tests within budget.
- Gemini returns typed edits with path, expected old content/hash, replacement and concise rationale. No shell scripts or arbitrary file operations.
- Enforce file allowlist, bounded changed lines, no binaries, no path escape/symlink escape, no secrets, no CI permission edits, and no edits to protected verification tests/config.
- Apply atomically to an isolated branch/workspace. If source content differs, mark stale; do not fuzzily apply against unrelated code.
- Run syntax/parse, relevant lint and approved behavioral checks. Compute a real Git diff from actual resulting files.
- Whole-file output is a fallback only with exact input hash and strict scope/diff-size validation.
- No-op patch is a visible failure. Partial application is rolled back.

### Controlled execution architecture

The public API process must not execute arbitrary repository code. Verification runs only in a separate isolated worker on an allowlisted fixture/profile for the initial release. Unknown repositories get review and patch export with `verification unavailable`.

Trusted profile fields: profile ID/version; approved repository/revision constraints; prebuilt image digest; dependency lock hash; command argument arrays; timeout; CPU/memory/PID/output limits; expected test identifiers; artifact parser. Profiles live outside analyzed PR contents and cannot be modified by a model or PR author.

Runner requirements:

- Non-root, no host credentials, no cloud metadata access, no outbound network during execution, no privileged mode, no Docker socket mount.
- Read-only container root where practical, dedicated writable temporary directories, strict workspace mount, dropped capabilities and default seccomp or stronger isolation available on host.
- CPU/memory/PID limits; wall-time timeout; terminate process tree; cap logs; clean up after cancellation.
- Dependencies installed only while building a trusted profile image, not from arbitrary PR installation hooks at execution time.
- Container access/control remains in a trusted runner service, never exposed to the untrusted test container or browser/API caller.
- If isolation cannot be provisioned, disable execution and retain static/recorded demonstration. Do not quietly run on the host.

### Verification protocol

Use the same independently specified test oracle on the buggy head and patched head. For a correctness regression test, expected behavior is red before / green after. Also run relevant pre-existing tests and a positive-control happy path. Capture collection count: zero tests collected is not success.

First confirm the intended failure before patching. Infrastructure failure, missing import/dependency or timeout is not a reproduced bug. After patching, require the intended assertion to pass, no newly failing relevant tests, and artifact provenance. Tests generated by Gemini are proposals requiring validation; existing/hand-reviewed protected tests have stronger evidentiary status.

Suggested demo: Flask expense-service search crosses `routes/search.py` → `services/search.py` → `repositories/expenses.py`, where the PR replaces parameter binding with unsafe query construction. A protected in-process test proves unauthorized rows are returned before the fix and not afterward, while valid searches still work. Use disposable synthetic data; no network attack against a live service.

Add a separate ordinary bug such as mutable default accumulation and a Ruff style finding. Do not classify every correctness bug as critical security.

### Publishing

Prepare a downloadable `.patch` and Markdown report regardless of credentials. A separate explicit action can create a fix branch/PR or a review. Show repository, target branch, reviewed SHA, exact content and requested operation first. Recheck source SHA immediately before publication. Retry idempotently; never duplicate comments/PRs. Never auto-merge.

## 10. API, jobs, persistence, and observability [P0]

Suggested versioned endpoints:

| Endpoint | Behavior |
|---|---|
| `GET /healthz` | Process health only |
| `GET /readyz` | DB/worker capability; no paid request on every probe |
| `GET /api/v1/capabilities` | Supported languages, modes, verification profiles, sanitized live availability |
| `POST /api/v1/reviews` | Validated repo/PR/local-diff submission; idempotency key; 202 + run ID |
| `GET /api/v1/reviews/{id}` | Status, scope, summary, coverage |
| `GET /api/v1/reviews/{id}/events` | SSE with monotonically increasing event IDs and reconnection |
| `POST /api/v1/reviews/{id}/cancel` | Cooperative cancellation, persisted result |
| `GET /api/v1/reviews/{id}/findings` | Filterable/paginated findings |
| `GET /api/v1/reviews/{id}/evidence/{evidence_id}` | Authorized bounded evidence access |
| `PATCH /api/v1/findings/{id}/disposition` | Dismiss/accept with reason and version check |
| `POST /api/v1/findings/{id}/patches` | Explicit patch-generation request |
| `GET /api/v1/patches/{id}` | Diff, validation status, artifacts |
| `POST /api/v1/patches/{id}/verify` | Approved profile only; idempotent |
| `POST /api/v1/reviews/{id}/publish` | Explicit authorized review publication |
| `POST /api/v1/patches/{id}/publish` | Explicit authorized fix branch/PR creation |
| `GET /api/v1/reviews/{id}/export` | JSON/Markdown; patch separately |
| `GET /api/v1/examples` | Public recorded examples with provenance |

Use a shared error envelope: stable code, human-readable message, retryable flag, run/stage IDs, safe details. Never return secrets, raw provider credentials, host filesystem paths, or full exception dumps to clients.

Persist runs, jobs, stage results, findings, evidence, patches, dispositions, publication IDs, and SSE events. Artifact files are content-addressed or referenced by immutable hashes. Store schema/model/prompt/rule versions. Migrations are repeatable and tested. On restart, reclaim only expired leases; mark uncertain in-flight side effects for reconciliation, not blind repetition.

Minimum deployment auth: anonymous recorded examples; authenticated or tightly controlled live scans; owner-bound result access; operator-only publishing to approved demo repositories. For cookie sessions, enforce CSRF protection on mutations. CORS is not authentication. For local mode use explicit local-only binding and document capabilities.

Request-scoped structured logs: run ID, stage, duration, queue time, tool version, model, usage, retries, error classification. Redact source/secret content. Frontend progress must reflect actual stage events; no invented percent completion. Distinguish queued, analyzing, verifying, interrupted and partial states.

## 11. GitHub and CI integration [P0/P1]

### P0 workflow

- Public PR read via GitHub REST API with pagination, timeouts, explicit rate-limit handling and revision capture.
- Controlled server token for owned demo repos only, never exposed in browser or test worker.
- One review summary with a small number of high-value inline comments. Group style nits in summary; default maximum five actionable inline comments.
- Respect GitHub review path/side/line semantics; out-of-hunk evidence belongs in summary with revision links.
- Record publication identifiers and use a run/finding marker to avoid duplicate review spam.
- Never post all old repository issues to a new PR.
- Link to check artifacts and show verification scope in review body.

### CLI and CI

Provide one CLI invoking the same engine as the web service:

```text
proofline doctor
proofline review --repo <path-or-supported-url> --base <sha> --head <sha> --format json
proofline review --pr <url> --format markdown
proofline evaluate --manifest evals/manifests/holdout.json --output <dir>
```

Exit codes: 0 successful review with no policy-blocking findings; 1 policy-blocking findings; 2 incomplete/error/configuration failure. Document exact policy. Style never blocks by default. Contextual LLM suspicion alone should not trigger a hard fail unless the user explicitly selects that policy.

Include a GitHub Actions example. Keep least privilege, pin action versions, and separate read-only analysis from privileged publishing. Never check out/run untrusted PR code under `pull_request_target` with secrets. Fork PRs without secrets get static-only analysis labeled accordingly; trusted model analysis runs in a separately authorized path. No secret access in verification containers.

### P1 GitHub App

Installation-scoped tokens; minimal contents-read and pull-request permissions; webhook HMAC verification; delivery-ID dedupe; updated-head cancellation; explicit opt-in for comment/check publication. Do not block the core demo on OAuth/App setup. Verify current GitHub endpoints and permissions in official docs before implementing.

References: https://docs.github.com/en/rest/pulls/reviews and https://docs.github.com/en/rest/pulls/comments

## 12. Developer UX and frontend [P0]

Build a cohesive review workspace, not a security dashboard with unrelated metrics.

### Entry screen

- Clear one-sentence value proposition and Python scope.
- Primary: paste repository/PR URL. Secondary: open recorded example.
- Examples labeled “Recorded run” with revision, date, provider/model and tool versions.
- Show availability/limits before submission; missing API key is actionable, not an infinite spinner.
- No mandatory account creation for exploring recorded examples.

### Review workspace

- Header: repo, PR/title, base/head SHA, live/recorded/static-only indicator, status, analyzed scope.
- Summary: actionable issues by category; verification status; skipped/failed stages; elapsed time and measured usage.
- Main panes: file/diff navigation, findings, and an evidence drawer. Stack accessibly on narrow screens.
- Finding shows impact, trigger, exact location, relevant source, evidence status, assumptions, and recommended action.
- Filters: security/bug/style, severity, introduced/pre-existing/unknown, evidence state, disposition.
- Evidence view: concise explanation plus source links and expandable logs/test results. Color is never the only status indicator.
- Patch view: before/after diff, changed files, expected base revision, validation checks, then download/publish actions.
- Safe clean result: “No issues found in the analyzed scope,” plus coverage. Partial analysis is visually distinct.
- Empty, unsupported, cancelled, stale, failed, offline, timeout and authentication states are first-class UI states.
- Review history/reload loads persisted reports. Reconnection must not duplicate findings or regress stage state.
- Dismiss/accept actions show reason and are reversible.
- Keyboard navigation, visible focus, readable contrast, copy buttons, semantic labels, reduced-motion support and accessible dialogs.
- Avoid tiny code fonts, color-only badges, excessive neon and scrolling animation. Show the valuable result quickly.

Maintain one state machine/reducer for run lifecycle; abort stale fetches on new runs/unmount. SSE reconnect uses event IDs and snapshot reconciliation. Add client error boundaries with recovery actions. Never expose provider keys via frontend bundles or public configuration.

### Meaningful visual differentiator [P1]

An evidence-path strip with actual source locations and a before/after verification timeline. This has higher priority than a force-directed graph. If an interactive graph is built, include only useful navigable edges, distinguish inferred relationships, and keep a textual equivalent.

## 13. Declarative project configuration [P0 minimal / P1 advanced]

Add `.proofline.yml` with versioned schema and safe defaults:

```yaml
version: 1
languages: [python]
exclude: ["**/vendor/**", "**/generated/**"]
review:
  max_inline_comments: 5
  include_style: true
  include_pre_existing: false
policy:
  blocking_severities: [critical, high]
  require_execution_evidence_for_llm_only_block: true
```

Untrusted repository config may narrow analysis and request conventions, not increase execution permissions, change remote endpoints, read host files, disable security controls, or supply arbitrary commands. Server caps always win. Report exclusions and policy hash in coverage. Trusted verification profiles are separate operator-owned configuration.

## 14. Evaluation and credibility [P0]

No hardcoded benchmark values in UI or docs. All result tables derive from committed machine-readable scorer output, with run provenance and actual sample counts.

### Datasets

1. **Controlled pairs:** 24 safe/unsafe pairs across supported bug/security cases; 12 pairs development, 12 held out. Add separately scored style fixtures. Create labels before tuning.
2. **Public benchmark:** predeclare a supported subset of OWASP BenchmarkPython, exact revision/case IDs and expected results. Label subset results honestly; do not claim the entire benchmark.
3. **Repo cases:** pinned Vulpy and lets-be-bad-guys snapshots where useful; their deliberate vulnerabilities are not representative production prevalence.
4. **Real bug history:** at least one small public Python project with an independently documented buggy parent, fixed commit and existing regression test; choose after checking dependencies/ground truth.
5. **Dogfood:** run Proofline on its own changes and manually adjudicate useful findings. Do not claim comprehensive ground truth.

References: https://owasp.github.io/www-project-benchmark/ ; https://github.com/OWASP-Benchmark/BenchmarkPython ; https://github.com/fportantier/vulpy ; https://github.com/mpirnat/lets-be-bad-guys

Manifest fields: dataset/case ID, license/source, repo SHA or fixture hash, split, category/rule/CWE, expected positive/negative, accepted location/function, causal expectation, supported flag, protected test/profile, known limitations. Do not send expected labels/fix commits/holdout answers to the reviewer model.

### Comparisons

- Static-only with pinned rule configuration.
- Simple Gemini baseline using the same model and fair relevant-code/token budget.
- Full Proofline pipeline.
- P1 ablations: no cross-file context; no challenge stage; no execution; compare only claims those variants can support.

Keep detection metrics separate from repair metrics. Run cold and warm latency separately. Repeat stochastic model runs three times where budget allows and report variation; if only one run is possible, disclose it.

### Metrics/scoring rules

- Precision, recall and F1 by category and aggregate with sample counts.
- False-positive rate on safe cases, false positives per clean PR, duplicate comment rate.
- Match findings by predefined class and accepted location/behavior; do not award a match for vague mention of “security.”
- Correctly handled unsupported cases and partial/failure rate.
- Patch attempts/eligible cases, validated fixes/attempts, regression failures, no-op/rejected patch count.
- Median/p95 end-to-end and stage latency with sample size; token usage, calls, retries, price basis if estimated cost shown.
- Execution infrastructure failures remain in the report; do not silently remove them to improve results.
- For small samples, show raw TP/FP/FN/TN and uncertainty/limitations; avoid overinterpreting tiny differences.

Internal goals, not promised results: precision >=90% and recall >=75% on the declared held-out supported cases; <=1 unnecessary comment across ten clean PRs; zero failed showcased repairs; a small-PR latency suitable for the demo (target median <=60 seconds, p95 <=120 seconds if measured sample supports it). Publish actual outcomes even when goals are missed.

P1 metamorphic checks: rename variables, move safe code, add unrelated input reads, change comments to prompt injections, preserve semantics across refactoring. Expected behavior should remain stable; document exceptions.

## 15. Test matrix and quality gates

Use meaningful tests of behavior, not snapshots that merely repeat implementation. Paid/network-dependent tests are opt-in and clearly marked. Fakes must be deterministic and never leak into production live mode.

### Unit and property-focused tests

- URL parsing/rejection; safe path resolution; symlink escape; size limits; duplicate basenames.
- Diff mapping: renames, deletes, added files, multiple hunks, old/new side, malformed/truncated diff.
- Qualified symbols/import aliases/name collisions; unresolved dynamic calls.
- The four graph counterexamples in section 2; scope-aware safe/unsafe sanitizer cases.
- Typed provider output: correct/invalid JSON, truncation, blocked/empty response, rate limit, timeout, auth failure, unavailable model.
- Retries obey deadline/global concurrency; cancellation; usage aggregation across workers.
- Empty post-validation list remains empty; skipped challenge contributes no corroboration.
- Canonical dedupe and fingerprint stability under line shifts; dismissal invalidation after changed code.
- No nonexistent path/line citation survives validation.
- Patch no-op, stale hash, forbidden file, oversized edit, path traversal, partial apply rollback.
- Evidence state transitions: model PoC never becomes reproduced; missing dependency never becomes verified; zero test collection never passes.
- Idempotent publish/job retries and tenant/owner access controls.

### Integration tests

- Controlled local Git repo with base/head commits → real diff → static adapters → fake Gemini → validated report.
- Live Gemini opt-in test with harmless fixture and schema; verify key redaction and usage metadata.
- Full controlled verification profile: expected failure before, pass after, happy-path tests preserved, protected test hash unchanged.
- Worker restart/lease expiry; persisted completed report; reconnect SSE with no duplicate event application.
- Simulated GitHub pagination, rate limit, changed head, comment mapping, permission failure and duplicate publish.
- Secret scanner/redaction applied before provider call and public artifact serialization.

### Frontend/end-to-end tests

Use Playwright or the project's available equivalent for: recorded example without credentials; live-style review with controlled backend; filtering and evidence; patch diff and checks; failed/partial state; cancellation/reconnection; stale patch; unauthorized publish; keyboard flow and narrow viewport. Frontend production build and type/lint checks must pass.

### Required gate commands

Create scripts/Make targets that actually exist before documenting them: `make setup`, `make dev`, `make doctor`, `make test`, `make lint`, `make build`, `make demo`, `make eval`, `make smoke`. Targets should be noninteractive where feasible, with clear missing-key/isolation errors. Document platform prerequisites and one supported Python/Node version; verify them on a fresh environment.

Do not claim “all tests pass” if paid/integration tests were skipped; summarize executed versus skipped suites.

## 16. Implementation milestones and acceptance criteria

### M0 — Baseline, inventory and regression harness [P0]

- [ ] Inspect repo/status/config; preserve user work; record baseline SHA and supported runtimes.
- [ ] Create implementation status tracker and baseline known-failure cases.
- [ ] Establish importable backend/test harness, deterministic local fixture repo and frontend checks.
- [ ] Fix empty-result fallback, workspace collisions, deceptive evidence labels.
- [ ] Confirm no old claim remains presented as verified behavior.

Gate: baseline regression tests demonstrate repaired trust/state defects; existing UI still opens.

### M1 — Proofline rename + Gemini vertical slice [P0]

- [ ] Complete branding/provider inventory, central settings and secrets handling.
- [ ] Implement native Gemini adapter with typed output, failure states and usage.
- [ ] One harmless fixture reaches frontend through provider adapter; fakes and live modes visibly separate.
- [ ] Opt-in live smoke passes if credentials available; otherwise document precise blocker without blocking remaining work.

Gate: no active Amazon/Nova integration; schema-valid provider result and provider failure both render correctly.

### M2 — Immutable PR review + static analysis [P0]

- [ ] GitHub PR/repo input, pinned revisions, safe snapshots, robust diff mapping.
- [ ] Ruff/Bandit and selected Semgrep adapters with normalized categories.
- [ ] Persist jobs/reports/events, bounded worker, coverage and interruption handling.
- [ ] Minimal review summary and diff UI.

Gate: controlled actual PR reports security, bug and style; no invalid citations; restart preserves completed report.

### M3 — Contextual intelligence and low noise [P0]

- [ ] Qualified symbol/index context with unresolved relationships explicit.
- [ ] Budgeted Gemini review/challenge, canonical dedupe, evidence provenance.
- [ ] Base/head comparison where supported; unknown state otherwise.
- [ ] Safe controls rejected appropriately; no heuristic confidence masquerading as probability.

Gate: cross-file demo finding is causally correct and linked to real code; matched safe example is handled; context omissions visible.

### M4 — Verified repairs [P0 flagship]

- [ ] Minimal typed edits, stale checks, isolated workspace and immutable test oracle.
- [ ] Approved isolated runner profile and interpreter for outcomes.
- [ ] Before/after regression plus ordinary behavior checks; hashes and logs saved.
- [ ] Patch/evidence UI, downloadable patch, failed/inconclusive states.

Gate: one independently reproducible red→green repair with existing checks passing; malicious/invalid patch rejected; no host execution fallback.

### M5 — Developer workflow and CI [P0]

- [ ] GitHub summary/inline publication controls and idempotency.
- [ ] CLI/CI share same engine and documented exit policy.
- [ ] Dispositions, persisted history, filtering, keyboard use, partial/empty states.
- [ ] Model and token budgets, rate limits, authenticated privileged routes.

Gate: developer can review, understand, dismiss, generate patch, inspect checks and export; controlled publication works if authorized.

### M6 — Evaluation and useful advanced depth [P0 evaluation / P1 extensions]

- [ ] Frozen case manifests; fair baselines; deterministic scorer; raw results and provenance.
- [ ] Publish actual metrics/limitations and rerun instructions.
- [ ] Add evidence-path visualization and metamorphic/ablation checks if core gates passed.
- [ ] Optional JS/TS deterministic lint/selected static rules with honest capability matrix; no claim of Python-equivalent semantic verification.
- [ ] Optional 2–3 developer usability sessions; capture real feedback, fix recurring friction.

Gate: another person can reproduce the result table; every headline claim points to evidence.

### M7 — Deployment and submission [P0]

- [ ] Fresh-clone setup tested; dependencies locked; web/API built; health/readiness configured.
- [ ] Public recorded mode without secrets; controlled live mode; persistent volume and cleanup policy.
- [ ] README, architecture, screenshots, evaluation, limitations, AI disclosure and team fields complete.
- [ ] Record concise demo; prepare offline fallback; all links verified from a fresh browser.
- [ ] Submit by target time, preserve final commit and artifact hashes.

Gate: end-to-end walkthrough succeeds from a clean user session; no undocumented manual step; final submission matches actual code.

## 17. Time and scope control

Use early-start authorization to complete M0/M1 and prepare fixtures before November 2 if possible. Official 48-hour allocation: approximately 6 hours PR/schema, 8 hours analyzers/context, 8 hours verified repair, 6 hours integration/UX, 12 hours evaluation/reliability, final 8 hours documentation/demo/submission. These are scope budgets, not guarantees or a request to skip sleep.

Checkpoint at hour 12: real PR ingestion must work. At hour 24: narrow verification to one trusted profile if needed. At hour 36: feature freeze. At hour 40: submission assets only except critical bugs. At hour 46: submission already uploaded.

Cut order if behind: extra languages → App/webhook setup → graph visualization → model routing/caching optimization → extra detector categories. Preserve one real contextual review, one independently verified fix, honest coverage, stable demo and reproducible evaluation. Never replace missing implementation with fabricated output.

## 18. Deployment and operational checklist

- Production frontend and Python API have explicit configured URLs; verify CORS and SSE behavior through the actual proxy.
- Use bounded review workers, persistent storage and health checks; avoid multi-instance SQLite contention by deploying a documented single-writer topology.
- Store secrets only in server secret configuration; ensure frontend bundle/logs and downloaded reports contain none.
- Public examples read immutable artifacts. Live analysis has quotas/auth; public access cannot spend unlimited Gemini calls or publish through an operator token.
- Separate verification worker from web host; if unavailable, capabilities endpoint disables verification truthfully.
- Warm deployment before recording/judging; measure cold-start separately.
- Back up final report/demo artifacts locally; include revision/time labels in replay.
- TTL cleanup handles workspaces/artifacts according to documented retention, does not delete active jobs, and respects owner deletion requests.
- No arbitrary user code execution on a shared server with credentials.

## 19. Documentation and presentation deliverables

README first screen: Proofline title + FT-05 + one-sentence benefit + demo/video links + evidence screenshot. Then supported scope, quickstart, workflow, results with counts, architecture, evaluation reproduction, limitations, team and AI tools.

Required files:

- `README.md`: judge-facing overview plus verified quickstart.
- `docs/architecture.md`: data flow, boundaries, schema and tradeoffs.
- `docs/evaluation.md`: manifests, matching rules, baselines, actual metrics and limitations.
- `docs/verification.md`: supported profiles and precise meaning of checks passed.
- `docs/deployment.md`: server/worker config, secrets, operations and recovery.
- `docs/demo-script.md`: timed demo with live/recorded segments identified.
- `docs/implementation-status.md`: execution tracker and remaining gaps.
- `docs/limitations.md`: unsupported languages/frameworks, dynamic resolution, partial analysis, dataset limitations.
- `.env.example`, CI workflow, run/test commands and dependency locks.

Three-minute demonstration:

1. 0:00–0:20: show a realistic PR and developer problem.
2. 0:20–0:45: submit PR, show revision/scope and genuine progress.
3. 0:45–1:15: inspect prioritized cross-file finding and cited source.
4. 1:15–1:55: show independent failing test, proposed patch, passing rerun and preserved happy path.
5. 1:55–2:15: safe counterpart and style/bug grouping; explain noise reduction.
6. 2:15–2:40: actual baseline/evaluation table, samples and limitations.
7. 2:40–3:00: export/GitHub workflow and concise supported-scope statement.

Do not spend demo time reciting libraries or waiting for a large repo scan. Use a small genuine PR. Record a fallback with the same release. If showing a completed run, explicitly label it. Do not claim “fully verified” beyond supported executed checks.

## 20. Final acceptance checklist

- [ ] Proofline identity throughout active product; no live legacy provider.
- [ ] Native Gemini structured generation with verified model configuration and explicit failure handling.
- [ ] Python-primary AI implementation; bug/security/style categories implemented.
- [ ] Real repo and PR review on immutable revisions; valid diff locations.
- [ ] Useful cross-file context with honest unresolved edges.
- [ ] Static facts, model assessments and execution evidence are distinct.
- [ ] No empty-result resurrection; no fake confidence/confirmation; no replay presented as live.
- [ ] One meaningful independently verified repair; test oracle protected; ordinary behavior preserved.
- [ ] Failed, partial, stale and unsupported states tested and visible.
- [ ] Unique workspaces, safe reads, bounded jobs, owner checks, secret redaction.
- [ ] CLI/CI and web use the same engine; publication is explicit and idempotent.
- [ ] Clear low-noise review UX, evidence/diff/test output and accessible controls.
- [ ] Evaluation manifests, raw artifacts, scorer and actual metrics committed/documented.
- [ ] Fresh-clone install, tests, lint/type checks, frontend build and smoke workflow verified.
- [ ] README and demo satisfy event requirements and reflect final functionality.
- [ ] Deployed/recorded examples work without exposing credentials; final links checked.
- [ ] Team names and actual AI-tool disclosure filled in by known information; no invented identities.
- [ ] Final report distinguishes completed work, skipped live checks, and remaining limitations.

The engineering bar is a dependable, inspectable developer workflow. Technical ambition earns credit when its behavior can be demonstrated, measured, reproduced and explained.
