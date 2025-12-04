from __future__ import annotations

"""Chat context enrichment node for RAG-based retrieval.

When a vectorstore exists for the thread, retrieves relevant code chunks
to enhance chat responses with specific code context.
"""

import logging
from typing import Any

from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


def chat_context_enrich_node(state: dict[str, Any]) -> dict[str, Any]:
    """Retrieve relevant code chunks for chat query using RAG.

    Parameters
    ----------
    state : dict[str, Any]
        Graph state containing vectorstore_id and chat_query

    Returns
    -------
    dict[str, Any]
        Updated state with chat_context_docs
    """
    settings = get_settings()
    vectorstore_id = state.get("vectorstore_id")
    chat_query = state.get("chat_query", "").strip()

    # Skip if no vectorstore or no query
    if not vectorstore_id or not chat_query:
        logger.debug("Chat context enrich: No vectorstore or query, skipping")
        return {}

    # Skip if OpenAI not available
    if not settings.OPENAI_API_KEY:
        logger.warning("Chat context enrich: OpenAI not available")
        return {}

    try:
        # Initialize Qdrant client
        qdrant_path = settings.QDRANT_PATH
        if qdrant_path == ":memory:":
            logger.warning("Chat context enrich: In-memory Qdrant not persistent, skipping")
            return {}

        client = QdrantClient(path=qdrant_path)

        # Check if collection exists
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if vectorstore_id not in collection_names:
            logger.debug("Chat context enrich: Collection %s not found", vectorstore_id)
            return {}

        # Embed query
        embeddings = OpenAIEmbeddings()
        query_vector = embeddings.embed_query(chat_query)

        # Search for relevant chunks
        results = client.search(
            collection_name=vectorstore_id,
            query_vector=query_vector,
            limit=5,
        )

        # Format results
        context_docs = []
        for result in results:
            payload = result.payload or {}
            path = payload.get("path", "unknown")
            text = payload.get("text", "")
            score = result.score

            context_docs.append(
                {
                    "path": path,
                    "text": text,
                    "score": float(score),
                }
            )

        logger.info(
            "Chat context enrich: Retrieved %d chunks for query: %s",
            len(context_docs),
            chat_query[:50],
        )

        return {"chat_context_docs": context_docs}

    except Exception as e:  # pragma: no cover
        logger.error("Chat context enrich: Failed to retrieve context: %s", e)
        return {}
