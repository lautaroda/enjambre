#!/usr/bin/env bash
# Imprime el multiaddr completo (con peer ID) del contenedor `bootstrap` para usar
# como BOOTSTRAP_MADDR al levantar el resto de los nodos. Ver infra/docker-compose.dev.yml.
set -euo pipefail

PEER_LINE=$(docker compose -f "$(dirname "$0")/../docker-compose.dev.yml" logs bootstrap \
  | grep -m1 -oE '/ip4/[0-9.]+/tcp/[0-9]+/p2p/[A-Za-z0-9]+' || true)

if [ -z "$PEER_LINE" ]; then
  echo "No encontré un multiaddr en los logs de 'bootstrap' todavía." >&2
  echo "Asegurate de haber corrido: docker compose -f infra/docker-compose.dev.yml up bootstrap" >&2
  exit 1
fi

echo "export BOOTSTRAP_MADDR=$PEER_LINE"
