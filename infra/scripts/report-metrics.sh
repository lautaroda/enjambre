#!/usr/bin/env bash
# Reporta metricas de ESTE nodo (CPU/RAM via `docker stats`, throughput leido
# de sus propios logs) al swarm-coordinator, cada INTERVAL segundos. Correr en
# la misma maquina donde ya esta arriba el contenedor de run-remote-node.sh.
#
# Uso:
#   NODE_ID=mac COORDINATOR_URL=http://192.168.1.135:8000 ./report-metrics.sh
#
# Variables opcionales: CONTAINER_NAME (default enjambre-node), INTERVAL
# (default 10, segundos).
set -euo pipefail

NODE_ID="${NODE_ID:?seteá NODE_ID=<nombre-para-identificar-este-nodo, ej. mac/ubuntu/asus>}"
COORDINATOR_URL="${COORDINATOR_URL:?seteá COORDINATOR_URL=http://<ip-del-coordinator>:8000}"
CONTAINER_NAME="${CONTAINER_NAME:-enjambre-node}"
INTERVAL="${INTERVAL:-10}"

# docker stats devuelve la memoria con unidades mixtas (ej. "123.4MiB /
# 1.94GiB") - hay que normalizar a MB antes de comparar/graficar, no alcanza
# con borrar las letras (perderia la escala real entre MiB y GiB).
to_mb() {
  local val="$1"
  local num unit
  num=$(echo "$val" | grep -oE '^[0-9.]+')
  unit=$(echo "$val" | grep -oE '[A-Za-z]+$')
  case "$unit" in
    GiB) awk "BEGIN{printf \"%.1f\", $num*1024}" ;;
    MiB) awk "BEGIN{printf \"%.1f\", $num}" ;;
    KiB) awk "BEGIN{printf \"%.1f\", $num/1024}" ;;
    GB)  awk "BEGIN{printf \"%.1f\", $num*1000}" ;;
    MB)  awk "BEGIN{printf \"%.1f\", $num}" ;;
    KB)  awk "BEGIN{printf \"%.1f\", $num/1000}" ;;
    *)   echo "$num" ;;
  esac
}

echo "Reportando métricas de '$CONTAINER_NAME' como '$NODE_ID' a $COORDINATOR_URL cada ${INTERVAL}s (Ctrl+C para cortar)..."

while true; do
  STATS=$(docker stats "$CONTAINER_NAME" --no-stream --format '{{.CPUPerc}}|{{.MemUsage}}' 2>/dev/null || echo "")

  if [ -n "$STATS" ]; then
    CPU=$(echo "$STATS" | cut -d'|' -f1 | tr -d '%')
    MEM_RAW=$(echo "$STATS" | cut -d'|' -f2)
    MEM_USED_RAW=$(echo "$MEM_RAW" | awk -F'/' '{print $1}' | tr -d ' ')
    MEM_TOTAL_RAW=$(echo "$MEM_RAW" | awk -F'/' '{print $2}' | tr -d ' ')
    MEM_USED=$(to_mb "$MEM_USED_RAW")
    MEM_TOTAL=$(to_mb "$MEM_TOTAL_RAW")
  else
    CPU="null"; MEM_USED="null"; MEM_TOTAL="null"
  fi

  THROUGHPUT=$(docker logs "$CONTAINER_NAME" 2>&1 | grep "Inference throughput" | tail -1 \
    | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "")
  THROUGHPUT="${THROUGHPUT:-null}"

  curl -s -X POST "$COORDINATOR_URL/nodes/$NODE_ID/metrics" \
    -H "Content-Type: application/json" \
    -d "{\"cpu_percent\": ${CPU:-null}, \"mem_used_mb\": ${MEM_USED:-null}, \"mem_total_mb\": ${MEM_TOTAL:-null}, \"throughput_tokens_per_sec\": ${THROUGHPUT}}" \
    >/dev/null || echo "no se pudo reportar al coordinator (¿esta arriba?)"

  sleep "$INTERVAL"
done
