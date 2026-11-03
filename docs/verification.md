# Verification and repair protocol

A patch proposal, source-supported claim and executed test result are different evidence states. Only recorded checks for an approved environment can establish that a particular repair passed those checks.

## Proposal validation

Gemini returns typed exact edits for the cited file. Proofline rejects escaping/protected paths, no-op edits, ambiguous or stale old content and empty proposals. Python patches must parse with Python AST; JS/JSX/TS/TSX patches must pass the trusted TypeScript parser's syntax diagnostics. Missing parser infrastructure prevents accepting that language's proposal. No reviewed project code or configuration executes during syntax validation. TypeScript syntax success does not prove full project type compatibility.

The proposal remains `proposed` until an approved execution workflow runs. Suggested tests in model output are advice, never authorization for host commands.

## Approved profiles

| Profile | Runtime | Required check phases |
|---|---|---|
| `expense_service_sql` | Python / pytest | Head regression assertion fails; happy path passes; patched checks pass |
| `python_contract` | Python / pytest | Passing base → designated head assertion failure → passing patched head |
| `javascript_contract` | Node test runner | Same differential contract |
| `typescript_contract` | Trusted transpilation + Node test runner | Same differential contract; transpilation is not a complete application build |
| Operator-loaded profile | Prepared Python or Node environment | Operator-selected independent oracle; base is required when `require_base=true` |

Profiles and test oracles live outside reviewed source. The model and repository cannot add execution privileges. [Operator environment setup](operator-verification.md) documents prepared dependency images and custom profiles.

## Execution rules

1. Validate enabled execution, approved profile and digest-pinned image.
2. Copy source into a disposable workspace; reject symlinks and validate exact edits without modifying the original.
3. For differential profiles, run the independent oracle on base. All collected tests must pass.
4. On unpatched head, the designated regression must fail with an assertion; the required happy path and all unrelated tests must pass.
5. Apply the validated edits in the disposable copy and rerun the oracle. Every collected test must pass, including the designated regression and happy path.

Containers have no network, a read-only root/source/oracle, a non-root user, dropped capabilities and CPU/memory/PID/time limits. Model/GitHub credentials are not passed. These constraints reduce exposure; they are not a claim of perfect containment against every container escape.

Missing infrastructure, zero tests, skipped/error results, invalid reports or unrelated head failures are `inconclusive`. A completed patched run with failing checks is `checks_failed`. Only successful required checks produce `checks_passed`. Commands, revisions, durations, exit codes and output excerpts remain inspectable.

## Recorded evidence

Actual Docker fixture checks passed for Python, JavaScript and TypeScript in [differential-execution.json](../evals/results/differential-execution.json). An externally configured application contract passed in [operator-profile-execution.json](../evals/results/operator-profile-execution.json). Reproduce with the scripts linked in [operator verification](operator-verification.md).

These results prove the exercised behavior and environment. They do not establish every proposed repair is correct, arbitrary projects can run, or a repository is secure. Independent model-quality measurement is tracked separately in [the evaluation protocol](../evals/README.md).
