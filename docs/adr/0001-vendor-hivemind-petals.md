# ADR 0001: Construir sobre hivemind + petals en vez de reescribir el networking/pipeline-parallel

## Contexto

Enjambre necesita dos piezas caras de construir desde cero: (a) una DHT pública con NAT traversal real (para que nodos detrás de routers domésticos se encuentren en internet), y (b) un protocolo de pipeline-parallel servidor-a-servidor (para partir un modelo entre nodos y encadenar la inferencia).

Se evaluaron:

- **`hivemind`** (learning-at-home) — activo, DHT libp2p con NAT traversal probado a escala de internet.
- **`petals`** (bigscience-workshop) — activo, corrió en producción real (BLOOM-176B, Llama-2-70B, Falcon-180B) sobre nodos voluntarios de internet. Limitación: dependencias congeladas (Python 3.10/3.11, `transformers==4.43.1`) y solo soporta arquitecturas `bloom`, `llama`, `falcon`, `mixtral`.
- **`exo`** — excelente para clusters LAN de confianza (descubrimiento por broadcast UDP), pero sin DHT pública ni capa de incentivos/verificación. No cumple el requisito de red pública abierta.
- **`prima.cpp`** — buena técnica de partitioning heterogéneo CPU/GPU, pero pensado para un único clúster doméstico, sin red p2p pública.

## Decisión

Vendorear/depender de `hivemind` + `petals` como base de la Fase 0, tratándolos como código de partida a inspeccionar y eventualmente parchear (no como dependencia suelta de PyPI a largo plazo).

## Consecuencias

- Ganamos meses de desarrollo en la parte más cara (DHT + pipeline-parallel), a cambio de heredar las limitaciones de Petals (arquitecturas de modelo soportadas, versiones de Python/`transformers` congeladas).
- El Dockerfile de la Fase 0 (`infra/docker/swarm-node.Dockerfile`) clona ambos repos en build-time — es un pin de fuente, no un vendoring real dentro del árbol git. Vendoring real (git submodules en `packages/swarm-node/vendor/`) queda como fast-follow una vez que el spike M0.1 valide el enfoque, no antes.
- Camino de evolución a futuro (no decidido, solo documentado para no sorprendernos): a partir de Fase 1, cuando haga falta escalar el join permissionless e integrar la capa de incentivos, evaluar reescribir la capa de networking (no el motor de tensores) en Rust con `libp2p-rust` — mismo protocolo que ya usa hivemind — dejando Python solo para la ejecución del modelo vía PyTorch.
