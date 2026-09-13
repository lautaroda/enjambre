#!/usr/bin/env bash
# Levanta un nodo real de Enjambre en ESTA maquina, fuera de docker-compose - pensado
# para una VM cloud (nodo ancla, necesita IP publica), la maquina de un amigo detras
# de NAT domestico (nodo que se suma), o una maquina propia con GPU. Es el setup de
# M0.5/M0.6: conecta por internet real, a diferencia de docker-compose.dev.yml que
# corre todo en localhost.
#
# Uso:
#   Nodo ANCLA (una VM cloud con IP publica, ej. Hetzner/DigitalOcean):
#     ROLE=anchor PUBLIC_IP=1.2.3.4 ./run-remote-node.sh
#
#   Nodo que se SUMA (no necesita IP publica - funciona detras de NAT domestico,
#   es justo lo que el NAT traversal de hivemind esta pensado para resolver):
#     ROLE=follower INITIAL_PEERS=/ip4/1.2.3.4/tcp/31337/p2p/<peer-id-del-ancla> ./run-remote-node.sh
#
#   Si esta maquina SI tiene una IP alcanzable por el resto (ej. misma LAN que
#   el ancla, o puerto ya forwardeado), agregar SELF_IP para que se anuncie
#   correctamente - sin esto, hivemind puede auto-anunciar la IP interna del
#   contenedor de Docker, no ruteable desde otra maquina:
#     ROLE=follower SELF_IP=192.168.1.50 INITIAL_PEERS=/ip4/1.2.3.4/tcp/31337/p2p/<peer-id> ./run-remote-node.sh
#
#   Con GPU AMD/ROCm (ej. RX 5700 XT) - agregar BACKEND=rocm. El host Ubuntu
#   necesita el driver de ROCm instalado antes (ver docs/gpu-node-setup.md):
#     BACKEND=rocm ROLE=anchor PUBLIC_IP=1.2.3.4 ./run-remote-node.sh
#
# Variables opcionales: MODEL (default bigscience/bloom-560m), NUM_BLOCKS (default 8,
# ignorado con BACKEND=rocm - se auto-detecta segun VRAM salvo que lo fijes vos),
# BLOCK_INDICES (ej. "0:8" - fija un rango exacto, mas confiable que NUM_BLOCKS
# con varias maquinas reales, ver comentario mas abajo), BACKEND (cpu default,
# o rocm), PORT (default 31337), REPO_DIR (default ./enjambre).
#
# Antes de correr el nodo ancla: abri el puerto 31337/tcp en el firewall del proveedor
# cloud (Hetzner Cloud Firewall / DigitalOcean Cloud Firewall / ufw) - esto es especifico
# de cada proveedor, este script no lo puede hacer por vos.
set -euo pipefail

ROLE="${ROLE:?seteá ROLE=anchor o ROLE=follower}"
MODEL="${MODEL:-bigscience/bloom-560m}"
NUM_BLOCKS="${NUM_BLOCKS:-8}"
BACKEND="${BACKEND:-cpu}"
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

if [ "$BACKEND" = "rocm" ]; then
  DOCKERFILE="infra/docker/swarm-node-rocm.Dockerfile"
  IMAGE_TAG="enjambre/swarm-node:rocm"
  GPU_ARGS=(--device=/dev/kfd --device=/dev/dri --group-add=video --group-add=render --security-opt seccomp=unconfined)
  DEVICE_ARGS=(--device cuda)  # si, "cuda" - torch ROCm usa ese nombre por compatibilidad
  NUM_BLOCKS_ARGS=()  # se auto-detecta segun VRAM disponible en GPU
else
  DOCKERFILE="infra/docker/swarm-node.Dockerfile"
  IMAGE_TAG="enjambre/swarm-node:dev"
  GPU_ARGS=()
  DEVICE_ARGS=()
  NUM_BLOCKS_ARGS=(--num_blocks "$NUM_BLOCKS")  # CPU no auto-detecta, hay que fijarlo
fi

# BLOCK_INDICES (ej. "0:8") opcional: fija un rango exacto en vez de dejar que
# cada nodo elija con --num_blocks. Encontrado en la practica (3 maquinas
# reales): si los nodos no pueden verificarse bien entre si (reachability
# check fallando), el auto-balance no ve el estado real del swarm y puede
# hacer que dos nodos elijan el MISMO rango, dejando otro rango sin nadie -
# --block_indices explicito lo evita de raiz, al costo de coordinar a mano
# que rangos no se pisen.
if [ -n "${BLOCK_INDICES:-}" ]; then
  NUM_BLOCKS_ARGS=(--block_indices "$BLOCK_INDICES")
fi

echo "Buildeando imagen ($BACKEND, puede tardar unos minutos la primera vez)..."
docker build -f "$DOCKERFILE" -t "$IMAGE_TAG" .

CONTAINER_NAME="enjambre-node"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

if [ "$ROLE" = "anchor" ]; then
  echo "Arrancando nodo ANCLA ($BACKEND) en :$PORT, anunciando IP publica $PUBLIC_IP..."
  docker run -d --name "$CONTAINER_NAME" --restart unless-stopped \
    ${GPU_ARGS[@]+"${GPU_ARGS[@]}"} \
    -p "$PORT:$PORT" \
    -v enjambre-node-identity:/root/.hivemind \
    "$IMAGE_TAG" \
    "$MODEL" \
    --new_swarm \
    ${DEVICE_ARGS[@]+"${DEVICE_ARGS[@]}"} \
    ${NUM_BLOCKS_ARGS[@]+"${NUM_BLOCKS_ARGS[@]}"} \
    --identity_path /root/.hivemind/node.id \
    --host_maddrs "/ip4/0.0.0.0/tcp/$PORT" \
    --announce_maddrs "/ip4/$PUBLIC_IP/tcp/$PORT"
else
  # SELF_IP opcional: si esta maquina tiene una IP alcanzable por el resto
  # (misma LAN, o puerto ya forwardeado en el router), avisarla explicito
  # evita que hivemind se auto-anuncie con la IP interna del contenedor de
  # Docker (no ruteable desde otra maquina). Sin SELF_IP, para alguien
  # realmente detras de NAT domestico, hivemind cae al relay automatico -
  # sigue sin necesitar puerto abierto, pero conviene igual publicar el
  # puerto localmente para casos mixtos.
  ANNOUNCE_ARGS=()
  if [ -n "${SELF_IP:-}" ]; then
    ANNOUNCE_ARGS=(--announce_maddrs "/ip4/$SELF_IP/tcp/$PORT")
  fi
  echo "Arrancando nodo ($BACKEND), conectando a $INITIAL_PEERS..."
  docker run -d --name "$CONTAINER_NAME" --restart unless-stopped \
    ${GPU_ARGS[@]+"${GPU_ARGS[@]}"} \
    -p "$PORT:$PORT" \
    -v enjambre-node-identity:/root/.hivemind \
    "$IMAGE_TAG" \
    "$MODEL" \
    --initial_peers "$INITIAL_PEERS" \
    ${DEVICE_ARGS[@]+"${DEVICE_ARGS[@]}"} \
    ${NUM_BLOCKS_ARGS[@]+"${NUM_BLOCKS_ARGS[@]}"} \
    --identity_path /root/.hivemind/node.id \
    --host_maddrs "/ip4/0.0.0.0/tcp/$PORT" \
    ${ANNOUNCE_ARGS[@]+"${ANNOUNCE_ARGS[@]}"}
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
