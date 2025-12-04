#!/bin/bash

# Start backend server
cd backend

echo "🚀 Starting Code Review Agent Backend..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating one..."
    cat > .env << EOF
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o-mini
QDRANT_PATH=./qdrant_data
QDRANT_MIN_FILES=10
QDRANT_MIN_BYTES=100000
LANGGRAPH_CHECKPOINTER=1
LOG_LEVEL=INFO
EOF
    echo "✅ Created .env file. Please edit it and add your OPENAI_API_KEY"
    echo ""
fi

# Start server (ensure absolute imports like 'backend.app' resolve)
echo "Starting uvicorn server on http://localhost:8000..."
PYTHONPATH=.. uv run uvicorn backend.main:app --reload --port 8000 --host 0.0.0.0
