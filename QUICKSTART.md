# Quick Start Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key

## Setup

### 1. Backend Setup

```bash
cd backend

# Install dependencies
uv sync

# Create .env file
cat > .env << EOF
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o-mini
# Optional: enable Postgres persistence
# DATABASE_URL=postgresql://user:pass@host:5432/dbname
QDRANT_PATH=./qdrant_data
QDRANT_MIN_FILES=10
QDRANT_MIN_BYTES=100000
# Optional: enable in-memory LangGraph checkpointer
# LANGGRAPH_CHECKPOINTER=1
EOF

# Run backend
uv run uvicorn app.main:app --reload --port 8000
```

Backend will be available at: http://localhost:8000

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run frontend
npm run dev
```

Frontend will be available at: http://localhost:3000

## Usage

### Option 1: Web UI

1. Open http://localhost:3000
2. Choose input method:
   - **Paste Code**: Copy/paste code directly
   - **Upload Files**: Drag and drop files
3. Click "Analyze Code"
4. View real-time analysis
5. Chat about the results

### Option 2: API

```bash
# Analyze code
curl -X POST http://localhost:8000/explain \
  -H "Content-Type: application/json" \
  -d '{"code": "def add(a,b): return a+b", "mode": "orchestrator"}'

# Upload files
curl -X POST http://localhost:8000/explain/upload \
  -F "files=@file.py" \
  -F "mode=orchestrator"
```

## Features

- ✅ Expert LLM analysis (security, API, database)
- ✅ Tree-sitter AST detection
- ✅ RAG for large codebases (>10 files)
- ✅ Real-time SSE streaming
- ✅ Thread history
- ✅ Chat interface
- ✅ Multiple input modes

## Troubleshooting

**Backend won't start:**
- Check Python version: `python --version` (need 3.11+)
- Verify OpenAI API key is set
- Check port 8000 is available

**Frontend won't start:**
- Check Node version: `node --version` (need 18+)
- Run `npm install` again
- Check port 3000 is available

**Analysis fails:**
- Verify OpenAI API key is valid
- Check backend logs for errors
- Ensure backend is running

## Next Steps

- Add more files to analyze
- Try the chat feature
- Explore thread history
