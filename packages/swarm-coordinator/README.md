# swarm-coordinator

Bootstrap DHT y dashboard de monitoreo del swarm (qué nodos están vivos, qué bloques hostea cada uno).

**Pendiente — Fase 0/1.** Por ahora el rol de bootstrap lo cumple el servicio `bootstrap` en [`infra/docker-compose.dev.yml`](../../infra/docker-compose.dev.yml) directamente con `petals.cli.run_server --new_swarm`.
