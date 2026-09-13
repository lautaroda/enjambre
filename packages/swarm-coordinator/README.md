# swarm-coordinator

Dashboard de monitoreo en vivo del swarm: qué nodos están reportando, CPU,
memoria y throughput de cada uno. Servicio FastAPI con estado en memoria (las
métricas son efímeras — a diferencia de [`ledger-daemon`](../ledger-daemon),
acá no hace falta persistencia).

No cumple rol de bootstrap DHT — eso lo sigue haciendo el primer nodo que
arranca con `--new_swarm` (ver [`infra/scripts/run-remote-node.sh`](../../infra/scripts/run-remote-node.sh)
y [`docs/adr/0001-vendor-hivemind-petals.md`](../../docs/adr/0001-vendor-hivemind-petals.md)
para por qué no hay un rol de "bootstrap puro" separado en petals).

## Setup

```bash
cd packages/swarm-coordinator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Correr

```bash
uvicorn coordinator.main:app --host 0.0.0.0 --port 8000
```

Abrir `http://<ip-de-esta-maquina>:8000/` — se refresca solo cada 5s.

## Sumar un nodo al dashboard

En la misma máquina donde ya está corriendo un nodo (via `run-remote-node.sh`),
correr [`infra/scripts/report-metrics.sh`](../../infra/scripts/report-metrics.sh)
apuntando al coordinator:

```bash
NODE_ID=<nombre-para-identificar-este-nodo> COORDINATOR_URL=http://<ip-del-coordinator>:8000 \
  ./infra/scripts/report-metrics.sh
```

Reporta CPU/memoria (vía `docker stats`, normalizado a MB — ojo que
`docker stats` devuelve unidades mixtas MiB/GiB, hay que convertir, no alcanza
con borrar las letras) y el último throughput visto en los logs del nodo, cada
10s por default. Un nodo se marca "sin reportar" en el dashboard si no
reportó en los últimos 30s.

## API

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/nodes/{node_id}/metrics` | Reporta métricas de un nodo (todos los campos opcionales) |
| `GET` | `/nodes` | Lista todos los nodos con sus últimas métricas (JSON) |
| `GET` | `/` | Dashboard HTML, auto-refresh cada 5s |
