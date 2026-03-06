# PHASE 3 — Observability, Debug Logging, and Router Transparency

## Objective

Phase 3 focuses on **observability and router transparency**.  
The goal is to make the behaviour of the system visible during development so that routing
decisions, classifier outputs, retries, and worker execution can be inspected.

This phase does **not change the core architecture** introduced in Phase 2:
User → Classifier → Router → Worker

Instead, it introduces structured logging, correlation IDs, and debugging tools.

---

# Architecture (unchanged)

User Input
↓
Classifier (LLM)
↓
Intent Router
↓
Worker (LLM)
↓
Response

---

# Key Additions

## 1. Structured Logging

Replace ad‑hoc prints with **structured logs** using the project logger.

Example:

```python
logger.info(
    "intent_router",
    request_id=request_id,
    input=user_input,
    intent=intent,
    route=route,
    confidence=confidence
)
```

### Logging Goals

* Inspect router decisions
* Inspect classifier behaviour
* Detect prompt failures
* Track retries and fallbacks
* Measure latency
* Correlate events per request

---

# 2. Request Correlation IDs

Each incoming request should generate a unique identifier.

Example:

```python
import uuid

request_id = str(uuid.uuid4())
```

The `request_id` should be passed through:

* classifier
* router
* worker
* response logging

Example:

```python
logger.info(
    "request_received",
    request_id=request_id,
    input=user_input
)
```

---

# 3. Classifier Debug Logging

The classifier must log:

### Raw Model Output

```python
logger.debug(
    "classifier_raw_output",
    request_id=request_id,
    output=response_text
)
```

### Parsed Result

```python
logger.info(
    "classifier_result",
    request_id=request_id,
    intent=intent,
    confidence=confidence
)
```

### Retry Events

```python
logger.warning(
    "classifier_retry",
    request_id=request_id,
    reason="invalid_json"
)
```

---

# 4. Router Decision Logging

The router should log how the intent maps to a worker.

Example:

```python
logger.info(
    "intent_router",
    request_id=request_id,
    input=user_input,
    intent=intent,
    route=route,
    confidence=confidence
)
```

If an unknown intent occurs:

```python
logger.warning(
    "router_fallback",
    request_id=request_id,
    intent=intent
)
```

---

# 5. Worker Execution Logs

Each worker execution should produce two logs.

### Worker Start

```python
logger.info(
    "worker_start",
    request_id=request_id,
    worker=worker_name
)
```

### Worker Completion

```python
logger.info(
    "worker_complete",
    request_id=request_id,
    worker=worker_name,
    latency_ms=latency
)
```

---

# 6. Latency Metrics

Capture timing for:

* classifier latency
* worker latency
* full request latency

Example:

```python
start = time.time()
...
latency_ms = int((time.time() - start) * 1000)
```

Example log:

```python
logger.info(
    "classifier_latency",
    request_id=request_id,
    latency_ms=latency_ms
)
```

---

# 7. DEBUG_ROUTER Mode

Add an environment variable:

```
DEBUG_ROUTER=true
```

When enabled:

* classifier prompts can be logged (truncated)
* router decision traces are expanded
* worker prompts are optionally logged

Example:

```python
if DEBUG_ROUTER:
    logger.debug(
        "classifier_prompt",
        request_id=request_id,
        prompt=prompt[:500]
    )
```

---

# 8. Debug Route Inspection Endpoint

Add a development endpoint:

```
GET /debug/routes
```

Returns:

```
{
  "routes": {
    "question_answering": "qa_worker",
    "summarisation": "summary_worker",
    "general": "general_worker"
  }
}
```

Purpose:

* Inspect router configuration
* Validate new intents during development

---

# 9. Logging Schema

Standard log events should include:

| Field | Description |
|------|-------------|
| request_id | Correlation ID |
| event | Log event name |
| input | User input (optional) |
| intent | Classifier result |
| route | Router destination |
| worker | Worker executed |
| latency_ms | Execution time |

---

# 10. Example End‑to‑End Log Trace

```
request_received
classifier_raw_output
classifier_result
intent_router
worker_start
worker_complete
request_complete
```

This allows complete request tracing.

---

# Deliverables

Phase 3 should produce:

* structured logging across the pipeline
* request correlation IDs
* classifier debug visibility
* router decision logging
* worker execution logging
* latency metrics
* DEBUG_ROUTER mode
* `/debug/routes` endpoint
* updated tests

---

# Non‑Goals

Phase 3 **does not introduce**:

* memory
* tool calling
* semantic routing
* vector databases
* multi-agent orchestration

Those are future phases.

---

# Expected Outcome

After Phase 3 you should be able to:

* see why the classifier chose an intent
* see how the router mapped the intent
* inspect worker execution
* detect malformed LLM outputs
* trace every request through the system

