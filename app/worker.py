"""Worker agent — calls the LLM to produce the final user-facing response.

Receives original user input and classifier intent; returns free-form text.
No memory, no tools.
"""

import logging

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)

# Intent-specific prompt templates; user input is appended via concatenation to
# avoid Python str.format() treating user-supplied braces as placeholders.
_PROMPTS: dict[str, str] = {
    "execution": (
        "You are a precise assistant. The user has asked you to perform a concrete task.\n"
        "Give a direct, concise answer. No planning structure. No preamble. No commentary.\n"
        "Respond in no more than 150 words.\n\n"
        "User request: "
    ),
    "planning": (
        "You are a structured assistant. The user needs a task broken into steps.\n"
        "Provide exactly 3 to 5 numbered steps. One sentence per step. No preamble.\n\n"
        "User request: "
    ),
    "analysis": (
        "You are an analytical assistant. The user wants open-ended thinking.\n"
        "Give a focused, insightful response. Limit to 3 sentences.\n\n"
        "User request: "
    ),
}

_FALLBACK_PROMPT = _PROMPTS["execution"]


async def generate(user_input: str, intent: str) -> str:
    """Generate a response for *user_input* given *intent*.

    Raises httpx.HTTPError on network or HTTP failures (caller handles gracefully).
    """
    prompt = _PROMPTS.get(intent, _FALLBACK_PROMPT) + user_input
    payload = {
        "model": settings.worker_model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": settings.max_tokens},
    }
    logger.info("LLM call 2/2: worker model=%s intent=%s", settings.worker_model, intent)
    async with httpx.AsyncClient(timeout=settings.worker_timeout) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["response"]
