# Contribuir a Enjambre

Proyecto en Fase 0 (prueba de concepto técnica) — ver [`docs/roadmap.md`](docs/roadmap.md) antes de proponer cambios de arquitectura, y las decisiones ya cerradas en la sección inicial (no se reabren sin discusión explícita en un issue).

## Setup local

Requiere Docker Desktop. No hace falta GPU NVIDIA ni `torch` en el host.

```bash
make dev-build          # build de la imagen swarm-node
make dev-up-smoke       # M0.2: un solo nodo con el modelo completo
make dev-up             # M0.3: partición en 3 nodos
make bench              # M0.4: harness de corrección (benchmarks/correctness_check.py)
```

## Decisiones de arquitectura

Cambios estructurales (no un bugfix chico) se documentan como ADR en `docs/adr/`, siguiendo el formato de [`0001-vendor-hivemind-petals.md`](docs/adr/0001-vendor-hivemind-petals.md): Contexto → Decisión → Consecuencias.

## Pull requests

- Un PR, un cambio lógico.
- Si tocás `infra/docker/swarm-node.Dockerfile`, el workflow `docker-build` valida que la imagen sigue buildeando.
