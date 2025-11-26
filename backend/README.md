Backend service with FastAPI + LangGraph. Supports SSE streaming to the Next.js frontend and optional Celery + Redis offloading for high throughput.

Quick start
- Create `.env` from `backend/.env.example` and fill keys.
- Run Redis locally: `docker run -p 6379:6379 redis`.
- Start API: `uvicorn backend.main:app --reload`.
- Optional: enable Celery by setting `USE_CELERY=1` in `.env` and run a worker:
  - `celery -A backend.app.celery_app.celery_app worker -l info -Q celery -c 2`

Notes
- When `USE_CELERY=1`, requests are streamed via Redis pub/sub from workers.
- Semantic cache uses Redis automatically when reachable; otherwise in-memory.
- LangGraph checkpointer can be enabled by `LANGGRAPH_CHECKPOINTER=1`.
