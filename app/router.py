"""Deterministic router — maps classifier intent to execution path.

The router is NOT an LLM. No probabilistic decisions are made here.

Phase 0 stub: not yet implemented.
"""

ROUTES: dict[str, str] = {
    "execution": "worker_agent",
    "decomposition": "worker_agent",
    "novel_reasoning": "worker_agent",
    "ambiguous": "clarification",
}


def route(intent: str) -> str:
    """Return the handler name for *intent*. (stub)"""
    raise NotImplementedError("Router not implemented until Phase 1")
