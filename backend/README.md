Backend service with FastAPI + LangGraph. Uses a SQLite LangGraph checkpointer and LangChain LLM cache. Supports SSE streaming to the Next.js frontend.

Quick start
- Create `.env` from `backend/.env.example` and fill keys.
- Start API: `uvicorn backend.main:app --reload`.
 

Notes
- LLM caching (LangChain) is configurable via env:
  - `LLM_CACHE=memory` (default) | `redis` | `redis_semantic` | `none`
  - `REDIS_URL=redis://localhost:6379/0` (used for Redis caches)
  - `LLM_CACHE_TTL=3600` (seconds, Redis caches only)
  - `LLM_CACHE_DISTANCE_THRESHOLD=0.2` (semantic cache similarity)
  - `OPENAI_EMBEDDINGS_MODEL=text-embedding-3-small` (for semantic cache)
  - Redis caches require the `redis` Python client (`pip install redis`).
  - Redis Semantic Cache requires either `langchain-redis` or a recent
    `langchain-community` providing `RedisSemanticCache`. If embeddings or the
    integration are unavailable, the app falls back gracefully to Redis
    exact-match cache or in-memory cache.
- LangGraph SQLite checkpointer is optional. Enable with `LANGGRAPH_CHECKPOINTER=1` (uses `DATABASE_URL`) and install dependency via `pip install langgraph-checkpoint-sqlite` or `pip install .[checkpointer]`.
- Security tools:
  - Semgrep is required for security scanning. Install with:
    - `pip install semgrep` (recommended in your venv), or
    - `brew install semgrep` (macOS)
  - Bandit (Python only): `pip install bandit` (or `brew install bandit`)
