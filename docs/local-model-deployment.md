# Local Model Deployment Examples

The app remains local/open-source first. Use these examples when moving beyond deterministic hashing/extractive defaults.

## Mac-Host Ollama

When backend and worker run in Docker and Ollama runs directly on the Mac:

```text
LOCAL_MODEL_PROFILE=host-ollama
PUBLIC_LLM_ENABLED=false
```

Pull the expected models on the Mac:

```bash
ollama pull nomic-embed-text
ollama pull llama3.1
ollama list
```

Restart backend and workers:

```bash
docker compose up -d --build backend worker worker-ocr
```

## Compose Ollama

When Ollama runs as the optional Compose service:

```bash
docker compose --profile local-models up -d ollama
docker compose --profile local-models exec ollama ollama pull nomic-embed-text
docker compose --profile local-models exec ollama ollama pull llama3.1
```

Use:

```text
LOCAL_MODEL_PROFILE=compose-ollama
PUBLIC_LLM_ENABLED=false
```

## vLLM GPU Example

The example [infra/local-models/docker-compose.vllm-gpu.example.yml](../infra/local-models/docker-compose.vllm-gpu.example.yml) shows a separate local GPU model stack with:

- vLLM OpenAI-compatible generation endpoint on port `8000`
- local reranker endpoint on port `8081`
- NVIDIA GPU reservation hints

Start the model services from a GPU host:

```bash
docker compose -f infra/local-models/docker-compose.vllm-gpu.example.yml up -d
```

Point the app at those services:

```text
LOCAL_MODEL_PROFILE=vllm-gpu
LOCAL_MODEL_GPU_PROFILE=single-gpu
PUBLIC_LLM_ENABLED=false
```

If the model stack runs on a different host, keep `LOCAL_MODEL_PROFILE=custom` and set explicit URLs:

```text
LOCAL_EMBEDDING_RUNTIME=vllm
LOCAL_EMBEDDING_BASE_URL=http://gpu-host.example.com:8000
LOCAL_LLM_RUNTIME=vllm
LOCAL_LLM_BASE_URL=http://gpu-host.example.com:8000
RERANKER_PROVIDER=local
LOCAL_RERANKER_RUNTIME=cross-encoder
LOCAL_RERANKER_BASE_URL=http://gpu-host.example.com:8081
```

## Health Checks

After any local model switch:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/model-status
python -m app.eval.run
```

The UI model panel should show the selected profile, embedding runtime, answer runtime, vector index, reranker, and latency thresholds.
