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

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.explain import router as explain_router
from graph.graph import build_graph


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    app = FastAPI(title="Code Explanation Agent")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Build and store the compiled LangGraph app
    app.state.graph_app = build_graph(settings)

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
