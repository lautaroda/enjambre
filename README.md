# Enjambre

Red pública de nodos voluntarios que comparten GPU para correr modelos de IA grandes de forma colectiva, partiendo un modelo entre varios nodos ("swarm"/model-parallel) en vez de requerir que un solo dispositivo tenga toda la capacidad de cómputo. Quien aporta hardware recibe una contraprestación económica liquidada vía blockchain.

Ver el plan completo en [`docs/roadmap.md`](docs/roadmap.md).

## Estado actual

**Fase 0 — prueba de concepto técnica.** Validando que partir un modelo entre nodos y correr inferencia pipelineada funciona, antes de abrir la red al público o tocar cualquier cosa de blockchain. Ver milestones en `docs/roadmap.md`.

## Arquitectura (resumen)

Construido sobre [`hivemind`](https://github.com/learning-at-home/hivemind) (DHT + NAT traversal) y [`petals`](https://github.com/bigscience-workshop/petals) (pipeline-parallel de inferencia), en vez de reescribir esas piezas desde cero. Ver [`docs/adr/0001-vendor-hivemind-petals.md`](docs/adr/0001-vendor-hivemind-petals.md) para el razonamiento, y [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) para la vista general.

## Estructura del repo

```
packages/
  swarm-node/          nodo que hostea bloques del modelo (Fase 0)
  swarm-coordinator/    bootstrap DHT + monitoreo (Fase 0/1)
  verifier/             verificación por redundancia (Fase 0/1)
  ledger-daemon/        créditos simples, sin blockchain (Fase 1)
  contracts/            Solidity/Foundry — pagos e incentivos (Fase 2/3)
  client-sdk/           SDK para pedir inferencia a la red (Fase 1+)
  api-gateway/          API compatible con OpenAI (aider, Continue, Open WebUI)
  shared/               esquemas compartidos
infra/                  Docker, docker-compose, scripts
benchmarks/             harness de corrección y latencia
docs/                   arquitectura, ADRs, roadmap
```

## Quick start (Fase 0, milestone M0.1)

Requiere Docker Desktop. No hace falta GPU NVIDIA ni `torch` instalado en el host — todo corre dentro del contenedor.

```bash
make dev-build   # build de la imagen swarm-node (Python 3.10 + torch CPU + hivemind + petals)
make dev-up      # levanta bootstrap DHT + nodos partidos + cliente (docker-compose.dev.yml)
make bench       # corre el harness de corrección (benchmarks/correctness_check.py)
```

## Licencia

Apache License 2.0 — ver [`LICENSE`](LICENSE).
