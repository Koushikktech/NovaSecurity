# NovaSecurity — Backend Engine

AI-powered Static Application Security Testing (SAST) and automated vulnerability remediation backend built with FastAPI, LangGraph, Tree-sitter, NetworkX, and Amazon Nova (`nova-2-lite-v1`).

---

## 🎯 Architecture Overview

The backend uses a multi-stage adversarial agent pipeline that marries compiler-level AST analysis with large language model reasoning:

```
Target Repository
       │
       ▼
 1. [Ingest Node] ────────► Clones repository, filters source & config files
       │
       ▼
 2. [Index Node] ─────────► Tree-sitter AST symbol & signal extraction
       │
       ▼
 3. [Graph Node] ─────────► Inter-procedural data-flow DiGraph (Sources → Sinks)
       │
       ▼
 4. [Targeted Scan] ──────► Parallel Nova evaluation of unsanitized data-flow paths
       │
       ▼
 5. [Indexed Sweep] ─────► Architectural & configuration vulnerability sweep
       │
       ▼
 6. [Merge Findings] ────► Deduplication & cross-source confidence boosting
       │
       ▼
 7. [Red Team Node] ──────► Parallel Proof-of-Concept (PoC) exploit construction
       │
       ▼
 8. [Blue Team Node] ─────► Exploit refutation & composite confidence scoring
       │
       ▼
 [Validated Findings] ───► Ready for Force Graph Visualization & Auto-Remediation
```

---

## 🔍 Core Components

| Module | Description |
|---|---|
| `agent.py` | StateGraph definition and node orchestrators for the 8-stage LangGraph workflow. Manages parallel LLM worker pools (`ThreadPoolExecutor`). |
| `indexer.py` | Tree-sitter AST parser (`tree-sitter-python`). Extracts functions, classes, decorators, imports, and security signals (`routes`, `db_access`, `user_input`, `dangerous_calls`, `auth`). Prioritizes files for scanning. |
| `graph.py` | Constructs inter-procedural directed data-flow graph (`networkx.DiGraph`). Maps untrusted sources (`request.args`, `sys.argv`), intermediate variable assignments, sanitizers (`escape`, `bleach`), and dangerous sinks (`eval`, `system`, `execute`). |
| `nova.py` | Client interface for Amazon Nova (`nova-2-lite-v1`) with JSON extraction, invalid backslash correction, and dynamic reasoning tokens. |
| `remediation.py` | Automated remediation engine. Creates isolated git branches, selects relevant context files, prompts Nova for targeted patches, applies changes, generates unified diffs, and opens GitHub Pull Requests. |
| `api.py` | FastAPI application exposing REST and Server-Sent Events (SSE) endpoints for scan execution, live progress tracking, demo datasets, and PR creation. |
| `storage.py` | Optional persistence layer for Supabase (stores scan summaries, metrics, and finding rows). |

---

## 📊 Confidence Scoring Formula

Findings are validated through an adversarial Red Team / Blue Team debate. The final confidence score is computed as:

$$\text{Final Confidence} = 0.30 \times C_{\text{LLM}} + 0.25 \times S_{\text{Graph}} + 0.25 \times E_{\text{Red}} + 0.20 \times (1.0 - D_{\text{Blue}})$$

Where:
- $C_{\text{LLM}}$: Base confidence reported by the scanner LLM.
- $S_{\text{Graph}}$: 1.0 if corroborated by AST data-flow path, else 0.0.
- $E_{\text{Red}}$: 1.0 if the Red Team succeeded in generating an exploit PoC, else 0.0.
- $D_{\text{Blue}}$: 1.0 if the Blue Team successfully disputed the vulnerability with architectural defense evidence, else 0.0.

### Categorization:
- **$\ge 0.60$**: `Confirmed`
- **$0.30 - 0.59$**: `Needs Review`
- **$< 0.30$**: `Likely False Positive` (filtered out by default)

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+ (tested up to 3.14)
- Git CLI installed

### Installation
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables
Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `NOVA_API_KEY` | Amazon Nova or OpenAI-compatible API key | *Optional for demo mode* |
| `NOVA_BASE_URL` | Endpoint for the LLM provider | `https://api.nova.amazon.com/v1` |
| `NOVA_MODEL` | Target Nova model name | `nova-2-lite-v1` |
| `NOVA_ALLOWED_ORIGINS` | Allowed CORS origins (comma-separated) | `http://localhost:3000` |
| `GITHUB_TOKEN` | Personal Access Token for PR creation | *Optional* |
| `SUPABASE_URL` | Supabase project URL | *Optional* |
| `SUPABASE_KEY` | Supabase anon key | *Optional* |

### Run the Server
```bash
python main.py
# Server runs on http://0.0.0.0:8000
```
Interactive API documentation is available at `http://localhost:8000/docs`.

---

## 📡 API Endpoints

- `POST /api/scan`: Initiates a repository scan (`{"repo_url": "..."}`).
- `GET /api/scan/{scan_id}/stream`: Real-time Server-Sent Events (SSE) tracking pipeline progress.
- `GET /api/scan/{scan_id}`: Retrieves scan status and full results.
- `GET /api/scan/{scan_id}/findings`: Retrieves clean findings and severity summary.
- `GET /api/scan/{scan_id}/graph`: Retrieves NetworkX nodes, links, and detected attack paths.
- `POST /api/demo`: Instant benchmark scan simulation (`{"repo_key": "lets-be-bad-guys" | "vulpy"}`).
- `POST /api/scan/{scan_id}/fix`: Triggers automated code remediation for a finding index.
- `GET /api/fix/{fix_id}`: Returns status, generated unified diff, rationale, and compare URL.
- `POST /api/fix/{fix_id}/pull-request`: Pushes fix branch and creates a GitHub Pull Request.
- `DELETE /api/scan/{scan_id}`: Deletes scan state and cleans up temporary disk workspaces.
