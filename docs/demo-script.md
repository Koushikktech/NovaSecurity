# Evidence-first demonstration

Use the actual current UI and actual recorded outcomes. Do not present mocked browser checks or static findings as successful live AI verification.

## Five-minute route

1. **Choose code (30 seconds).** Explain Paste a link, Pick from GitHub, and Local folder. Select **Try example** to construct real base/head Git commits with a Python caller regression and a TypeScript async mistake. The controlled example is reproducible source, not a canned model report.
2. **Explain one correctness finding (60 seconds).** Select the caller regression. Walk through What happens, Why it matters and Recommended action. Open source and the related callee. Explain the distinction between static evidence, source-supported model assessment and execution proof.
3. **Show impact (45 seconds).** Open Files & diff. Inspect a changed symbol, resolved callers and lexical test hints. Show the colored diff and connect an impact item to its finding. No graph edge or missing-test claim should be invented.
4. **Show operational honesty (45 seconds).** Open model activity and verification coverage. Identify actual requests, retries, tool observations and omitted candidates. If the provider failed or quota was exhausted, retain the partial status. Resume pinned review demonstrates preserved source rather than fetching a different commit.
5. **Show repair proof (60 seconds).** Propose and inspect a patch only when the model is available. For deterministic execution evidence, run `PYTHONPATH=backend ../.venv/bin/python scripts/verify-differential.py` against the prepared images. The real Python/JS/TS checks establish base pass, intended head failure and patched pass. The custom external-profile demonstration is `scripts/verify-operator-profile.py`. These test specific contracts, not every application.
6. **Show evaluation (45 seconds).** Explain the 12 development/24 heldout authored corpus, blinded independent review and strict finding adjudication. Show pinned public-history source observations. Until annotation and full live ablations are complete, do not display an accuracy percentage or claim superiority.
7. **Close (15 seconds).** Export the report. State the supported languages/scopes and the remaining real integration limits. Publish externally only with an explicitly authorized PR target and configured write policy.

## Before recording

- Restart the API after backend changes; use one operator process. Start the frontend with `npm run dev` or a checked production build.
- Keep an approved source fixture, a saved report and a screen recording available as fallbacks. Label recordings as recordings.
- Confirm model access and quota. The configured model previously hit quota; an alternate catalog model also returned provider overload/deadline failures. Do not assume these conditions have cleared.
- Docker is available locally and prepared images passed recorded checks; inspect the current image digests before the demo.
- GitHub App credentials are configured, but real account authorization/private-repository access still needs a user flow check. Publication is disabled unless separately configured.
- Independent labels and adjudication are pending. The ten-case `make eval` result remains a static integration smoke check, not model accuracy.

## ChatGPT subscription recording

Use the localhost Codex provider described in `local-codex.md`. On November 2, a real four-invocation run with the discovered GPT-5.6 Sol model and high reasoning completed all review stages and assessed every requested candidate, in about 67 seconds. This is a working integration case, not benchmark accuracy or execution proof. Keep the provider/model visible in request history. Subscription capacity errors remain possible; saved reports must be labeled as completed prior runs.
