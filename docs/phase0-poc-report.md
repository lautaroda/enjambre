# Reporte de la Fase 0 (M0.1 a M0.5)

Estado: **M0.1–M0.5 validados.** M0.5 se completó con 3 máquinas reales del
usuario en vez de VMs cloud (Mac M4 + PC Intel i7/Ubuntu + ASUS ROG Ally X con
Windows/WSL2), todas en la misma LAN. M0.6 (modelo grande en GPU real) sigue
pendiente. No hay recomendación go/no-go final para Fase 1 hasta tener M0.6.

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

## M0.5 — Máquinas reales separadas ✅

Se hizo con 3 máquinas reales del usuario en la misma LAN, en vez de VMs cloud:

| Nodo | Hardware | SO | Bloques |
|---|---|---|---|
| Ancla | MacBook Pro M4, 16GB | macOS (Docker Desktop) | 0-8 |
| Follower | Intel i7, 16GB, RX 5700 XT (sin usar, CPU only) | Ubuntu | 8-16 |
| Follower | ASUS ROG Ally X (Ryzen Z1 Extreme) | Windows 11 + WSL2 | 16-24 |

**Resultado**: inferencia distribuida real, atravesando las tres máquinas.

```
Route found: 0:8 via …bWzPbW => 8:16 via …qU4eAh => 16:24 via …u1nRFL
RESULTADO: Hola, como estas? Yo estoy en el mismo dilema que tu, y no sé si me
```

### Bugs reales encontrados y corregidos en el camino

Ninguno de estos aparecía en las pruebas de localhost (M0.1-M0.4) — todos
salieron solo al usar máquinas, sistemas operativos y redes de verdad:

1. **bash 3.2 (macOS)**: `"${ARR[@]}"` sobre un array vacío tira "unbound variable" bajo `set -u`. Funciona en cualquier bash 4.4+ de Linux; rompe en Mac.
2. **Follower sin puerto publicado**: el branch de follower de `run-remote-node.sh` no hacía `-p` ni fijaba `--host_maddrs` — ningún peer podía alcanzarlo.
3. **Auto-anuncio de IP interna de Docker**: sin `SELF_IP` explícito, hivemind anunciaba `172.17.0.2` (la IP del contenedor), no ruteable desde otra máquina.
4. **Bloques duplicados**: con `--num_blocks` (auto-balance) y nodos que no se ven bien entre sí, dos nodos eligieron el mismo rango (8-15) y nadie cubrió 0-7. Se agregó `BLOCK_INDICES` para asignación explícita.
5. **Firewall de Windows (puerto 31337)**: bloqueaba el puerto del swarm. El firewall no es parte de WSL2 — hay que abrirlo en Windows aunque uses "mirrored networking".
6. **UFW sin regla para 31337** en la Ubuntu (aunque Docker suele saltear UFW igual al publicar puertos).
7. **`routing: not found` — el más sutil**: pasarle al cliente solo la dirección del ancla no alcanza. El DHT le da el *peer ID* del nodo que sirve cada rango, pero no su *dirección*; el cliente cae a resolverla por DHT `FindPeer`, que en un swarm de 3 nodos no tiene red suficiente y falla. **Hay que pasarle al cliente las direcciones de todos los nodos.** En el swarm público de petals esto no se nota porque el cliente termina conectado a muchos servidores igual.

### Limitación de esta corrida

Las tres máquinas están en la **misma LAN**, así que esto todavía **no ejercita
el NAT traversal real de hivemind** entre redes distintas (el objetivo original
de M0.5). Para eso falta un nodo genuinamente fuera de la red — una VM cloud o
la casa de alguien más. Lo que sí quedó validado: máquinas físicas distintas,
tres sistemas operativos distintos, y red real (no localhost).

## Pendiente

- **M0.5b** — repetir con al menos un nodo fuera de la LAN (VM cloud o casa de un amigo) para ejercitar NAT traversal de verdad.
- **M0.6** — repetir con un modelo que justifique partición real (Llama-2-7B o similar).
- **M0.7** — recomendación go/no-go para Fase 1, con los hallazgos de M0.5b/M0.6.
