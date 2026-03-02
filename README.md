# local-agentic-platform-poc
This is a PoC - not fit for production use

## Getting Started

### Prerequisites
- Docker with Docker Compose
- (Optional) A devcontainer-capable editor; the `.devcontainer.json` mounts the host Docker socket

### Run the stack

```bash
docker compose up --build
```

| Service    | URL                        | Notes                          |
|------------|----------------------------|--------------------------------|
| OpenWebUI  | http://localhost:3000      | Chat interface                 |
| Ingress API| http://localhost:8000      | Internal orchestration API     |
| Ollama     | http://localhost:11434     | Local LLM runtime              |

### Verify the stub endpoint

```bash
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"input": "hello"}'
# → {"intent":"stub","response":"Phase 0 OK"}
```

### OpenWebUI

1. Browse to http://localhost:3000 and create a local account.
2. Type any message — you should receive the stub response **"Phase 0 OK"**.
3. (Phase 1) Pull a model first: `docker exec ollama ollama pull llama3`

### Run smoke tests (no Docker required)

```bash
pip install -r requirements.txt
pytest tests/test_smoke.py -v
```

---

## Architecture

```
User (browser)
  └─► OpenWebUI  (port 3000)
        └─► POST /v1/chat/completions  (Ingress API, port 8000)
              └─► POST /ingest  (internal orchestration)
                    Phase 0: stub response
                    Phase 1+: Classifier → Router → Worker → Ollama
```

See [PLAN.md](PLAN.md) for the full architecture description.

