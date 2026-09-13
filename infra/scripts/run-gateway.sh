#!/usr/bin/env bash
# Levanta el gateway compatible con la API de OpenAI por delante del swarm.
# Corre desde la raiz del repo.
#
# Uso:
#   MODEL=deepseek-ai/deepseek-coder-6.7b-instruct \
#     ./infra/scripts/run-gateway.sh /ip4/<ip1>/tcp/31337/p2p/<peer1> /ip4/<ip2>/...
#
# Igual que chat.sh: MODEL es OBLIGATORIO y tiene que coincidir EXACTO con lo
# que sirven los nodos, y hay que pasar las direcciones de TODOS los nodos (en
# swarms chicos el cliente no puede resolver por DHT donde esta cada peer).
#
# Despues, apuntale cualquier herramienta que hable el protocolo de OpenAI:
#
#   aider --openai-api-base http://localhost:8000/v1 \
#         --openai-api-key enjambre --model "$MODEL"
#
#   curl http://localhost:8000/v1/chat/completions \
#     -H 'Content-Type: application/json' \
#     -d '{"model":"x","messages":[{"role":"user","content":"hola"}]}'
#
# Variables opcionales: PORT (8000), MAX_TOKENS (512), IMAGE
# (enjambre/swarm-node:dev), MEM_LIMIT (3g).
set -euo pipefail

if [ $# -eq 0 ] || [ -z "${MODEL:-}" ]; then
  echo "Uso: MODEL=<modelo-que-sirven-los-nodos> $0 <multiaddr-1> [<multiaddr-2> ...]" >&2
  echo "Ejemplo: MODEL=deepseek-ai/deepseek-coder-6.7b-instruct $0 /ip4/192.168.1.135/tcp/31337/p2p/Qm..." >&2
  exit 1
fi

PORT="${PORT:-8000}"
MAX_TOKENS="${MAX_TOKENS:-512}"
IMAGE="${IMAGE:-enjambre/swarm-node:dev}"
MEM_LIMIT="${MEM_LIMIT:-3g}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

PEERS="$(IFS=,; echo "$*")"

CONTAINER_NAME="enjambre-gateway"
if docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
  echo "Habia un gateway previo corriendo - lo reemplazo." >&2
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

docker volume create enjambre-hf-cache >/dev/null

# Se monta el codigo del repo en vez de rebuildear la imagen: el Dockerfile
# solo instala dependencias (torch/petals/hivemind), no copia el repo.
# fastapi/uvicorn no estan en la imagen, se instalan al arrancar - son livianos
# y evita mantener una imagen aparte solo para esto.
exec docker run --rm -it \
  --name "$CONTAINER_NAME" \
  --memory "$MEM_LIMIT" \
  -p "$PORT:8000" \
  -e HF_HUB_DISABLE_XET=1 \
  -e PYTHONWARNINGS=ignore::FutureWarning \
  -e ENJAMBRE_MODEL="$MODEL" \
  -e ENJAMBRE_PEERS="$PEERS" \
  -e ENJAMBRE_MAX_TOKENS="$MAX_TOKENS" \
  -e PYTHONPATH=/app/gw:/app/sdk \
  -v "$REPO_ROOT/packages/api-gateway:/app/gw" \
  -v "$REPO_ROOT/packages/client-sdk:/app/sdk" \
  -v enjambre-hf-cache:/root/.cache/huggingface \
  -w /app/gw \
  --entrypoint sh "$IMAGE" -c \
  "pip install -q fastapi 'uvicorn[standard]' >/dev/null 2>&1; \
   exec uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000"
