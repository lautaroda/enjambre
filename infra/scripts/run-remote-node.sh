#!/usr/bin/env bash
# Levanta un nodo real de Enjambre en ESTA maquina, fuera de docker-compose - pensado
# para una VM cloud (nodo ancla, necesita IP publica) o la maquina de un amigo detras
# de NAT domestico (nodo que se suma). Es el setup de M0.5: conecta por internet real,
# a diferencia de docker-compose.dev.yml que corre todo en localhost.
#
# Uso:
#   Nodo ANCLA (una VM cloud con IP publica, ej. Hetzner/DigitalOcean):
#     ROLE=anchor PUBLIC_IP=1.2.3.4 ./run-remote-node.sh
#
#   Nodo que se SUMA (no necesita IP publica - funciona detras de NAT domestico,
#   es justo lo que el NAT traversal de hivemind esta pensado para resolver):
#     ROLE=follower INITIAL_PEERS=/ip4/1.2.3.4/tcp/31337/p2p/<peer-id-del-ancla> ./run-remote-node.sh
#
# Variables opcionales: MODEL (default bigscience/bloom-560m), NUM_BLOCKS (default 8),
# PORT (default 31337), REPO_DIR (default ./enjambre).
#
# Antes de correr el nodo ancla: abri el puerto 31337/tcp en el firewall del proveedor
# cloud (Hetzner Cloud Firewall / DigitalOcean Cloud Firewall / ufw) - esto es especifico
# de cada proveedor, este script no lo puede hacer por vos.
set -euo pipefail

ROLE="${ROLE:?seteá ROLE=anchor o ROLE=follower}"
MODEL="${MODEL:-bigscience/bloom-560m}"
NUM_BLOCKS="${NUM_BLOCKS:-8}"
PORT="${PORT:-31337}"
REPO_DIR="${REPO_DIR:-./enjambre}"
REPO_URL="https://github.com/lautaroda/enjambre.git"

if [ "$ROLE" = "anchor" ] && [ -z "${PUBLIC_IP:-}" ]; then
  echo "ROLE=anchor necesita PUBLIC_IP=<ip publica de esta maquina>" >&2
  exit 1
fi
if [ "$ROLE" = "follower" ] && [ -z "${INITIAL_PEERS:-}" ]; then
  echo "ROLE=follower necesita INITIAL_PEERS=<multiaddr del nodo ancla>" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker no esta instalado - instalando..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
  echo "Si los pasos siguientes fallan por permisos, abri una sesion nueva (o corre con sudo) y volve a correr este script."
fi

if [ ! -d "$REPO_DIR" ]; then
  git clone --depth 1 "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

echo "Buildeando imagen (puede tardar unos minutos la primera vez)..."
docker build -f infra/docker/swarm-node.Dockerfile -t enjambre/swarm-node:dev .

CONTAINER_NAME="enjambre-node"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

if [ "$ROLE" = "anchor" ]; then
  echo "Arrancando nodo ANCLA en :$PORT, anunciando IP publica $PUBLIC_IP..."
  docker run -d --name "$CONTAINER_NAME" --restart unless-stopped \
    -p "$PORT:$PORT" \
    -v enjambre-node-identity:/root/.hivemind \
    enjambre/swarm-node:dev \
    "$MODEL" \
    --new_swarm \
    --num_blocks "$NUM_BLOCKS" \
    --identity_path /root/.hivemind/node.id \
    --host_maddrs "/ip4/0.0.0.0/tcp/$PORT" \
    --announce_maddrs "/ip4/$PUBLIC_IP/tcp/$PORT"
else
  echo "Arrancando nodo, conectando a $INITIAL_PEERS..."
  docker run -d --name "$CONTAINER_NAME" --restart unless-stopped \
    -v enjambre-node-identity:/root/.hivemind \
    enjambre/swarm-node:dev \
    "$MODEL" \
    --initial_peers "$INITIAL_PEERS" \
    --num_blocks "$NUM_BLOCKS" \
    --identity_path /root/.hivemind/node.id
fi

echo ""
echo "Nodo arrancado. Ver logs con:"
echo "  docker logs -f $CONTAINER_NAME"
echo ""
if [ "$ROLE" = "anchor" ]; then
  echo "Cuando en los logs aparezca 'Running a server on [...]', copiá la linea que"
  echo "empieza con /ip4/$PUBLIC_IP/tcp/$PORT/p2p/... - ese es el INITIAL_PEERS que"
  echo "necesitan los nodos que se sumen (ver docs/m0-5-remote-setup.md)."
fi
