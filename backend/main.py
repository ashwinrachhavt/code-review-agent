"""
Code Explanation Agent - Backend

TODO: Implement your agent that:
1. Receives code via the /explain endpoint
2. Analyzes the code using LLM and/or tools
3. Streams back an explanation

You decide:
- How to structure your code (separate files? classes? functions?)
- What tools/utilities to create
- How to organize imports and modules
- Whether to use LangChain's agent framework or roll your own

Document your decisions in the README!
"""

import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Code Explanation Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class CopilotRequest(BaseModel):
    messages: list[Message]


@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/explain")
async def explain_code(request: CopilotRequest) -> StreamingResponse:
    """
    Main endpoint - implement your agent logic here!
    
    The request contains:
    - messages: list of conversation messages
    - messages[-1]: the latest user message (contains code to explain)
    
    You should:
    1. Extract the code from the user's message
    2. Analyze it (using LLM, tools, or both)
    3. Stream the response back
    
    TODO: Replace this placeholder with your implementation
    """
    
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            user_message = request.messages[-1].content
            
            # TODO: Your agent implementation here!
            # Ideas:
            # - Create an agent class in a separate file
            # - Use LangChain tools
            # - Parse the code with AST
            # - Call Groq LLM
            # - Stream responses
            
            placeholder = f"""# Welcome to Code Explanation Agent

You sent: {user_message[:100]}...

## Your Task:
Implement the agent logic to analyze and explain code!

## Next Steps:
1. Structure your code (agent.py? tools/? utils/?)
2. Initialize Groq LLM from environment variables
3. Implement code analysis logic
4. Stream real responses here
5. Document your approach in README

Good luck! 🚀
"""
            
            for char in placeholder:
                yield char
                
        except Exception as e:
            logger.exception("Error in explain_code")
            yield f"\n\n❌ Error: {str(e)}"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain"
    )


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
