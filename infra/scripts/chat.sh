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
# MODEL es OBLIGATORIO (no tiene default): tiene que coincidir EXACTO con el
# modelo que ya estan sirviendo los nodos. Bug real encontrado en uso: con un
# default fijo, en cuanto el swarm cambia de modelo (ej. de bloom-560m a
# deepseek-coder) el chat sigue buscando el viejo y nadie lo sirve -
# MissingBlocksError en loop, pareciendo que esta "colgado" en vez de dar un
# error claro. Mas vale obligar a pasarlo que arriesgarse a que quede
# desactualizado en silencio.
#
# Variables opcionales: MAX_NEW_TOKENS (default 60), IMAGE (default
# enjambre/swarm-node:dev), MEM_LIMIT (default 2g).
set -euo pipefail

if [ $# -eq 0 ] || [ -z "${MODEL:-}" ]; then
  echo "Uso: MODEL=<modelo-que-ya-estan-sirviendo-los-nodos> $0 <multiaddr-nodo-1> [<multiaddr-nodo-2> ...]" >&2
  echo "Ejemplo: MODEL=deepseek-ai/deepseek-coder-1.3b-instruct $0 /ip4/192.168.1.135/tcp/31337/p2p/Qm..." >&2
  echo "" >&2
  echo "MODEL tiene que coincidir EXACTO con lo que ya corre en los nodos - revisa" >&2
  echo "'docker logs enjambre-node | grep DHT prefix' en cualquiera de ellos si no estas seguro." >&2
  exit 1
fi

MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-60}"
IMAGE="${IMAGE:-enjambre/swarm-node:dev}"
MEM_LIMIT="${MEM_LIMIT:-2g}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# --name + limpieza previa: `docker run --rm` SOLO borra el contenedor cuando el
# proceso termina. Si cerras la terminal sin salir del REPL (Ctrl+C, cerrar la
# ventana, perder el SSH), el contenedor NO muere: queda vivo bloqueado en
# input(), con el modelo y el cliente cargados en RAM. Sin nombre fijo, cada
# chat crea uno nuevo con nombre random y se van apilando invisibles.
#
# Bug real: cinco sesiones de chat abandonadas acumularon 5.6GB de los 7.6GB de
# la VM de Docker Desktop en el Mac. El nodo del swarm -que corre en la misma
# VM- empezo a morir por OOM del kernel apenas se anunciaba al DHT, entrando en
# loop de reinicio. Como el OOM era GLOBAL de la VM y no del cgroup del nodo,
# `docker inspect` mostraba OOMKilled=false y ExitCode=0: parecia un bug del
# modelo grande que estabamos probando, y no tenia nada que ver.
CHAT_CONTAINER="enjambre-chat"
if docker ps -aq -f name="^${CHAT_CONTAINER}$" | grep -q .; then
  echo "Habia una sesion de chat previa sin cerrar (${CHAT_CONTAINER}) - la limpio." >&2
  docker rm -f "$CHAT_CONTAINER" >/dev/null
fi

# Volumen para el cache de HuggingFace: sin esto el modelo (~1.1GB para
# bloom-560m, mucho mas para modelos grandes) se vuelve a bajar en cada chat,
# porque el contenedor es --rm y pierde /root/.cache al salir.
docker volume create enjambre-hf-cache >/dev/null

exec docker run --rm -it \
  --name "$CHAT_CONTAINER" \
  --memory "$MEM_LIMIT" \
  -e PYTHONWARNINGS=ignore::FutureWarning \
  -e HF_HUB_DISABLE_XET=1 \
  -v "$REPO_ROOT/packages/client-sdk/client_sdk:/app/client_sdk" \
  -v "$REPO_ROOT/packages/client-sdk/chat.py:/app/chat.py" \
  -v enjambre-hf-cache:/root/.cache/huggingface \
  --entrypoint python3 "$IMAGE" -u chat.py \
  --model "$MODEL" \
  --max-new-tokens "$MAX_NEW_TOKENS" \
  --peers "$@"
