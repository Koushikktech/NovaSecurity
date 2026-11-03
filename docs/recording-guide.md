# Checkout recording walkthrough

Open `/showcase`. It replays the real November 3 end-to-end authored checkout case and uses no inference during replay. The active product is available at `/review`.

1. **The change**: remove the discount default in pricing; checkout still supplies only subtotal. Replay the saved failing checkout outcome.
2. **The investigation**: follow pricing → checkout → source-supported consequence. Click the caller to inspect source.
3. **The evidence**: two observations support one checkout regression; open source quotations. Candidate assessment is distinct from executed proof.
4. **The repair**: inspect the actual model-generated caller edit, adding `discount_cents=0`.
5. **The execution**: the same protected oracle on original, changed and repaired snapshots: pass, assertion fail, pass. The explicit-discount happy path stays green.
6. **The system**: connect source snapshots, deterministic analysis, investigation, assessment and controlled repair execution. The architecture is a capability view, not an invented execution trace.

Use arrow keys, next/previous buttons and focus mode. Escape closes source or leaves focus. Video capture mode disables decorative animations; it never simulates live requests. `docs/final-narration.md` supplies suggested two-minute narration.

Reproduce live evidence: `PYTHONPATH=backend ../.venv/bin/python scripts/build-flagship-demo.py --live`. It requires the local ChatGPT CLI and prepared Docker image. `--resume` reuses the recorded review snapshot to propose/verify a patch; model calls remain explicit. The saved artifact is `evals/results/flagship-checkout.json`. Protected oracles reside outside reviewed snapshots. Do not claim this controlled case proves general accuracy.
