# Code Explanation Agent - Take Home Project

Build an AI agent that explains code using natural language.

## 🎯 The Challenge

Create an agent that:

1. Accepts code via a chat interface
2. Analyzes and explains the code
3. Answers follow-up questions
4. Streams responses in real-time

**What's provided:**

- ✅ FastAPI skeleton with `/explain` endpoint
- ✅ React frontend with CopilotKit chat UI
- ✅ Groq LLM integration (free API)

**What you implement:**

- ⬜ Agent architecture (how do you structure the code?)
- ⬜ Code analysis logic (AST parsing? LLM prompts? Tools?)
- ⬜ Response streaming
- ⬜ Error handling

## 🚀 Quick Start

### Prerequisites

```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Get free Groq API key
# https://console.groq.com/
```

### Setup

```bash
# Backend
cd backend
uv sync
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# Run
uv run python main.py

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173

## 📋 Requirements

### Minimum (2-3 hours)

Your agent should:

- ✅ Explain what code does (basic understanding)
- ✅ Identify potential issues
- ✅ Suggest improvements
- ✅ Stream responses to the UI
- ✅ Handle errors gracefully

## ✅ Evaluation Criteria

We'll evaluate on:

1. **Code Organization** (30%)

   - How did you structure your code?
   - Is it easy to understand and maintain?
   - Good separation of concerns?

2. **Implementation Quality** (30%)

   - Does it work end-to-end?
   - Clean, readable code?
   - Proper error handling?
   - Type hints used appropriately?

3. **Architecture Decisions** (25%)

   - Smart use of LLM vs traditional parsing?
   - Good tool design (if applicable)?
   - Appropriate abstractions?

4. **Documentation** (15%)
   - Clear README explaining your approach
   - Inline comments where helpful
   - Design decisions documented

## 🔧 Development Commands

```bash
# Run server
uv run python main.py

# Run with auto-reload
uv run uvicorn main:app --reload

# Add a package
uv add package-name

# Run tests (if you add them)
uv run pytest
```

## 📝 Submission Guidelines

### Update This README

Add a new section at the bottom explaining:

1. **Architecture Overview**

   - How did you structure your code?
   - What files did you create and why?

2. **Design Decisions**

   - Why did you choose this approach?
   - What trade-offs did you make?

3. **How It Works**

   - Brief explanation of the flow
   - Key functions/classes

4. **What Would You Improve?**
   - With more time, what would you add?
   - Known limitations?

### Testing

Make sure:

- Both backend and frontend run without errors
- Can paste code and get a response
- Streaming works (not just one big chunk at the end)
- Error messages are helpful

### Code Quality

- Use type hints
- Add docstrings to classes/functions
- Handle edge cases (empty input, invalid code, etc.)
- Clean, readable code

## ❓ Questions?

If anything is unclear, make reasonable assumptions and document them in your README submission.

Good luck! 🚀

---

## 📝 Your Implementation (Fill this in)

### Architecture Overview

_Explain how you structured your code..._

### Design Decisions

_Why did you make the choices you made?..._

### How to Test

_Any specific test cases or scenarios to try?..._

### Future Improvements

_What would you add with more time?..._
