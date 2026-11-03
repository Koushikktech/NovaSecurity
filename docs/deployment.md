# Local operation and deployment

Use one API process; SQLite and the two-slot in-process review scheduler are designed for a single operator deployment, not an enterprise multi-tenant service. Restart marks queued/running reviews interrupted; resume them from sealed source when available. Run `make setup`, then `make dev` for the API and `cd frontend && npm run dev` for the UI. The homepage and `/review` use v1 review APIs.

Server model configuration: set `GEMINI_API_KEY` and `PROOFLINE_GEMINI_REVIEW_MODEL` to a currently available supported text model. No obsolete model is silently selected. Missing configuration gives partial static results; it never silently produces fake model reviews.

Remote access requires `PROOFLINE_OPERATOR_TOKEN`; enter it under UI Settings & debug. It is kept only in page memory. All API routes are protected in remote mode. Local development without a token accepts loopback clients only. Never expose a shared operator token as a public demo credential; use controlled access or recordings.

`docker compose config` validates deployment configuration (set the operator token). Backend build context is repository root so language parser and fixtures are present. Compose disables execution and binds published ports to loopback. HTTPS/reverse proxy and secure secret provisioning are operator responsibilities. The review frontend build and dedicated Docker verification images were checked locally; the local Compose stack now builds and passes authentication, CORS, Python/JS/TS static reviews, sealed-source resume and restart persistence checks. A publicly hosted deployment remains unverified.

Verification is deliberately separate. Build `backend/verification/Dockerfile` on a trusted host, inspect its local or registry digest, and set `PROOFLINE_VERIFICATION_IMAGE` to the resulting immutable `name@sha256:<64hex>` digest. Enable `PROOFLINE_EXECUTION_ENABLED=true` only on the controlled Docker runner host. Never mount its Docker socket inside the reviewed test container. Operator-owned oracle tests are mounted read-only; repository code is copied to a disposable workspace; source is never changed. Containers have no network, no host environment/keys, non-root identity, read-only root and resource limits. Docker timeout cleanup removes the named container. Missing infrastructure or unexpected JUnit failures are inconclusive, never verified.

GitHub publication requires a separately configured `GITHUB_TOKEN` and `PROOFLINE_GITHUB_PUBLISH_ENABLED=true`. Review publication posts a summary and supported diff-restricted inline comments; fix publication creates a dedicated branch/PR in the original PR head repository targeting its head branch. It never merges or writes directly to that branch. Unsupported fork permissions fail explicitly. API integration is tested with mock transports; live publication still requires validation on an owned repository.

## Trusted CI reviewer

The pull-request workflow runs reviewer code from the immutable base revision and analyzes a separate checkout of the subject. It never executes the PR's modified reviewer implementation. This requires the base branch to contain a working Proofline CLI; bootstrap the reviewer on the base branch before enabling this workflow. There is no fallback to untrusted PR code. Provider keys, execution and publication are disabled, checkout credentials are not persisted, and the report is retained as an artifact. Actions are pinned to immutable official-repository commits recorded in `ci-action-pins.json`. Local CLI/static checks are tested; the workflow itself still needs a real GitHub Actions run after the work is committed and authorized for CI.


## Reproducible local container checks

Backend images use frozen `backend/uv.lock`; frontend uses `npm ci` and the sole `package-lock.json`. `make setup` installs the pinned uv tool and synchronizes the backend environment from its lock. `backend/requirements.txt` is a hashed export for pip/CI. Do not maintain a second independent frontend lock.

Root/frontend Docker ignore files exclude local environment files, keys, review data, caches and legacy public replay artifacts. Both runtime containers are non-root, read-only with explicit temporary storage and dropped capabilities. The backend persists database, workspace and artifact paths in the data volume. Health checks authenticate internally without exposing the token. API/UI host ports, browser API build URL and allowed origins can be configured separately; published ports stay on loopback.

An isolated local stack passed `scripts/verify-container-stack.py` and the real browser walkthrough in `scripts/browser-container-smoke.cjs`. The reports are `evals/results/container-stack.json` and `server-recovery.json`. The latter interrupted an actively running API process and exercised queue saturation plus ten two-review warm rounds; it is not a production load benchmark. Local test containers are removed after verification; no public deployment or image publication follows from these checks.

Publication uses bounded single-process serialization, a 60-second operation budget, per-request remaining-time limits and remote marker checks on retry. A timeout is reported as unconfirmed, not successful. External exactly-once delivery is not claimed.
