"""Ingress API — entry point for all user requests.

Exposes:
  POST /ingest                  — internal schema used by custom clients
  POST /v1/chat/completions     — OpenAI-compatible shim for OpenWebUI
"""

import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from app.models import IngestRequest, IngestResponse

app = FastAPI(title="Agentic Platform — Ingress API")


# ---------------------------------------------------------------------------
# Internal endpoint
# ---------------------------------------------------------------------------


@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    """Accept user input, orchestrate classification and routing, return response.

    Phase 0: returns a hard-coded stub so the full request path can be verified
    before any LLM integration is in place.
    """
    return IngestResponse(intent="stub", response="Phase 0 OK")


# ---------------------------------------------------------------------------
# OpenAI-compatible shim so OpenWebUI can treat this service as an LLM backend
# ---------------------------------------------------------------------------


class _OAIMessage(BaseModel):
    role: str
    content: str


class _OAIChatRequest(BaseModel):
    model: str = "agentic"
    messages: list[_OAIMessage]
    stream: bool = False


@app.post("/v1/chat/completions")
async def chat_completions(request: _OAIChatRequest) -> dict:
    """Translate an OpenAI chat-completions request into an /ingest call.

    Extracts the last user message, forwards it to the ingest logic, and wraps
    the result in a minimal ChatCompletion-shaped response.
    """
    user_text = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        "",
    )

    result = await ingest(IngestRequest(input=user_text))

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.response},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
