# Implementation Description — Local Agentic Platform PoC

> This document describes the current state of the implementation as of v0.2.0 (Phase 4) completion.
> It is intended to be read as context by an LLM when planning future phases of the project.

---

## Purpose

This is a proof-of-concept for a **local agentic platform** that routes user requests through a
two-stage LLM pipeline (classifier → worker) using locally-hosted models via
[Ollama](https://ollama.com), then passes the agent's JSON output through a deterministic tool
execution layer. It is not production-ready.

---

## High-Level Architecture

```
User (browser)
  └─► OpenWebUI  (port 3000)
        └─► POST /v1/chat/completions  ← OpenAI-compatible shim
              └─► POST /ingest         ← internal orchestration entry point
                    ├─► Classifier LLM call (Ollama /api/chat)   → intent + confidence
                    ├─► Router (pure Python, no LLM)             → handler name
                    └─► Worker LLM call (Ollama /api/generate)   → JSON action envelope
                                │
                           parse_agent_output                     → AgentAction
                                │
                           ToolExecutor.execute                   → tool result or direct content
```

- **Ollama** runs on the host machine (not in Docker). The ingress container reaches it via
  `host.docker.internal:11434` on Mac/Windows, or via `host-gateway` on Linux.
- **OpenWebUI** is a pre-built chat UI that talks to the ingress API via the OpenAI-compatible
  `/v1/chat/completions` shim.
- **Ingress API** is a FastAPI service that owns all orchestration logic.

---

## Invariants (Architectural Constraints)

These constraints were established across phases and must remain true:

1. Single orchestration entry point: `POST /ingest`
2. Exactly **two LLM calls** per successful (non-ambiguous) request:
   - Call 1: Classifier → intent classification
   - Call 2: Worker → JSON action envelope generation
3. Router is **pure Python** — no LLM calls, no probabilistic decisions
4. **No memory layer** — each request is stateless
5. **Agents never execute tools directly** — only `ToolExecutor` can run tools
6. **No autonomous planning loops**
7. Worker prompts use string concatenation for user input — never `str.format()` or f-strings

---

## File Structure

```
app/
  __init__.py       — empty package marker
  main.py           — FastAPI app, /ingest endpoint, /v1/chat/completions shim, /debug/routes, /health
  models.py         — Pydantic schemas: ClassifierResponse, IngestRequest, IngestResponse
  classifier.py     — Classifier agent: deterministic prefix checks + LLM call to Ollama
  router.py         — Deterministic intent→handler mapping (pure Python dict lookup)
  worker.py         — Worker agent: intent-aware prompt selection + LLM call to Ollama
  settings.py       — Pydantic-settings config loaded from env vars or .env file

core/
  __init__.py       — empty package marker
  tools.py          — Tool, ToolRegistry, AgentAction, ToolExecutor, parse_agent_output

tools/
  __init__.py       — empty package marker
  filesystem.py     — read_file tool implementation

bootstrap_tools.py  — ToolRegistry singleton; registers all tools at startup

tests/
  test_smoke.py     — All tests (unit + integration via TestClient, Ollama fully mocked)

Dockerfile          — python:3.11-slim, runs uvicorn on port 8000
docker-compose.yml  — ingress + openwebui services on an isolated bridge network
requirements.txt    — fastapi, uvicorn, httpx, pydantic, pydantic-settings, pytest
pytest.ini          — sets pythonpath = . so app.*, core.*, tools.* imports resolve without install
```

---

## Module Detail

### `app/settings.py`

Pydantic `BaseSettings` subclass. All values are overridable via environment variables
(case-insensitive) or a `.env` file.

| Setting               | Default                              | Purpose                              |
|-----------------------|--------------------------------------|--------------------------------------|
| `ollama_base_url`     | `http://host.docker.internal:11434`  | Base URL for all Ollama API calls    |
| `classifier_model`    | `llama3.2:3b`                        | Model used by the classifier agent   |
| `worker_model`        | `llama3.2:3b`                        | Model used by the worker agent       |
| `classifier_timeout`  | `60` (seconds)                       | httpx timeout for classifier call    |
| `worker_timeout`      | `300` (seconds)                      | httpx timeout for worker call        |
| `max_tokens`          | `256`                                | `num_predict` passed to worker       |
| `ingress_port`        | `8000`                               | Informational only (not used in code)|
| `log_level`           | `INFO`                               | Python logging level                 |
| `debug_router`        | `false`                              | When `true`, log classifier/worker prompts at DEBUG level |

A singleton `settings` instance is imported by all modules.

---

### `app/models.py`

Three Pydantic v2 models:

- **`ClassifierResponse`** — `intent: Literal["execution", "planning", "analysis", "ambiguous"]`,
  `confidence: float`. The `Literal` constraint enforces the valid intent vocabulary.
- **`IngestRequest`** — `input: str`. A `field_validator` rejects empty or whitespace-only strings
  (returns HTTP 422 if violated).
- **`IngestResponse`** — `intent: str`, `confidence: float`, `response: str`. The `intent` field
  here is a plain `str` (not `Literal`) so failure paths can write `"ambiguous"` without schema
  gymnastics.

---

### `app/classifier.py`

The classifier agent assigns an intent label and confidence score to raw user input.

**Stage 1 — Deterministic prefix check (no LLM)**

Before calling the LLM, the input is lowercased and matched against hard-coded prefix tuples:

- `_EXECUTION_PREFIXES`: `("write", "generate", "create", "compose", "draft", "produce",
  "summarise", "summarize", "translate", "calculate", "code", "list")` → returns
  `intent="execution", confidence=0.95` immediately.
- `_PLANNING_PREFIXES`: `("how do i", "how would i", "how can i", "what steps")` → returns
  `intent="planning", confidence=0.95` immediately.
- `_AMBIGUOUS_SHORT`: `("help", "hi", "hello", "hey", "ok", "okay", "thanks")` → returns
  `intent="ambiguous", confidence=0.95` immediately.

**Stage 2 — LLM call via `_call_ollama()`**

If no prefix matches, the LLM is called via Ollama `/api/chat`. Up to **2 attempts** are made.
Falls back to `ClassifierResponse(intent="ambiguous", confidence=0.0)` after 2 failures.

**`_parse()` normalisation:** strip markdown fences → `json.loads` → strict Pydantic parse →
field-name scan → alias map → graceful `ambiguous` fallback.

---

### `app/router.py`

A single dict lookup:

```python
ROUTES = {
    "execution": "worker",
    "planning":  "worker",
    "analysis":  "worker",
    "ambiguous": "clarify",
}
```

Any intent not in the dict maps to `"clarify"`. The handler name is returned as a plain string.

---

### `app/worker.py`

Generates the final user-facing response. Intent-aware via three prompt templates in `_PROMPTS`.

All prompts instruct the LLM to return a JSON action envelope:
```json
{"action": "respond", "content": "..."}
```
or a tool call:
```json
{"action": "tool", "tool": "<name>", "args": {"<key>": "<value>"}}
```

User input is **appended** to the prompt string via `+` — never `str.format()`.

`generate()` raises `httpx.HTTPError` on failure; the caller (`main.py`) handles gracefully.

---

### `core/tools.py`

The tool execution layer. Exports:

- **`Tool`** — `@dataclass` with `name`, `description`, `input_schema`, `function`. `execute(args)`
  calls the function and logs `event=tool_execute` / `event=tool_execute_complete`.
- **`ToolRegistry`** — dict-backed registry. `register()` raises `ValueError` on duplicates.
  `get()` raises `ValueError` for unknown tools (logs `event=tool_lookup_failed`).
- **`AgentAction`** — typed wrapper for agent JSON output: `action`, `tool`, `args`, `content`.
  `from_dict()` is the primary constructor, parses from a raw dict.
- **`ToolExecutor`** — dispatches on `action.action`: `"respond"` returns `action.content`
  directly; `"tool"` looks up the tool and calls it; anything else raises `ValueError`.
- **`parse_agent_output(raw)`** — parses a JSON string into `AgentAction`. Logs
  `event=agent_output_received`. Raises and logs `event=agent_output_parse_error` on failure.

---

### `bootstrap_tools.py`

Creates the `tool_registry = ToolRegistry()` singleton and registers:

| Tool name   | Function            | Args              | Description                   |
|-------------|---------------------|-------------------|-------------------------------|
| `read_file` | `tools.filesystem.read_file` | `path: string` | Read a local file by path |

Imported by `app/main.py` at startup. Add new tools here.

---

### `tools/filesystem.py`

`read_file(path: str) -> str` — reads and returns the text content of a file. Returns
`"File not found: <path>"` if the file does not exist (never raises).

---

### `app/main.py`

The FastAPI application.

#### `POST /ingest`

Pipeline:

1. Generate `request_id = uuid4().hex`; log `event=request_received`
2. `classify(request.input, request_id)` → `ClassifierResponse`
3. `route(...)` → handler name
4. If handler is `"clarify"`: set `response_text = _CLARIFY_RESPONSE` (no LLM call)
5. If handler is `"worker"`:
   - Log `event=agent_selected agent=worker`
   - Call `generate(request.input, intent, request_id)` → raw JSON string
   - Try `parse_agent_output(raw)` → `AgentAction`
     - On `json.JSONDecodeError`: treat raw text as direct response (graceful fallback)
     - On `ValueError` (unknown tool/action): log `event=tool_execution_error`, return `_WORKER_FAILURE_RESPONSE`
   - Call `executor.execute(action)` → response text
   - On `httpx.HTTPError`: log `event=worker_error`, return `_WORKER_FAILURE_RESPONSE` with `intent="ambiguous", confidence=0.0`
6. Log `event=request_complete` with timing
7. Return `IngestResponse`

**Module-level:** `executor = ToolExecutor(tool_registry)` is instantiated once at import time.

---

## Testing

All tests are in `tests/test_smoke.py`. 61 tests covering all components.

**Test runner:** `pytest tests/test_smoke.py -v`

Async tests use `@pytest.mark.anyio`. All Ollama calls are mocked with `AsyncMock`.

---

## Infrastructure

### Dockerfile

- Base image: `python:3.11-slim`
- Workdir: `/workspace`
- Copies: `requirements.txt`, `app/`, `core/`, `tools/`, `bootstrap_tools.py`
- Entry point: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### `docker-compose.yml`

Two services on an isolated `agentic` bridge network: `ingress` (port 8000) and `openwebui`
(port 3000). OpenWebUI has `ENABLE_OLLAMA_API=false` so it can only use the ingress shim.

---

## What Has Been Done

- **Phase 1**: Skeleton FastAPI service, `/ingest`, classifier LLM call, deterministic router,
  basic worker LLM call, smoke tests, Docker/Compose setup, OpenWebUI integration.
- **Phase 2**: Intent-aware worker prompts, classifier hardening (prefix checks, alias
  normalisation, field-name scanning, markdown fence stripping, retry-with-fallback), graceful
  worker failure handling, expanded test suite.
- **Phase 3**: Request correlation IDs, structured log events (`event=` prefix), `DEBUG_ROUTER`
  env var, `GET /debug/routes` endpoint, latency in milliseconds.
- **Phase 4 (v0.2.0)**: Tool execution layer (`core/tools.py`) with `Tool`, `ToolRegistry`,
  `AgentAction`, `ToolExecutor`, `parse_agent_output`; `tools/filesystem.py` with `read_file`;
  `bootstrap_tools.py` registering all tools; updated worker prompts to request JSON action
  envelopes; integrated executor into `POST /ingest` pipeline; `event=agent_selected` log;
  graceful JSON parse fallback for non-JSON LLM responses; updated Dockerfile to copy new
  directories; 18 new tests covering the entire tool layer.

---

## What Has NOT Been Built (Non-Goals so far)

- Memory / conversation history
- Streaming responses
- Multi-agent coordination
- Task Graph / Planner orchestration
- Authentication / authorisation
- Persistent storage of any kind
- Rate limiting
- Multiple model backends (only Ollama supported)
- Async concurrency beyond what FastAPI/httpx provide naturally
- Separate classifier and worker model instances (both default to the same model)

