"""Application entrypoint.

Creates FastAPI app, configures CORS/logging, builds the LangGraph, and
includes routers. Heavy logic lives in graph/nodes.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv

    load_dotenv()  # CWD
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)
except Exception:
    pass

from backend.app.api.routes import router as explain_router
from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger, setup_logging
from backend.graph.graph import build_graph

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    # SQLite checkpointer creates its own tables as needed
    setup_logging(settings.LOG_LEVEL)

    # Initialize application DB (Threads/Messages)
    from backend.app.db.db import init_db

    init_db()

    logger.info("Starting Code Explanation Agent (log_level=%s)", settings.LOG_LEVEL)
    app = FastAPI(title="Code Explanation Agent")

    # Enable LangChain's LLM cache (configurable via env).
    # Falls back silently if libraries or backends are unavailable.
    try:  # pragma: no cover - optional
        from langchain.globals import set_llm_cache  # type: ignore

        cache_backend = (settings.LLM_CACHE or "").lower()
        if cache_backend == "none":
            logger.info("LLM cache disabled (LLM_CACHE=none)")
        elif cache_backend == "redis_semantic":
            try:
                # Prefer dedicated redis integration if installed
                try:
                    from langchain_redis import RedisSemanticCache  # type: ignore
                except Exception:  # noqa: BLE001
                    # Fallback to community cache package if available
                    from langchain_community.cache import (  # type: ignore
                        RedisSemanticCache,
                    )

                # Embeddings are required for semantic cache
                try:
                    from langchain_openai import OpenAIEmbeddings  # type: ignore
                except Exception:  # noqa: BLE001
                    OpenAIEmbeddings = None  # type: ignore

                if settings.OPENAI_API_KEY and OpenAIEmbeddings is not None:
                    embeddings = OpenAIEmbeddings(model=settings.OPENAI_EMBEDDINGS_MODEL)
                    cache = RedisSemanticCache(
                        redis_url=settings.REDIS_URL,
                        embeddings=embeddings,
                        distance_threshold=settings.LLM_CACHE_DISTANCE_THRESHOLD,
                        ttl=settings.LLM_CACHE_TTL,
                    )
                    set_llm_cache(cache)
                    logger.info(
                        "LLM semantic cache enabled (Redis), threshold=%s, ttl=%ss",
                        settings.LLM_CACHE_DISTANCE_THRESHOLD,
                        settings.LLM_CACHE_TTL,
                    )
                else:
                    logger.warning(
                        "LLM_CACHE=redis_semantic requested but embeddings unavailable; "
                        "falling back to exact-match Redis cache."
                    )
                    raise RuntimeError("semantic-cache-unavailable")
            except Exception:
                # Fallback to exact-match Redis cache
                try:
                    try:
                        from langchain_redis import RedisCache  # type: ignore
                    except Exception:  # noqa: BLE001
                        from langchain_community.cache import (  # type: ignore
                            RedisCache,
                        )

                    cache = RedisCache(redis_url=settings.REDIS_URL, ttl=settings.LLM_CACHE_TTL)
                    set_llm_cache(cache)
                    logger.info(
                        "LLM cache enabled (Redis exact-match), ttl=%ss",
                        settings.LLM_CACHE_TTL,
                    )
                except Exception:
                    # Final fallback is in-memory
                    from langchain_community.cache import InMemoryCache  # type: ignore

                    set_llm_cache(InMemoryCache())
                    logger.info("LLM cache enabled (in-memory)")
        elif cache_backend == "redis":
            try:
                try:
                    from langchain_redis import RedisCache  # type: ignore
                except Exception:  # noqa: BLE001
                    from langchain_community.cache import RedisCache  # type: ignore

                cache = RedisCache(redis_url=settings.REDIS_URL, ttl=settings.LLM_CACHE_TTL)
                set_llm_cache(cache)
                logger.info(
                    "LLM cache enabled (Redis exact-match), ttl=%ss",
                    settings.LLM_CACHE_TTL,
                )
            except Exception:
                from langchain_community.cache import InMemoryCache  # type: ignore

                set_llm_cache(InMemoryCache())
                logger.info("LLM cache enabled (in-memory)")
        else:
            # Default in-memory cache
            try:
                from langchain_community.cache import InMemoryCache  # type: ignore

                set_llm_cache(InMemoryCache())
                logger.info("LLM cache enabled (in-memory)")
            except Exception:
                pass
    except Exception:
        # Never block app startup due to cache wiring issues
        pass

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Build and store the compiled LangGraph app
    logger.debug("Building LangGraph workflow…")
    app.state.graph_app = build_graph(settings)
    logger.info("LangGraph ready. API routes mounted.")

    # Simple root route
    @app.get("/")
    async def root():  # type: ignore[reportGeneralTypeIssues]
        return {"status": "running"}

    # Include API router
    app.include_router(explain_router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
