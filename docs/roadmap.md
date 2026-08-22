# Roadmap

Decisiones de diseño ya tomadas (no se reabren sin una discusión explícita):

1. **Arquitectura swarm/model-parallel** — no un marketplace de jobs; la razón de ser es correr modelos que no entran en una sola GPU.
2. **Red pública abierta desde el día 1** — cualquiera puede sumar un nodo o pedir cómputo.
3. **Blockchain como parte del diseño inicial** — para pagos/incentivos, no algo a evaluar "después".

## Fase 0 — PoC técnico (en curso)

Validar que partir un modelo entre nodos y correr inferencia pipelineada funciona, en un entorno controlado (nodos propios + de confianza), sin blockchain todavía.

Modelo de prueba: `bigscience/bloom-560m` (Petals no soporta GPT-2; alternativa: `TinyLlama/TinyLlama-1.1B`).

- **M0.1 — Spike de entorno**: Dockerfile builda y corre en arm64; `import petals` funciona en el contenedor.
- **M0.2 — Smoke test un solo nodo**: 1 contenedor sirviendo todos los bloques + 1 cliente generando texto.
- **M0.3 — Partición multi-nodo en una máquina**: bootstrap DHT + 3 nodos con `--block_indices` + cliente, en `docker-compose`. Mide overhead puro del mecanismo (sin ruido de red real).
- **M0.4 — Harness de corrección**: compara logits de la ruta local plana vs. la ruta distribuida (`benchmarks/correctness_check.py`). Semilla de la capa de verificación.
- **M0.5 — Latencia de red real**: mismo setup en máquinas separadas — cloud (Hetzner/DigitalOcean) + 1-2 nodos de personas de confianza en paralelo. Es lo único que ejercita el NAT traversal real de hivemind.
- **M0.6 — Escalar tamaño de modelo en GPU real**: repetir M0.5 con Llama-2-7B o Mixtral-8x7B en GPUs cloud baratas (RunPod/Vast.ai/Lambda).
- **M0.7 — Reporte de hallazgos**: `docs/phase0-poc-report.md`, recomendación go/no-go para Fase 1.

## Fase 1 — Join permissionless + ledger simple

DHT abierta (hivemind ya lo resuelve) + `packages/ledger-daemon` con una DB simple de créditos (sin blockchain) para validar el loop económico básico. Verificación por redundancia Nivel 2 (fingerprint firmado por hop) si Nivel 1 no alcanza.

## Fase 2 — Contrato de liquidación

L2 **Base**, pagos en **USDC**, liquidación por lotes vía Merkle root (`UsageLedger.sol`), ventana de disputa de 24-72h. Ver `docs/architecture/04-incentive-ledger.md`.

## Fase 3 — Stake y slashing

`StakeManager` + `SlashingModule` — stake para elegibilidad de trabajo de mayor confianza, slashing ante trampa comprobada. Reputación on-chain no transferible, separada del dinero retirable.

## Verificación por redundancia (Fase 0/1)

Petals encadena servidor-a-servidor directamente (el cliente solo habla con el primer/último nodo) — no se puede interceptar cada hop barato sin modificar el protocolo.

- **Nivel 1** (sin tocar el protocolo): correr 2-3 pipelines end-to-end con nodos disjuntos, comparar logits crudos (no el token muestreado). Umbral: similaridad coseno `> 0.999` (calibrar en M0.4) + norma relativa `‖a−b‖₂/‖a‖₂ < ε`. Discrepancia → nodo sospechoso, no se le paga esa unidad.
- **Nivel 2** (Fase 1, requiere modificar el fork): fingerprint firmado del output intermedio por request ID, permite acotar la disputa a un solo hop.

Aplicar Nivel 1 al 100% de requests en Fase 0/1; bajar a auditoría probabilística (5-10%) cuando madure la reputación en Fase 3.
