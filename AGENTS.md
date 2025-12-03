Code Review Agent — Agent Guidelines

Scope: Entire repository

Purpose
- Keep the backend simple, nimble, and useful. Routes stay thin; the graph nodes and tools do the work. Prefer LangChain/LangGraph primitives over custom frameworks.

Key Architecture
- Graph: Defined in `backend/graph/graph.py`. Flow: `START → router → chat_mode → tools_parallel → synthesis → persist → END`.
- Tools: Run in parallel from `backend/graph/nodes/tools_parallel.py` using small, direct wrappers:
  - Security scanners (Bandit, Semgrep): `backend/tools/security_tooling.py`
  - Dead code (Vulture) + complexity (Radon): LC wrappers in `backend/graph/tools/*`
- Routes: Slim API in `backend/app/api/routes.py` (replaces the older `explain.py`).
- Memory: Lightweight in‑process conversation memory in `backend/app/core/memory.py`.

Do / Don’t
- Do keep API routes minimal. Stream SSE events and defer logic to the graph.
- Do use LC Tool wrappers (see `backend/graph/tools/security_tools.py`, `radon_tool.py`).
- Do run tools concurrently with `asyncio.to_thread` when calling sync helpers.
- Do keep SSE format stable: each line is prefixed with `data: `. Emit:
  - `:::progress: N`
  - `🔎 Router: language detection done.`
  - `🧪 Tools complete.`
- Don’t reintroduce a custom tool framework (registries, decorators, listeners). We removed `backend/tools/{base,registry,decorators,listener,builtin,orchestrator}.py`.
- Don’t expand the routes with orchestration logic; keep them as thin adapters.

Endpoints
- `GET /health` → `{"status": "healthy"}`
- `POST /explain` (SSE) → streams progress + final paragraphs
  - Request model: `backend/app/core/models.ExplainRequest`
  - Threading: Accept `thread_id` header `x-thread-id` or payload field
  - Persists latest analysis in memory for future chat (if added)

Local Dev
- Install: `make install-backend`
- Run API: `make run-backend`
- Example:
  - `POST /explain {"code": "def f(x):\n    return eval(x)"}`
  - Watch stream: router → tools → synthesis paragraphs → progress markers

Dependencies
- Optional tools: Semgrep, Vulture (graceful fallback). Bandit/Radon included in `pyproject`.
- OpenAI optional. Without keys set, synthesis falls back to deterministic markdown.

Coding Style
- Python 3.11+, Ruff configured in `backend/pyproject.toml`.
- Keep changes focused and minimal. Avoid adding new top‑level abstractions.
- Preserve JSON‑serializable graph state; avoid non‑serializable types in nodes.

Testing Notes
- Some tests assume `/health` and streaming `/explain` exist.
- When adding new nodes, keep names stable to avoid breaking stream messages.

Future Extensions
- Add `/chat` back as a slim endpoint if needed, using the in‑memory analysis context.
- Optional DB persistence (SQLite + SQLAlchemy) can replace in‑memory memory; keep route surface small.

