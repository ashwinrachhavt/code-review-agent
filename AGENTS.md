Code Review Agent — Agent Guidelines

Scope: Entire repository

Purpose
- Keep the backend simple, nimble, and useful. Routes stay thin; graph nodes and tools do the work. Prefer LangGraph/LangChain primitives over custom frameworks.

Architecture
- Graph (backend/graph/graph.py)
  - Flow: START → mode_gate → (chat_reply | router) → context → tools_parallel → synthesis → persist → END
  - Checkpointer: optional SQLite saver (backend/graph/memory/sqlite_checkpoint.py) gated by `LANGGRAPH_CHECKPOINTER=1`.
- Context node (backend/graph/nodes/context.py)
  - Normalizes inputs across modalities
  - Outputs files list, context summary, aggregated code sample
- Tools node (backend/graph/nodes/tools_parallel.py)
  - Runs in parallel: Bandit, Semgrep, Radon, Vulture, Python AST
  - Aggregates security_report, quality_report, ast_report
- Synthesis (backend/graph/nodes/synthesis.py)
  - Collector LLM (or markdown fallback) builds final_report
- Chat (backend/graph/nodes/chat_reply.py)
  - Concise reply grounded in saved analysis

Routes (backend/app/api/routes.py)
- GET /health → health check
- POST /explain (SSE)
  - Accepts: pasted code or files[] + source ('folder' | 'pasted' | 'cli')
  - Streams: progress markers, router/context/tools notifications, final report paragraphs
  - Persists thread (state + report)
  - Sets `x-thread-id` response header
- POST /chat (text stream)
  - Chats over the persisted analysis; persists assistant replies
- GET /threads (JSON)
  - Lists recent threads for sidebar
- GET /threads/{id} (JSON)
  - Returns a thread with state + messages

Persistence
- Repository API (backend/app/db/repository.py)
  - Defaults to in-memory, switches to SQLAlchemy (SQLite) if installed
  - Models (backend/app/db/models.py): Thread, Message
  - Config: `DATABASE_URL=sqlite:///backend/data.db` by default

SSE Contract
- Prefix: every line begins with `data: `
- Progress markers: `:::progress: N`
- Messages: `🔎 Router: language detection done.`, `📚 Context ready.`, `🧪 Tools complete.`
- Final: synthesis paragraphs

Tools
- Security wrappers: backend/tools/security_tooling.py
- LC Tool exports: backend/graph/tools/security_tools.py, backend/graph/tools/radon_tool.py
- AST utilities: backend/graph/tools/ast_tools.py

Dev Commands
- Install backend: `make install-backend`
- Run backend: `make run-backend`
- Environment:
  - Optional LLM: `OPENAI_API_KEY`, `OPENAI_MODEL` (default gpt-4o-mini)
  - Optional checkpointer: `LANGGRAPH_CHECKPOINTER=1`
  - Database: `DATABASE_URL` (SQLite by default)

Coding Style
- Python 3.11+, Ruff configuration in backend/pyproject.toml
- Keep JSON-serializable graph state; avoid non-serializable types
- Prefer small, composable nodes; keep routes thin

Testing & Stability
- Keep node names stable to preserve stream messages consumed by the frontend
- Validate SSE format (data: prefix) and `:::progress:` handling

Frontend Notes
- See `code-docs/frontend-changes.md` for required UI/API proxy updates (threads, folder upload, SSE handling)
