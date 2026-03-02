# PLAN.md — Minimal Local Agentic PoC

## Objective

Build a minimal, local-first proof-of-concept demonstrating:
- Deterministic orchestration around LLMs
- Explicit intent classification
- Separation between control logic and model reasoning
- Integration with OpenWebUI as a UI only

This system must be simple, auditable, and runnable on a Mac Mini using Docker.

---

## Non-Goals (Explicitly Out of Scope)

- No cloud APIs
- No long-term memory
- No vector databases
- No tool execution (filesystem, shell, etc.)
- No multi-agent collaboration
- No async queues or background workers

---

## Architecture Overview

User → OpenWebUI → Ingress API → Classifier → Router → Worker Agent → Response

All orchestration logic lives in Python.
LLMs are used only for classification and generation.

---

## Technology Choices

- Python 3.11
- FastAPI
- Ollama HTTP API
- Docker / Docker Compose
- One local 7B–8B model (same model for all roles)

---

## Core Components

### 1. Ingress API (FastAPI)

Responsibilities:
- Accept POST requests containing raw user input
- Orchestrate classification and routing
- Return final response

No business logic should live in LLM prompts.

---

### 2. Classifier Agent (LLM)

Purpose:
- Categorise user intent

Allowed outputs (STRICT JSON ONLY):

```json
{
  "intent": "execution" | "decomposition" | "novel_reasoning" | "ambiguous",
  "confidence": 0.0-1.0
}
```

Rules:
- Stateless
- No tools
- No memory
- No explanations
- Output must be machine-consumable

⸻

### 3. Router (Python)

Purpose:
- Deterministically select execution path based on classifier output

Rules:
- Router is NOT an LLM
- No probabilistic decisions
- Hard-coded mapping is acceptable for PoC

Example logic:
- execution → worker_agent
- decomposition → worker_agent
- novel_reasoning → worker_agent
- ambiguous → clarification response

⸻

### 4. Worker Agent (LLM)

Purpose:
- Produce final user-facing response

Rules:
- No memory
- No tools
- Receives:
- Original user input
- Classifier intent
- Free-form natural language output

⸻

## API Design

### POST /ingest

Request:
```json
{
  "input": "string"
}
```

Response:
```json
{
  "intent": "string",
  "response": "string"
}
```

### OpenWebUI Integration

- OpenWebUI forwards user messages to /ingest
- OpenWebUI displays returned response
- OpenWebUI does NOT manage:
- Agent logic
- Routing
- Memory
- Tools

⸻

### Folder Structure

```text
/app
  main.py          # FastAPI app
  classifier.py    # LLM classification call
  router.py        # Deterministic routing logic
  worker.py        # LLM generation call
  models.py        # Pydantic schemas
  settings.py      # Model names, URLs
Dockerfile
docker-compose.yml
```

### Success Criteria
- System runs locally via Docker
- Classifier returns valid JSON every time
- Router never calls an LLM
- One prompt in → one response out
- Architecture is understandable without diagrams

⸻

### Future Extensions (Not Implemented)

- Planner agent
- Memory tiers
- Tool-enabled agents
- Rate limits and budgets
- Multi-model routing

⸻

## Guiding Principle

“LLMs propose. Code disposes.”

LLMs are not trusted with control flow, persistence, or side effects.

