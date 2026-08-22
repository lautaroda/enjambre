.PHONY: dev-build dev-up dev-up-smoke dev-down bench contracts-test

dev-build:
	docker build --platform linux/arm64 -f infra/docker/swarm-node.Dockerfile -t enjambre/swarm-node:dev .

dev-up:
	docker compose -f infra/docker-compose.dev.yml up bootstrap node-1 node-2 node-3 client

dev-up-smoke:
	docker compose -f infra/docker-compose.dev.yml --profile smoke up bootstrap single-node

dev-down:
	docker compose -f infra/docker-compose.dev.yml down -v

bench:
	docker compose -f infra/docker-compose.dev.yml exec client python3 benchmarks/correctness_check.py

contracts-test:
	cd packages/contracts && forge test
