# Proofline Python backend

See the root README and docs/deployment.md for canonical setup. Run `make dev` from the repository root, or `PYTHONPATH=backend ../.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000` with the configured virtual environment.

Versioned review APIs live under `/api/v1`. Configure Gemini server-side only. Missing model/key is explicit partial analysis. Node and the installed frontend TypeScript library are also required for JavaScript/TypeScript static parsing. No npm configuration from reviewed repositories executes.

Legacy scan endpoints remain for compatibility; the home interface uses the versioned PR workflow. Verification and GitHub writes require explicit configuration and user action. See language-support.md and deployment.md in the root docs directory for precise boundaries.

Gemini API selection: `PROOFLINE_GEMINI_API_MODE=auto` uses Interactions for modern models and generateContent for Gemini 2.5. Use debug settings or CLI `--api-mode` to override. Interactions disables conversation storage and automatic continuation. Historic saved runs preserve their original transport. See [transport details](../docs/backend-v2.md#gemini-api-compatibility).
