# Proofline review interface

Install dependencies with `npm ci`, then run `npm run dev`. The homepage and `/review` use v1 review APIs. The API defaults to http://localhost:8000; configure `NEXT_PUBLIC_API_BASE_URL` at build time if needed. Never place provider or GitHub secrets in NEXT_PUBLIC variables.

Connection settings accept the single-operator server token in page memory. The interface provides a controlled example, category filters, real source/diff/evidence, dispositions, patch proposal/download/checks and explicit publication. Follow the root README for setup and actual language capabilities.

A review-session reducer discards stale responses, aborts replaced requests and retries transient reads. Saved running reviews continue polling; `?run=<id>` restores the report on reload. Reconnect reads existing state and never submits another model job. The current UI polls snapshots; the separate SSE endpoint also supports event cursors. Browser regression scripts are in `../scripts/browser-*-smoke.cjs`, including recovery fault injection.
