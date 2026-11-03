# Operator-approved verification environments

Reviewed repository configuration cannot grant execution rights. To add a trusted project test environment, set `PROOFLINE_VERIFICATION_PROFILES` to an operator-owned JSON file outside the review workspace directory. Restart the backend after changing it. Duplicate built-in IDs are rejected. Example:

```json
[{
  "profile_id": "approved-service",
  "name": "Approved service regression",
  "description": "Operator-maintained tests for a pinned dependency environment",
  "runtime": "python",
  "image_env": "PROOFLINE_SERVICE_VERIFICATION_IMAGE",
  "test_command": [],
  "container_command": ["python", "-m", "pytest", "-p", "no:cacheprovider", "--junitxml=/results/report.xml", "/oracle/test_service.py"],
  "oracle_dir": "/absolute/operator-owned/oracles/service",
  "oracle_file": "test_service.py",
  "regression_test_id": "test_regression",
  "happy_path_test_id": "test_happy",
  "require_base": true,
  "timeout_seconds": 30
}]
```

The selected image environment variable must contain a digest-pinned image reference. Prepare dependency environments in advance; no project dependency installation is performed during isolated execution. Commands are trusted operator configuration, never model-generated or loaded from the PR. Python commands must write JUnit to `/results/report.xml`; Node commands must emit JUnit to stdout. The source is mounted at `/work`, oracle at `/oracle`, and results at `/results`. Network is disabled, root filesystem read-only, user non-root, resources constrained, and no model or GitHub credentials are passed.

Differential verification requires base tests all passing; only the designated head regression assertion may fail; patched tests all pass. Missing tests, environment errors, unrelated head failures or incomplete reports are inconclusive.

## Validated fixture environments

```sh
docker build -t proofline-verification:python -f backend/verification/Dockerfile .
docker build -t proofline-verification:node -f backend/verification/Dockerfile.node .
PYTHONPATH=backend ../.venv/bin/python scripts/verify-differential.py
```

The script discovers local image digests and stores commands and test outputs in `evals/results/differential-execution.json`. Real Python, JavaScript and TypeScript fixture checks passed. These fixture checks establish the execution mechanism, not compatibility with every application. Operator profiles for real applications still require their own environment validation.

The non-root container UID matches the worker owner for private result-directory access (root operators use UID/GID 65534). Results use mode 0700, not world-writable permissions. Captured output is capped at 2 MB, file writes at 2 MiB, profile phases at 120 seconds, and DTD/entity-bearing JUnit is rejected. Evidence is still test-result evidence for trusted profiles, not cryptographic attestation against adversarial test evasion.
