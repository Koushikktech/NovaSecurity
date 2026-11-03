# Dependency audit — 2026-11-01

The npm registry audit initially reported six affected production dependency entries, including the pinned Next.js 16.1.6 chain. The frontend now pins [Next.js 16.4.3](https://github.com/vercel/next.js/releases/tag/v16.4.3), uses a single npm lockfile, and includes Linux native optional dependencies. Clean local and Linux ARM64 container production builds passed.

The subsequent production audit reported zero known advisories. The full audit still reports 16 moderate affected development dependency entries stemming from [the minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249). Those lint dependency chains remain documented; no incompatible blanket major-version override was forced. Reviewed repositories do not execute their ESLint configuration in Proofline's analysis pipeline.

[Machine-readable audit evidence](../evals/results/dependency-audit.json) records counts, affected scope and source. This is a point-in-time package advisory check, not proof of application security or every dependency ecosystem. Rerun `npm audit --omit=dev --json` and `npm audit --json` from `frontend/` when preparing the final release.
