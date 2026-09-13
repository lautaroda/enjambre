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
# o rocm), PORT (default 31337), REPO_DIR (default ./enjambre),
# MEM_LIMIT (ej. "6g" - limite de RAM del contenedor, ver mas abajo por que
# conviene fijarlo), INFERENCE_MAX_LENGTH, ATTN_CACHE_TOKENS y MAX_BATCH_SIZE
# (largo maximo de secuencia, cache de atencion y tamaño de batch - el default
# de petals para modelos sin multi-query attention es 2048 en los tres, muy
# poco para aider y similares).
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

# Caches persistentes. SIN esto, cada reinicio del contenedor vuelve a descargar
# el modelo entero desde cero (el cache vive en la capa de escritura del
# contenedor, que `docker rm` borra). Con --restart unless-stopped eso se vuelve
# un bucle: arranca -> descarga -> algo falla -> reinicia -> descarga de nuevo,
# para siempre. Fue exactamente el bug del 6.7B (ver docs/phase0-poc-report.md).
#
# Ojo con el path: el SERVIDOR de petals NO usa ~/.cache/huggingface. Usa su
# propio directorio, `PETALS_CACHE` o ~/.cache/petals (petals.utils.disk_cache.
# DEFAULT_CACHE_DIR), y ahi guarda tanto los pesos de los bloques como
# `throughput_v5.json` - el resultado del benchmark de arranque, que tarda ~2
# minutos (el speedtest de red solo tiene 60s de timeout y en una conexion lenta
# ni termina). Montar solo el de HuggingFace no alcanza: el cliente (chat.sh) si
# usa ~/.cache/huggingface, pero el nodo no. Se montan los dos.
docker volume create enjambre-petals-cache >/dev/null
docker volume create enjambre-hf-cache >/dev/null
CACHE_ARGS=(
  -v enjambre-petals-cache:/root/.cache/petals
  -v enjambre-hf-cache:/root/.cache/huggingface
)

# HF_HUB_DISABLE_XET=1: `hf_xet` es el descargador nuevo de HuggingFace (activo
# por defecto desde huggingface_hub 0.30) que baja en chunks paralelos y los
# bufferea en RAM. Con un modelo de 13GB en una maquina con poca memoria eso
# dispara el OOM killer del kernel ANTES de cargar un solo bloque. Evidencia
# real en el Mac (Docker Desktop, VM de 7.6GB):
#   hf-xet-7 invoked oom-killer: ... constraint=CONSTRAINT_NONE, global_oom
#   Out of memory: Killed process (python) total-vm:6541524kB
# Lo confuso del caso: como el OOM fue GLOBAL de la VM (no del cgroup del
# contenedor), `docker inspect` reporta OOMKilled=false y ExitCode=0 - parece
# que el proceso salio solo, sin error ni traceback. El downloader clasico
# (sin xet) escribe a disco en streaming y usa memoria constante.
DOWNLOAD_ENV=(-e HF_HUB_DISABLE_XET=1)

# MEM_LIMIT opcional pero MUY recomendado: fija un limite de cgroup al
# contenedor. No es solo proteccion - es diagnostico. Sin limite, un pico de
# memoria del nodo se lleva puesta la maquina entera y el kernel elige que
# matar (arriba mato al proceso equivocado), dejando OOMKilled=false y un exit
# code 0 que no dice nada. Con limite, el OOM queda atribuido al contenedor y
# `docker inspect` lo reporta como OOMKilled=true, que es una pista directa.
MEM_ARGS=()
if [ -n "${MEM_LIMIT:-}" ]; then
  MEM_ARGS=(--memory "$MEM_LIMIT")
fi

# Largo maximo de secuencia, cache de atencion y tamaño de batch.
#
# petals elige TRES defaults distintos segun el tipo de atencion del modelo:
# 8192/16384/8192 (inference_max_length/attn_cache_tokens/max_batch_size) si
# usa multi-query attention (Llama 2, Falcon), y 2048/4096/2048 para el resto.
# deepseek-coder esta basado en Llama 1 (32 cabezas de query y 32 de
# key/value, sin GQA), asi que cae en "el resto" y queda en 2048 en los tres -
# aunque el modelo soporta 16384 de contexto.
#
# Los tres hacen falta a la vez para que un prompt largo funcione, y fallan en
# ORDEN, cada uno tapando al siguiente - se encontraron uno por uno subiendo
# solo el primero y probando de nuevo:
#
#   1) inference_max_length muy chico -> ValueError: Cannot allocate KV cache
#      for 2611 tokens, max = 2048
#   2) con eso resuelto, attn_cache_tokens (el tamaño real reservado) puede
#      seguir chico y dar el mismo error con otro numero
#   3) con el cache ya resuelto (alloc_done exitoso), max_batch_size sigue
#      limitando el PREFILL - el paso que procesa el prompt entero de una
#      pasada - y tira ValueError: Task size greater than max_batch_size
#      (2048), it can't be processed
#
# 2048 es muy poco para herramientas reales: aider manda su system prompt mas
# el contexto del repo y ya arranca en ~2600 tokens.
#
# El costo de subir attn_cache_tokens es memoria, lineal con los tokens y con
# la cantidad de bloques del nodo (medido: 1.75 GiB para 14 bloques del 6.7B
# con 8192 tokens, ~225 KB por token por cada 14 bloques). Por eso los tres
# quedan configurables y no fijos: un nodo chico no deberia pagar eso.
SEQ_ARGS=()
if [ -n "${INFERENCE_MAX_LENGTH:-}" ]; then
  SEQ_ARGS+=(--inference_max_length "$INFERENCE_MAX_LENGTH")
fi
if [ -n "${ATTN_CACHE_TOKENS:-}" ]; then
  SEQ_ARGS+=(--attn_cache_tokens "$ATTN_CACHE_TOKENS")
fi
if [ -n "${MAX_BATCH_SIZE:-}" ]; then
  SEQ_ARGS+=(--max_batch_size "$MAX_BATCH_SIZE")
fi

# /dev/shm de Docker (64 MiB por defecto) - un cuarto limite en la misma
# cadena, este no es de petals sino del propio Docker. El nodo pasa los
# tensores de activacion entre su proceso principal y el pool de inferencia
# via memoria compartida (torch._share_filename_cpu_); con max_batch_size en
# 8192 el tensor no entra en 64 MiB y el nodo tira, ya con el batch aceptado:
#
#   RuntimeError: unable to allocate shared memory(shm) for file
#   </torch_95_4117754786_4>: No space left on device (28)
#
# --shm-size sube ese limite. 1g alcanza de sobra para un batch de 8192.
SHM_ARGS=(--shm-size "${SHM_SIZE:-1g}")

if [ "$ROLE" = "anchor" ]; then
  echo "Arrancando nodo ANCLA ($BACKEND) en :$PORT, anunciando IP publica $PUBLIC_IP..."
  docker run -d --name "$CONTAINER_NAME" --restart unless-stopped \
    ${GPU_ARGS[@]+"${GPU_ARGS[@]}"} \
    ${MEM_ARGS[@]+"${MEM_ARGS[@]}"} \
    ${SHM_ARGS[@]+"${SHM_ARGS[@]}"} \
    ${DOWNLOAD_ENV[@]+"${DOWNLOAD_ENV[@]}"} \
    -p "$PORT:$PORT" \
    -v enjambre-node-identity:/root/.hivemind \
    ${CACHE_ARGS[@]+"${CACHE_ARGS[@]}"} \
    "$IMAGE_TAG" \
    "$MODEL" \
    --new_swarm \
    ${DEVICE_ARGS[@]+"${DEVICE_ARGS[@]}"} \
    ${NUM_BLOCKS_ARGS[@]+"${NUM_BLOCKS_ARGS[@]}"} \
    ${SEQ_ARGS[@]+"${SEQ_ARGS[@]}"} \
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
    ${MEM_ARGS[@]+"${MEM_ARGS[@]}"} \
    ${SHM_ARGS[@]+"${SHM_ARGS[@]}"} \
    ${DOWNLOAD_ENV[@]+"${DOWNLOAD_ENV[@]}"} \
    -p "$PORT:$PORT" \
    -v enjambre-node-identity:/root/.hivemind \
    ${CACHE_ARGS[@]+"${CACHE_ARGS[@]}"} \
    "$IMAGE_TAG" \
    "$MODEL" \
    --initial_peers "$INITIAL_PEERS" \
    ${DEVICE_ARGS[@]+"${DEVICE_ARGS[@]}"} \
    ${NUM_BLOCKS_ARGS[@]+"${NUM_BLOCKS_ARGS[@]}"} \
    ${SEQ_ARGS[@]+"${SEQ_ARGS[@]}"} \
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
