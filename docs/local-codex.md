# Local Codex with a ChatGPT subscription

The local backend can use the installed Codex CLI and its existing **ChatGPT** login. It does not copy credentials into Proofline, mount a login into Docker, create an unofficial ChatGPT proxy, or fall back to API-key billing. Requests go to OpenAI and consume the account's Codex subscription limits. Localhost refers to the integration, not offline model inference.

## Start and use

The local `backend/.env` is configured for this demo. Restart backend and frontend after pulling these changes:

```sh
make dev
# another terminal, from the repository root:
cd frontend
npm run dev
```

If login is needed, run `codex login` in your terminal and choose ChatGPT. `codex login status` should say that ChatGPT is in use. No OpenAI API key is required.

In **Settings & debug**, select **Local Codex · ChatGPT subscription**. Leave Model ID blank to use the live account catalogue's default; the field also suggests discovered models. High reasoning and one attempt are the demo defaults. Model roles remain configurable. Start a URL/folder review or **Try example**. Repairs and pinned-source resume preserve the original provider, models and reasoning.

Local settings:

```dotenv
PROOFLINE_LLM_PROVIDER=codex_cli
PROOFLINE_CODEX_CLI_ENABLED=true
PROOFLINE_CODEX_CLI_PATH=codex
PROOFLINE_CODEX_MODEL=auto
PROOFLINE_CODEX_REASONING=high
PROOFLINE_CODEX_REQUEST_TIMEOUT_SECONDS=120
```

Use a native local backend process, not the container stack, for this mode. Remote-client use is rejected. Do not publish a subscription-backed service or forward it through a public proxy. Gemini remains selectable separately.

## Implementation

`codex exec` runs in an empty temporary directory, read-only and ephemeral, without user configuration/rules. Native shell, browser, app/plugin, hook and delegation capabilities are disabled. Proofline's existing bounded read tools perform repository investigation through typed JSON. The source context is supplied through private stdin files; application/provider/GitHub API keys are removed from the child environment. Native Codex owns login and refresh.

Strict JSON Schema and Pydantic validate final output. Incomplete turns, invalid output and native tool activity cannot become successful findings. Completed output can coexist with a nonfatal startup diagnostic about disabled native Code Mode; that diagnostic is visible in debug history. Cancellation/deadlines terminate the invocation process group. Output is bounded. One local CLI inference invocation runs at a time.

The UI counts CLI launches, including Proofline retries. Native CLI service retries are not separately counted, so these counts are not exact upstream HTTP-request counts. Returned usage includes input/output/cache/reasoning metadata; missing usage on failures is unknown, not a zero-cost claim. Capacity, subscription limits, unsupported models and login failures remain explicit. No silent model/provider fallback occurs.

## Actual validation

The stale local model cache advertised GPT-6.1 Sol, which the account rejected. Native `model/list` returned GPT-5.6 Sol as the account default. That discovered model passed structured transport and the complete authored base/head review with high reasoning: four CLI invocations, all stages completed, and all four requested candidate assessments returned source-supported quotations. Final comments can consolidate candidate signals; source-supported does not mean execution-proven or independently correct.

The complete review took approximately 67 seconds. Reports: `evals/results/codex-cli-smoke.json` and `codex-cli-review.json`. Earlier diagnostic failures are retained separately. These are integration results, not precision/recall measurements.

Optional reproduction, spending subscription quota:

```sh
PYTHONPATH=backend ../.venv/bin/python scripts/verify-codex-demo.py --live
```

CLI review also supports `--provider codex_cli --codex-reasoning high`, model-role overrides, budgets and pinned-source resume. Ordinary regression tests disable live Codex use.

Official references: [authentication](https://learn.chatgpt.com/docs/auth?surface=cli), [non-interactive structured execution](https://learn.chatgpt.com/docs/non-interactive-mode), [native model discovery](https://learn.chatgpt.com/docs/app-server#list-models-modellist).
