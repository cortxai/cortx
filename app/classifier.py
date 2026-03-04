"""Classifier agent — calls the LLM to categorise user intent.

Returns strict JSON: {"intent": <str>, "confidence": <float>}

Retries once if the response is not valid JSON; falls back to
intent="ambiguous", confidence=0.0 on second failure.
"""

import json
import logging
from typing import Optional

import httpx
from pydantic import ValidationError

from app.models import ClassifierResponse
from app.settings import settings

logger = logging.getLogger(__name__)

# Prompt header is fixed text; user input is appended via concatenation to
# avoid Python str.format() treating user-supplied braces as placeholders.
_PROMPT_HEADER = """\
Classify the user input below into exactly one intent. Reply with ONLY valid JSON.
Schema: {"intent": "execution|decomposition|novel_reasoning|ambiguous", "confidence": 0.0-1.0}

intent values:
- execution: concrete task with a known, finite deliverable (write, translate, calculate, summarise, explain, code)
  e.g. "Write a haiku", "Summarise X in 3 sentences", "Explain Y in 2 paragraphs", "Translate this", "Write a function"
  NOTE: asking for output in N sentences/words/points is execution, not decomposition.
- decomposition: broad HOW-TO goal requiring a multi-step process or plan
  e.g. "How would I build a SaaS?", "Plan a migration", "Steps to launch a startup"
  NOTE: only use this when the request asks HOW to do something complex, not for a summary or explanation.
- novel_reasoning: open-ended thinking with no single right answer (design, compare, analyse, ethics)
  e.g. "Design an economy for Mars", "Compare capitalism and socialism"
- ambiguous: missing a clear task — a single word, greeting, or fragment with no actionable request
  e.g. "Help.", "Do the thing.", "What about it?", "Hey"
  NOTE: if you cannot tell what the user wants to produce or achieve, choose ambiguous.

User input: """

# Maps common LLM-generated intent variants to valid schema values.
_INTENT_ALIASES: dict[str, str] = {
    "creative_writing": "execution",
    "creative": "execution",
    "generation": "execution",
    "task": "execution",
    "action": "execution",
    "command": "execution",
    "analysis": "novel_reasoning",
    "reasoning": "novel_reasoning",
    "explanation": "novel_reasoning",
    "synthesis": "novel_reasoning",
    "planning": "decomposition",
    "complex": "decomposition",
    "unclear": "ambiguous",
    "unknown": "ambiguous",
    "other": "ambiguous",
}

# Alternative field names some models use instead of "intent".
_INTENT_FIELD_CANDIDATES = ("intent", "category", "type", "classification", "class")


async def classify(user_input: str) -> ClassifierResponse:
    """Classify *user_input* and return a ClassifierResponse.

    Retries once on bad JSON or network error; returns fallback on second failure.
    """
    for attempt in range(2):
        try:
            raw = await _call_ollama(user_input)
        except httpx.HTTPError as exc:
            body = ""
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    body = exc.response.text[:200]
                except Exception:
                    pass
            logger.warning(
                "Classifier attempt %d: %s body=%r %s",
                attempt + 1, type(exc).__name__, body, exc,
            )
            continue
        result = _parse(raw)
        if result is not None:
            return result
        logger.warning("Classifier attempt %d: could not parse response: %r", attempt + 1, raw)

    logger.error("Classifier failed after 2 attempts; returning fallback.")
    return ClassifierResponse(intent="ambiguous", confidence=0.0)


async def _call_ollama(user_input: str) -> str:
    prompt = _PROMPT_HEADER + user_input
    payload = {
        "model": settings.classifier_model,
        "prompt": prompt,
        "format": "json",  # Ollama native JSON mode — constrains token generation to valid JSON
        "stream": False,
        "options": {"temperature": 0, "num_predict": settings.max_tokens},
    }
    logger.info("LLM call 1/2: classifier model=%s", settings.classifier_model)
    async with httpx.AsyncClient(timeout=settings.classifier_timeout) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
        resp.raise_for_status()
        raw = resp.json()["response"]
        logger.debug("Classifier raw response: %r", raw)
        return raw


def _parse(raw: str) -> Optional[ClassifierResponse]:
    text = raw.strip()
    # Strip markdown code fences in case a model ignores the format constraint.
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    # Try strict parse first.
    try:
        return ClassifierResponse(**data)
    except ValidationError:
        pass

    # Normalise: find the intent value under any common field name, then map aliases.
    raw_intent = None
    for field in _INTENT_FIELD_CANDIDATES:
        if field in data:
            raw_intent = str(data[field]).strip().lower().replace(" ", "_").replace("-", "_")
            break

    if raw_intent is None:
        logger.warning("Classifier response has no recognisable intent field: %r", data)
        return None

    intent = _INTENT_ALIASES.get(raw_intent, raw_intent)
    confidence = float(data.get("confidence", data.get("score", data.get("certainty", 0.5))))

    try:
        return ClassifierResponse(intent=intent, confidence=confidence)
    except ValidationError:
        logger.warning(
            "Classifier intent %r (normalised from %r) not in schema; treating as ambiguous",
            intent, raw_intent,
        )
        return ClassifierResponse(intent="ambiguous", confidence=0.0)

