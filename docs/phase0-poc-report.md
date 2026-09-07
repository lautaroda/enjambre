# Reporte de la Fase 0 (parcial — M0.1 a M0.4)

Estado: **M0.1–M0.4 validados en localhost.** M0.5 (latencia de red real) y M0.6
(modelo grande en GPU real) quedan pendientes — requieren máquinas separadas
(cloud y/o gente de confianza) que todavía no se provisionaron. No hay
recomendación go/no-go para Fase 1 hasta tener esos dos.

## M0.1 — Spike de entorno

La imagen `enjambre/swarm-node:dev` (Python 3.10 + torch CPU + hivemind + petals)
builda y corre en Docker Desktop sobre Apple Silicon (arm64 nativo, sin emulación).
Se encontraron y corrigieron 4 bugs reales de dependencias en el camino — ver el
historial de commits (`Corregir Dockerfile de swarm-node para que el build M0.1
funcione`) para el detalle de cada uno: `pip --index-url` vs `--extra-index-url`,
`pkg_resources` faltante en setuptools recientes, `grpc_tools` faltante al
desactivar build isolation, y la necesidad de instalar el commit exacto de
`hivemind` que `petals` pinea (no el HEAD de `main`, que ya no expone
`hivemind.PeerID`).

## M0.2 — Smoke test de un solo nodo

Un nodo (`single-node`, ancla su propio swarm con `--new_swarm --num_blocks 24`)
sirve los 24 bloques de `bigscience/bloom-560m`. El cliente se conecta vía DHT y
genera texto coherente end-to-end. Bugs corregidos: el CLI de petals espera el
modelo como argumento posicional (no `--model`); petals no tiene modo "solo DHT
sin bloques" (el nodo `--new_swarm` siempre hostea bloques él mismo, y en CPU
exige `--num_blocks` explícito).

## M0.3 — Partición en 3 nodos (localhost)

`node-1` (bloques 0-8, ancla el DHT) + `node-2` (8-16) + `node-3` (16-24), todos
en el mismo host vía `docker-compose`. Los tres anuncian sus rangos correctamente
y el swarm cubre el modelo completo (0-24). Bug corregido: `get-bootstrap-peer.sh`
usaba la IP que hivemind imprime para sí mismo (no ruteable entre contenedores)
en vez del nombre DNS del servicio de compose.

Este test corre en localhost — **no ejercita el NAT traversal real de hivemind**
(eso es M0.5). Mide solo el overhead puro del mecanismo de partición/pipeline.

## M0.4 — Harness de corrección

`benchmarks/correctness_check.py` comparó los logits de `bloom-560m` corrido (a)
localmente en `transformers` plano vs (b) distribuido a través de los 3 nodos de
M0.3:

```
similaridad coseno = 1.000012
norma relativa     = 0.000167
```

Prácticamente idéntico (la diferencia es ruido de punto flotante entre pasadas,
no error de partición) — muy por encima del umbral fijado (`cos_sim > 0.999`).
Confirma que partir el modelo en 3 procesos separados no degrada la salida.
Bug corregido: la imagen Docker no incluye el código del repo (el Dockerfile solo
instala dependencias) — se agregó un bind mount de `benchmarks/` al servicio
`client` en vez de rebuildear la imagen por cada cambio al script.

## Pendiente

- **M0.5** — mover este mismo setup a máquinas separadas geográficamente (cloud +
  gente de confianza, según lo acordado) para medir latencia de red real y
  ejercitar el NAT traversal de hivemind. Requiere provisionar instancias cloud
  (con costo, y con las credenciales/cuenta del usuario) y coordinar con las
  personas que sumen nodos — ninguna de las dos cosas se puede automatizar desde
  acá.
- **M0.6** — repetir M0.5 con un modelo que justifique partición real (Llama-2-7B
  o similar) en GPUs cloud.
- **M0.7** — este reporte se completa con los hallazgos de M0.5/M0.6 y ahí sí se
  da una recomendación go/no-go para Fase 1.
