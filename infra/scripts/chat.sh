#!/usr/bin/env bash
# Abre un chat contra el swarm. Corre desde la raiz del repo.
#
# Uso:
#   ./infra/scripts/chat.sh /ip4/<ip1>/tcp/31337/p2p/<peer1> /ip4/<ip2>/... ...
#
# Pasar las direcciones de TODOS los nodos, no solo la del ancla - en swarms
# chicos el cliente no puede resolver por DHT donde esta cada peer y falla con
# `routing: not found` (ver packages/client-sdk/README.md).
#
# Variables opcionales: MODEL (default bigscience/bloom-560m), MAX_NEW_TOKENS
# (default 60), IMAGE (default enjambre/swarm-node:dev).
set -euo pipefail

if [ $# -eq 0 ]; then
  echo "Uso: $0 <multiaddr-nodo-1> [<multiaddr-nodo-2> ...]" >&2
  echo "Ejemplo: $0 /ip4/192.168.1.135/tcp/31337/p2p/Qm..." >&2
  exit 1
fi

MODEL="${MODEL:-bigscience/bloom-560m}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-60}"
IMAGE="${IMAGE:-enjambre/swarm-node:dev}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Volumen para el cache de HuggingFace: sin esto el modelo (~1.1GB para
# bloom-560m, mucho mas para modelos grandes) se vuelve a bajar en cada chat,
# porque el contenedor es --rm y pierde /root/.cache al salir.
docker volume create enjambre-hf-cache >/dev/null

exec docker run --rm -it \
  -v "$REPO_ROOT/packages/client-sdk/client_sdk:/app/client_sdk" \
  -v "$REPO_ROOT/packages/client-sdk/chat.py:/app/chat.py" \
  -v enjambre-hf-cache:/root/.cache/huggingface \
  --entrypoint python3 "$IMAGE" -u chat.py \
  --model "$MODEL" \
  --max-new-tokens "$MAX_NEW_TOKENS" \
  --peers "$@"
