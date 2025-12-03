Backend service with FastAPI + LangGraph. Uses a SQLite LangGraph checkpointer and LangChain LLM cache. Supports SSE streaming to the Next.js frontend.

Quick start
- Create `.env` from `backend/.env.example` and fill keys.
- Start API: `uvicorn backend.main:app --reload`.
 

Notes
- LangChain LLM cache is enabled in-memory to avoid repeated model calls.
- LangGraph SQLite checkpointer can be enabled by `LANGGRAPH_CHECKPOINTER=1` (uses `DATABASE_URL`).
- Security tools:
  - Semgrep is required for security scanning. Install with:
    - `pip install semgrep` (recommended in your venv), or
    - `brew install semgrep` (macOS)
  - Bandit (Python only): `pip install bandit` (or `brew install bandit`)
