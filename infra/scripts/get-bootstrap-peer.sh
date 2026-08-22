#!/usr/bin/env bash
# Imprime el multiaddr del nodo ancla del swarm (el que arrancó con --new_swarm) para
# usar como BOOTSTRAP_MADDR al levantar el resto de los nodos. Ver infra/docker-compose.dev.yml.
#
# Uso: ./infra/scripts/get-bootstrap-peer.sh [servicio]   (default: node-1)
#
# Ojo: no reusamos la IP que hivemind imprime en sus propios logs (suele ser 127.0.0.1
# o la IP que el contenedor ve de si mismo) porque no es alcanzable desde los otros
# contenedores. Extraemos solo el peer ID y armamos la direccion con el nombre DNS
# del servicio de docker-compose, que si resuelve entre contenedores.
set -euo pipefail

SERVICE="${1:-node-1}"

PEER_ID=$(docker compose -f "$(dirname "$0")/../docker-compose.dev.yml" logs "$SERVICE" \
  | grep -m1 -oE '/p2p/[A-Za-z0-9]+' | head -n1 | sed 's#/p2p/##' || true)

if [ -z "$PEER_ID" ]; then
  echo "No encontré un peer ID en los logs de '$SERVICE' todavía." >&2
  echo "Asegurate de haber corrido: docker compose -f infra/docker-compose.dev.yml up -d $SERVICE" >&2
  exit 1
fi

echo "export BOOTSTRAP_MADDR=/dns4/$SERVICE/tcp/31337/p2p/$PEER_ID"
