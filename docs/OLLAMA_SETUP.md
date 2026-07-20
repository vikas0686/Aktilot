# Running Ollama locally with Docker Compose

Aktilot can use [Ollama](https://ollama.com) as a fully local, air-gapped LLM and embedding
provider — no API key required. This guide walks through adding the `ollama` service to
`docker-compose.yml` so it starts alongside the rest of the stack.

## 1. Add the services

Open `docker-compose.yml` and add the following two services under the
`# ── Application Stack ──` section (anywhere alongside `postgres`, `temporal`, etc.):

```yaml
  ollama:
    image: ollama/ollama:latest
    profiles: ["ollama"]
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD-SHELL", "ollama list || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  ollama-model:
    image: curlimages/curl:latest
    profiles: ["ollama"]
    depends_on:
      ollama:
        condition: service_healthy
    entrypoint: ["sh", "-c"]
    command:
      - |
        set -eu
        until curl -fsS http://ollama:11434/api/tags > /dev/null; do sleep 1; done
        curl -fsS http://ollama:11434/api/pull -d '{"name": "${CHAT_MODEL:-llama3.2}"}'
        curl -fsS http://ollama:11434/api/pull -d '{"name": "${EMBEDDING_MODEL:-nomic-embed-text}"}'
    restart: "no"
```

- **`ollama`** runs the Ollama server itself, exposed on `localhost:11434`, with its model
  data persisted in the `ollama_data` volume.
- **`ollama-model`** is a one-shot helper that waits for `ollama` to become healthy, then
  pulls the chat and embedding models named by `CHAT_MODEL` / `EMBEDDING_MODEL` (falling back
  to `llama3.2` and `nomic-embed-text`). It exits once the pull completes and does not restart.

Both services are gated behind the `ollama` [Compose profile](https://docs.docker.com/compose/how-tos/profiles/),
so they never start unless you explicitly request that profile — the default
`docker compose up` is unaffected.

## 2. Declare the volume

Make sure `ollama_data` is listed under the top-level `volumes:` block:

```yaml
volumes:
  # ...existing volumes...
  ollama_data:
```

## 3. Configure environment variables

Copy `.env.example` to `.env` (if you haven't already) and set:

```bash
LLM_PROVIDER=ollama
CHAT_MODEL=llama3.2
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://ollama:11434
```

`OLLAMA_BASE_URL` uses the Compose service name `ollama` as the hostname so the `backend`
and `worker` containers can reach it over the Compose network.

## 4. Start the stack with the `ollama` profile

```bash
docker compose --profile ollama up --build
```

On first run, `ollama-model` will pull the configured models — this can take a few minutes
depending on model size and your connection. Subsequent runs reuse the models already
persisted in the `ollama_data` volume.

## Verifying it worked

```bash
curl http://localhost:11434/api/tags
```

should list the pulled models. You can also check container health with:

```bash
docker compose ps ollama
```

## Notes

- Running local models requires enough RAM/CPU (or GPU) on the host to serve the chosen
  model size — `llama3.2` and `nomic-embed-text` are reasonable defaults for most laptops.
- To pull a different model, change `CHAT_MODEL` / `EMBEDDING_MODEL` in `.env` and re-run
  `docker compose --profile ollama up` — `ollama-model` will pull the newly configured model.
- To free disk space used by downloaded models, remove the volume with
  `docker compose down -v` (this also removes other Compose volumes, so only do this in a
  disposable dev environment).
