# verifier

Verificación por redundancia Nivel 1 (ver
[`docs/roadmap.md`](../../docs/roadmap.md#verificaci%C3%B3n-por-redundancia-fase-01)):
corre 2-3 pipelines end-to-end con nodos disjuntos, compara sus logits, y acredita
solo a los nodos de la corrida (o corridas) que coinciden entre sí vía
[`ledger-daemon`](../ledger-daemon).

## Estructura

- `compare.py` — similaridad coseno + norma relativa entre dos vectores de logits. Sin dependencias pesadas (solo `numpy`).
- `redundancy.py` — `RedundancyVerifier`: agrupa corridas por acuerdo mutuo (union-find) y decide qué nodos se acreditan (`credited_node_ids`), cuáles quedan sospechosos de verdad (`suspect_node_ids`), cuáles divergieron por inestabilidad de red y no por trampa (`unreliable_node_ids`), o si el resultado es inconcluyente.
- `ledger_client.py` — cliente HTTP mínimo hacia `ledger-daemon` para acreditar el verdict.
- `dispatch.py` — despacha una misma request a N pipelines reales del swarm en paralelo, capturando si petals/hivemind emitieron algún warning durante cada corrida (`RunResult.had_warnings`). **Necesita el mismo entorno que `swarm-node`** (torch + petals) — correr dentro de `infra/docker/swarm-node.Dockerfile`, no en el venv liviano de este paquete.

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

## Fix aplicado (y su propio bug real, encontrado en vivo)

`dispatch.py` captura si petals/hivemind emitieron algún warning (nivel
`WARNING`+, ej. `MissingBlocksError` con reintento) durante cada corrida, y lo
marca en `RunResult.had_warnings`. `RedundancyVerifier` usa esa señal para
separar dos casos que antes se trataban igual:

- **`suspect_node_ids`**: la corrida divergió y no tuvo ningún warning — sí es evidencia real de trampa.
- **`unreliable_node_ids`**: la corrida divergió pero tuvo warnings — probablemente inestabilidad de red/carga, no trampa. No debería penalizar reputación.

La primera versión de este fix filtraba los warnings por thread id (para que
corridas concurrentes no se mezclaran entre sí). Los 12 tests unitarios
pasaban — pero probándolo en vivo forzando la caída real de un nodo a mitad de
una corrida (`docker stop`/`docker start` sobre `node-2` mientras una
inferencia estaba en curso), el resultado daba **`had_warnings=False`** pese a
que el warning se veía clarito en los logs del contenedor. El filtro por
thread id descartaba en silencio *todos* los warnings reales: petals/hivemind
los emite desde un hilo/loop de asyncio interno, no desde el hilo que llama.

Fix real: sacar el filtro por thread id, capturar cualquier warning global
mientras la corrida está en vuelo. La contra es que, con corridas realmente
concurrentes, un warning de una puede marcar `had_warnings=True` también en la
otra — pero eso es sobre-atribución seguro (marcar de más como "no confiable"),
no bajo-atribución peligrosa (tratar una corrida inestable como confiable).
Reproducido el mismo escenario forzado con el fix aplicado:
`RESULTADO: had_warnings=True` — confirmado con datos reales, no solo con el
test sintético.

Este es exactamente el motivo por el que valió la pena insistir en la prueba
end-to-end contra el swarm real en vez de conformarse con los tests
unitarios — el bug del filtro por thread id nunca iba a aparecer en un test
sintético, porque ahí no hay ningún hilo/loop interno de petals que difiera
del hilo que llama.
