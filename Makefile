.PHONY: dev-build dev-up dev-up-smoke dev-down bench contracts-test

dev-build:
	docker build --platform linux/arm64 -f infra/docker/swarm-node.Dockerfile -t enjambre/swarm-node:dev .

# M0.3 es un flujo de 2 pasos (BOOTSTRAP_MADDR se conoce recien despues de que node-1
# arranca) - ver infra/docker-compose.dev.yml para el detalle. Este target arranca solo
# node-1; el resto se levanta a mano una vez exportado BOOTSTRAP_MADDR.
dev-up:
	docker compose -f infra/docker-compose.dev.yml up -d node-1

dev-up-smoke:
	docker compose -f infra/docker-compose.dev.yml --profile smoke up single-node

dev-down:
	docker compose -f infra/docker-compose.dev.yml down -v

bench:
	docker compose -f infra/docker-compose.dev.yml exec client python3 benchmarks/correctness_check.py

contracts-test:
	cd packages/contracts && forge test
