# Review projects, commits, comparisons, PRs and local work

The home page offers six explicit selectors: Detect from URL, Whole project, Single commit, Compare revisions, Pull request, and Local folder. Supported languages remain Python and JavaScript/TypeScript as detailed in language-support.md. Supported remote hosts are public GitHub repositories; use a local folder for other hosting providers. This is not a claim to understand every programming language or unlimited repository size.

| Mode | Input | Exact analysis scope |
|---|---|---|
| Whole project | GitHub repository URL; optional branch/tag/commit | Immutable selected snapshot; defaults to default-branch HEAD. No invented all-files-added diff. |
| Single commit | GitHub `/commit/<sha>` URL, or repo plus revision | Commit against its first parent; initial commit against empty tree. Merge commits use first parent, clearly labeled. |
| Compare revisions | Repo URL plus base and head | Exact base snapshot versus head snapshot, even when revisions diverge. |
| GitHub compare URL | `/compare/base...head` | Merge base versus head, matching triple-dot comparison semantics. Cross-fork comparisons require a PR URL. |
| Pull request | GitHub `/pull/<number>` | Resolved PR merge base to head, including explicit fork-head fetch. |
| Local folder | Browser directory selection | Uploaded supported text files, preserved as a content-hashed snapshot; no history is assumed. |
| Working tree (CLI) | Local Git repository | HEAD versus copied local working files, including supported untracked files. Original files are never changed. |

Branch names with slashes are supported. A `/tree/branch` URL is interpreted as a revision, not as a selected subdirectory; for ambiguous GitHub tree paths, use the repository URL and the explicit revision field. Invalid revisions fail visibly; they never silently fall back to HEAD.

## Whole-project depth and coverage

Quick mode uses one budgeted context selection. Deep mode batches supported source across multiple structured model calls, bounded by configured context, call and time budgets. Static tools inspect supported files in the exported snapshot independently of model coverage. Reports expose the exact revision, file inventory, batch coverage, unreviewed files and failed stages. Deep does not imply exhaustive reasoning or guarantee no bugs.

Initial limits: 2,000 files / 20 MiB selected text / 500 KiB per file; binary, symlink, submodule and vendored/build content is excluded. Inputs that exceed total inventory limits fail instead of claiming a full review. Folder upload filters unsupported files before upload and enforces server-side path/size checks. With Gemini configured, selected source context is sent to Gemini; no uploaded program/configuration is executed during analysis.

## Local CLI

Run these from the repository root after setup. `--static-only` avoids all model calls; omit it for configured Gemini inference.

```sh
# Whole local folder, including current unsaved-to-Git working files
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo /path/to/project --mode project --static-only

# Local immutable tag/branch snapshot
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo /path/to/project --mode project --revision v1.0 --depth deep

# A local commit versus its first parent
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo /path/to/project --mode commit --revision HEAD --static-only

# Exact comparison of local revisions
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo /path/to/project --mode compare --base main --head feature/pagination --static-only

# Staged + unstaged + supported untracked files versus HEAD
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo /path/to/project --mode working --static-only

# A public GitHub commit URL, automatically detected
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo https://github.com/OWNER/REPO/commit/SHA --static-only
```

Local project mode without a revision reviews filesystem contents; it does not include unsaved editor buffers that have not been written to disk. A local folder without Git history supports project review; revision/commit/working modes require a valid Git repository.

## Actions after review

Every mode supports findings, source/evidence inspection, dismissal, export and patch proposals when Gemini is available. Review comments and fix-PR publication require a pinned PR mode; other modes clearly offer export/download rather than claiming a GitHub publication destination. Runtime verification remains restricted to the approved operator profile and requires its configured Docker worker.

## Shared runtime controls and CLI recovery

```sh
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --repo ./project --thinking low --max-model-calls 8 --max-tool-calls 16 --deadline-seconds 180
PYTHONPATH=backend ../.venv/bin/python backend/cli.py review --resume <run-id> --static-only --format json
```

`--model`, `--verifier-model` and `--repair-model` select Gemini models; `--max-attempts` limits retries. `--strategy` supports diff/context/investigate/verified evaluation variants. Resume preserves sealed source and recorded configuration unless explicitly overridden. A new source snapshot requires a new review. Static-only never contacts the model. CLI `evaluate` remains a labeled legacy snippet heuristic; use `evals/review_benchmark.py` for system ablations.
