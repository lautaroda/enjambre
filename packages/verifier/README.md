# verifier

Verificación por redundancia Nivel 1 (ver
[`docs/roadmap.md`](../../docs/roadmap.md#verificaci%C3%B3n-por-redundancia-fase-01)):
corre 2-3 pipelines end-to-end con nodos disjuntos, compara sus logits, y acredita
solo a los nodos de la corrida (o corridas) que coinciden entre sí vía
[`ledger-daemon`](../ledger-daemon).

## Estructura

- `compare.py` — similaridad coseno + norma relativa entre dos vectores de logits. Sin dependencias pesadas (solo `numpy`).
- `redundancy.py` — `RedundancyVerifier`: agrupa corridas por acuerdo mutuo (union-find) y decide qué nodos se acreditan, cuáles quedan sospechosos, o si el resultado es inconcluyente.
- `ledger_client.py` — cliente HTTP mínimo hacia `ledger-daemon` para acreditar el verdict.
- `dispatch.py` — despacha una misma request a N pipelines reales del swarm en paralelo. **Necesita el mismo entorno que `swarm-node`** (torch + petals) — correr dentro de `infra/docker/swarm-node.Dockerfile`, no en el venv liviano de este paquete.

## Setup (compare/redundancy/ledger_client — sin torch/petals)

```bash
cd packages/verifier
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Hallazgo real de la prueba end-to-end (importante)

Se probó `dispatch.py` + `RedundancyVerifier` contra el swarm real de 3 nodos de
M0.3. Corriendo las 2 corridas **en paralelo** contra el mismo swarm en esta
máquina, un nodo tiró `MissingBlocksError` bajo la carga combinada y, tras
reintentos, las dos corridas terminaron dando logits que **no coincidían**
(`inconclusive=True` sobre los 3 nodos). Repitiendo la misma prueba
**secuencial** (sin la contención de 2 pipelines pesados compitiendo por la
misma CPU), el resultado fue `cos_sim=1.0, rel_norm=0.0` — coincidencia
perfecta. La lógica de comparación es correcta; lo que se descubrió es un
riesgo real de diseño:

**correr verificación por redundancia genera contención de carga sobre el
propio swarm que está verificando, y esa contención puede producir falsos
positivos** (nodos marcados sospechosos por caerse momentáneamente bajo carga,
no por hacer trampa). En este dev setup los 3 "nodos" y las 2 corridas de
verificación compiten por los mismos cores de una sola laptop — en producción,
con nodos en máquinas separadas, el efecto debería ser menor pero no
necesariamente desaparece (la red real introduce su propia variabilidad).

No resuelto todavía — ver comentario en
[issue #4](https://github.com/lautaroda/enjambre/issues/4). Antes de confiar en
esto para penalizar nodos de verdad, hace falta distinguir "el nodo devolvió un
resultado distinto" de "el nodo se cayó/reintentó a mitad de la corrida" (esto
último no debería contar como sospechoso).
