```markdown
# Code Review Agent — Comprehensive Agent Guidelines

**Scope**: Entire repository  
**Philosophy**: Simple, nimble, production-ready. Routes stay thin; graph nodes and tools do the work. Prefer LangGraph/LangChain primitives over custom frameworks.

---

## 🧠 **Cognitive Architecture: Sequential Thinking Protocol**

Before writing ANY code, you MUST:

1. **Use Sequential Thinking MCP** to break down the task:
   ```
   - Understand: What is the user asking for?
   - Decompose: Break into atomic, sequential steps
   - Dependencies: Identify what needs what
   - Plan: Create a numbered execution plan
   - Execute: Implement step-by-step
   - Verify: Test each step before moving forward
   ```

2. **Use Serena MCP** for context gathering:
   ```
   - Query codebase for existing patterns
   - Find similar implementations
   - Understand data flow and state management
   - Identify integration points
   ```

3. **Use Context 7 MCP** for documentation:
   ```
   - Search official docs for LangGraph, FastAPI, Next.js
   - Find best practices for streaming, async, SSE
   - Reference API specifications
   - Check for deprecated patterns
   ```

### **Execution Order (MANDATORY)**
```
1. Sequential Thinking: Lay out plan
2. Serena: Gather codebase context
3. Context 7: Check official docs
4. Implement: Write code
5. Verify: Test against requirements
```

---

## 🏗️ **Architecture Overview**

### **Backend Stack**
- **Framework**: FastAPI (async-first, SSE streaming)
- **Graph Engine**: LangGraph (stateful workflows with checkpointing)
- **Persistence**: SQLAlchemy + SQLite (optional in-memory fallback)
- **LLM**: OpenAI GPT-4o-mini (streaming-enabled)

### **Graph Flow (backend/graph/graph.py)**
```
START 
  → mode_gate (route: orchestrator|chat)
    ├─ orchestrator:
    │   → router (language detection)
    │   → build_context (normalize inputs)
    │   → tools_parallel (security/quality/AST analysis)
    │   → collector (aggregate tool outputs)
    │   → synthesis (LLM-generated final report)
    │   → persist_thread (save to DB)
    │   → END
    │
    └─ chat:
        → chat_reply (grounded Q&A over saved analysis)
        → END
```

**Key Nodes**:
- **Context** (`backend/graph/nodes/context.py`): Normalizes pasted code, files[], folder paths
- **Tools Parallel** (`backend/graph/nodes/tools_parallel.py`): Runs Bandit, Semgrep, Radon, Vulture, AST concurrently
- **Synthesis** (`backend/graph/nodes/synthesis.py`): Streams LLM-generated markdown report
- **Chat Reply** (`backend/graph/nodes/chat_reply.py`): Conversational follow-ups with memory

---

## 🚀 **API Routes (backend/app/api/routes.py)**

### **Design Principles**
- **Thin routes**: Business logic lives in graph nodes, not routes
- **SSE-first**: All streaming uses Server-Sent Events format
- **Thread-centric**: Every analysis creates a thread for chat continuity

### **Endpoints**

| Method | Path | Purpose | Response Type |
|--------|------|---------|---------------|
| `GET` | `/health` | Health check | JSON |
| `POST` | `/explain` | Stream code analysis | SSE (text/event-stream) |
| `POST` | `/explain/upload` | Upload files for analysis | SSE (text/event-stream) |
| `POST` | `/chat` | Chat about analysis | Plain text stream |
| `GET` | `/threads` | List recent threads | JSON |
| `GET` | `/threads/{id}` | Get thread details | JSON |

### **SSE Contract (Critical for Frontend)**

**Format**:
```
data: tent>\n\n
```

**Special Markers**:
- `:::progress: N` → Progress updates (0-100)
- `:::done` → Stream completion signal
- `🔎`, `📚`, `🧪`, `🧠` → Progress emojis for UX

**Example Stream**:
```
data: :::progress: 5\n\n
data: 🚀 Starting analysis...\n\n
data: :::progress: 20\n\n
data: 📚 Context: 3 files (1024 bytes)\n\n
data: :::progress: 90\n\n
data: # Code Review Report\n\n
data: \n\n
data: ## Security Analysis\n\n
data: Found 2 vulnerabilities...\n\n
data: :::done\n\n
```

---

## 💾 **Persistence Layer (backend/app/db/)**

### **Models** (`backend/app/db/models.py`)
```
class Thread:
    id: str (UUID)
    title: str
    created_at: datetime
    updated_at: datetime  # ⚠️ Required for sorting
    report_text: str (markdown)
    state_json: dict (full graph state)
    file_count: int

class Message:
    id: int
    thread_id: str (FK)
    role: 'user' | 'assistant'
    content: str (markdown)
    created_at: datetime
```

### **Repository API** (`backend/app/db/repository.py`)
```
# Thread management
repo.create_thread(thread_id: str, title: str) → Thread
repo.update_thread(thread_id, report_text, state, file_count) → Thread
repo.get_thread(thread_id: str) → Thread | None
repo.list_threads(limit: int = 50) → list[Thread]

# Message management (for chat)
repo.add_message(thread_id: str, role: str, content: str) → Message
repo.get_messages(thread_id: str) → list[Message]
```

### **Configuration**
```
# SQLite (default)
DATABASE_URL=sqlite:///./data/threads.db

# In-memory (no persistence)
# DATABASE_URL not set

# PostgreSQL (production)
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

---

## 🛠️ **Tools & Analysis**

### **Security Tools** (`backend/tools/security_tooling.py`)
- **Bandit**: Python security linter (subprocess wrapper)
- **Semgrep**: Static analysis for vulnerabilities
- Output: JSON → structured `security_report`

### **Quality Tools**
- **Radon**: Cyclomatic complexity, maintainability index
- **Vulture**: Dead code detection
- Output: Metrics → `quality_report`

### **AST Tools** (`backend/graph/tools/ast_tools.py`)
- **Python AST**: Extract functions, classes, imports
- Output: Code structure → `ast_report`

### **Tool Execution** (`backend/graph/nodes/tools_parallel.py`)
```
# All tools run concurrently using asyncio.gather()
async def tools_parallel(state: AgentState) -> AgentState:
    results = await asyncio.gather(
        run_bandit(state["code"]),
        run_semgrep(state["code"]),
        run_radon(state["code"]),
        # ... more tools
    )
    state["security_report"] = merge_security(results)
    state["quality_report"] = merge_quality(results)
    return state
```

---

## ⚡ **Performance & Optimization**

### **Streaming Best Practices**

1. **Backend (FastAPI)**:
```
from fastapi.responses import StreamingResponse

async def event_stream() -> AsyncGenerator[str, None]:
    # ✅ Yield immediately, don't batch
    yield sse(":::progress: 5")
    
    # ✅ Stream LLM tokens as they arrive
    async for event in graph.astream_events(state, version="v2"):
        if event["event"] == "on_chat_model_stream":
            token = event["data"]["chunk"].content
            yield sse(token)
    
    yield sse(":::done")

def sse(data: str) -> str:
    """Format as SSE: 'data: <payload>\n\n'"""
    return f"data: {data}\n\n"
```

2. **Frontend (React)**:
```
// ✅ Use refs to avoid batching
const dataRef = useRef<string>('');
const [renderTrigger, setRenderTrigger] = useState(0);

// ✅ Force re-render with flushSync
import { flushSync } from 'react-dom';

for (const line of lines) {
  if (line.startsWith('data: ')) {
    const content = line.slice(6);
    dataRef.current += content;
    flushSync(() => setRenderTrigger(prev => prev + 1));
  }
}
```

### **LangGraph Optimization**

```
# ✅ Use astream_events v2 for best performance
async for event in graph.astream_events(state, version="v2"):
    # Lower overhead than v1
    pass

# ✅ Stream only changed fields
graph.astream(state, stream_mode="updates")  # Not "values"

# ✅ Enable checkpointing for resumable workflows
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
graph = graph.compile(checkpointer=checkpointer)
```

---

## 🎯 **Coding Standards**

### **Python (Backend)**

**Style**: PEP 8 + Ruff configuration in `backend/pyproject.toml`

```
# ✅ DO: Type hints everywhere
async def process_code(code: str, language: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    return result

# ✅ DO: Async for I/O operations
async def fetch_data() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    return response.text

# ✅ DO: Explicit error handling
try:
    result = await risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise

# ❌ DON'T: Bare except blocks
try:
    risky()
except:  # Too broad!
    pass

# ✅ DO: Structured logging
logger.info("Analysis started", extra={
    "thread_id": thread_id,
    "file_count": len(files)
})

# ❌ DON'T: Print statements
print("Debug info")  # Use logger instead
```

### **TypeScript (Frontend)**

```
// ✅ DO: Explicit types
interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
}

// ✅ DO: Error boundaries
try {
  const data = await fetchData();
} catch (error) {
  if (error instanceof TypeError) {
    // Handle type error
  }
  throw error;
}

// ✅ DO: Proper cleanup
useEffect(() => {
  const controller = new AbortController();
  
  fetchData(controller.signal);
  
  return () => controller.abort();  // Cleanup
}, [dependency]);

// ❌ DON'T: Ignore dependencies
useEffect(() => {
  fetchData();
}, []);  // Missing dependencies!
```

### **Async Patterns**

```
# ✅ DO: Concurrent execution
results = await asyncio.gather(
    task1(),
    task2(),
    task3()
)

# ❌ DON'T: Sequential when parallel is possible
result1 = await task1()  # Waits
result2 = await task2()  # Could run concurrently!
result3 = await task3()

# ✅ DO: Timeout protection
async with asyncio.timeout(30):
    result = await long_operation()

# ✅ DO: Proper resource cleanup
async with aiofiles.open('file.txt') as f:
    data = await f.read()
```

---

## 🧪 **Testing & Quality**

### **Test Structure**
```
backend/tests/
├── test_graph_nodes.py       # Unit tests for nodes
├── test_tools.py              # Tool wrapper tests
├── test_api_routes.py         # Integration tests
└── test_streaming.py          # SSE format validation
```

### **Critical Tests**

```
# 1. SSE Format Validation
def test_sse_format():
    stream = explain_endpoint(code="def foo(): pass")
    for line in stream:
        assert line.startswith("data: ")
        assert line.endswith("\n\n")

# 2. Thread Persistence
async def test_thread_persistence():
    thread_id = await create_thread()
    thread = repo.get_thread(thread_id)
    assert thread is not None
    assert thread.updated_at is not None  # Critical!

# 3. Chat Context
async def test_chat_context():
    messages = [
        {"role": "user", "content": "What is X?"},
        {"role": "assistant", "content": "X is..."},
        {"role": "user", "content": "Explain more"}
    ]
    response = await chat(thread_id, messages)
    # Should reference previous answer
    assert "X" in response or "as mentioned" in response
```

---

## 📦 **Environment Configuration**

### **Backend (.env)**
```
# Required
OPENAI_API_KEY=sk-...

# Optional
OPENAI_MODEL=gpt-4o-mini         # Default model
OPENAI_TEMPERATURE=0.3           # For synthesis
DATABASE_URL=sqlite:///data.db   # Persistence
LANGGRAPH_CHECKPOINTER=1         # Enable checkpointing
LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR

# Production
CORS_ORIGINS=https://app.com     # Comma-separated
MAX_FILE_SIZE=10485760           # 10MB limit
```

### **Frontend (.env.local)**
```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 🚀 **Development Workflow**

### **Setup**
```
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
make run-backend

# Frontend
cd frontend
pnpm install
pnpm dev
```

### **Common Tasks**

```
# Run backend with hot reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest backend/tests/ -v

# Format code
ruff format backend/
ruff check backend/ --fix

# Database migrations (if using Alembic)
alembic revision --autogenerate -m "Add updated_at column"
alembic upgrade head
```

---

## 🐛 **Debugging Guide**

### **Common Issues**

**1. "No messages yet" despite successful stream**
```
// Problem: React batching state updates
// Solution: Use refs + flushSync (see Performance section)
```

**2. "Chat not working"**
```
// Problem: Only sending current message, not full history
// Solution: Send full conversation array
body: JSON.stringify({
  messages: conversationHistory,  // Not just [currentMessage]
})
```

**3. "Thread not persisting"**
```
-- Problem: Missing updated_at column
-- Solution: Run migration
ALTER TABLE threads ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

**4. "Streaming stops mid-response"**
```
# Problem: Exception not caught
# Solution: Wrap in try/except
try:
    async for event in graph.astream_events(...):
        yield sse(event)
except Exception as e:
    logger.error(f"Stream failed: {e}")
    yield sse(f"Error: {e}")
```

### **Logging Strategy**

```
# Add correlation IDs for tracing
logger.info(
    "Request started",
    extra={
        "thread_id": thread_id,
        "request_id": request.headers.get("x-request-id"),
        "user_agent": request.headers.get("user-agent")
    }
)

# Log at decision points
logger.debug(f"Router detected language: {language}")
logger.info(f"Tools completed in {elapsed:.2f}s")
logger.warning(f"No security issues found (unusual?)")
logger.error(f"LLM call failed: {error}", exc_info=True)
```

---

## 📚 **Frontend Integration Notes**

See `code-docs/frontend-changes.md` for:
- Thread sidebar implementation
- Folder upload UI
- SSE parsing in React hooks
- Chat interface with streaming
- Progress bars and loading states

**Key Files**:
- `frontend/lib/hooks/useSSEStream.ts` - SSE parser
- `frontend/components/ChatInterface.tsx` - Chat UI
- `frontend/app/api/chat/route.ts` - Proxy to backend

---

## 🎓 **Best Practices Checklist**

Before submitting code, verify:

- [ ] Used Sequential Thinking MCP to plan approach
- [ ] Queried Serena MCP for existing patterns
- [ ] Checked Context 7 MCP for official docs
- [ ] All functions have type hints (Python) or interfaces (TypeScript)
- [ ] Async operations use proper concurrency (not sequential)
- [ ] Error handling is explicit (no bare `except:`)
- [ ] SSE format validated (`data: ` prefix, `\n\n` terminator)
- [ ] Thread persistence includes `updated_at` timestamp
- [ ] Chat sends full conversation history
- [ ] Logging uses structured format with context
- [ ] Tests cover happy path + error cases
- [ ] No hardcoded secrets (use environment variables)
- [ ] CORS configured correctly for production
- [ ] Resource cleanup (abort controllers, file handles)

---

## 📞 **Support & Resources**

- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **FastAPI Streaming**: https://fastapi.tiangolo.com/advanced/custom-response/
- **SSE Spec**: https://html.spec.whatwg.org/multipage/server-sent-events.html
- **React Streaming**: https://react.dev/reference/react-dom/flushSync

---

**Last Updated**: December 3, 2025  
**Maintained By**: Development Team  
**Version**: 2.0 (Hyper-charged Edition)
```