# Arquitectura — vista general

Enjambre tiene cuatro capas, construidas en ese orden (ver `docs/roadmap.md` para el detalle por fase):

1. **Networking/descubrimiento** — DHT tipo Kademlia para que los nodos se encuentren sin servidor central. Provista por `hivemind` (libp2p, NAT traversal real a escala de internet).
2. **Model-parallelism** — partir capas del modelo entre nodos y pipelinear la inferencia. Provista por `petals`.
3. **Verificación/anti-abuso** — redundancia (mandar el mismo tramo de cómputo a 2-3 nodos y comparar) en vez de criptografía de verificación de inferencia (zkML sigue siendo demasiado lento/caro para LLMs en producción). Ver [`03-verification.md`](03-verification.md).
4. **Incentivos on-chain** — settlement por lotes en una L2 (Base), separado del hot path de inferencia. Ver `04-incentive-ledger.md`.

## Por qué construir sobre hivemind + petals

Ver [`docs/adr/0001-vendor-hivemind-petals.md`](../adr/0001-vendor-hivemind-petals.md). En resumen: ambos ya resuelven, en producción real (BLOOM-176B/Llama-2-70B sobre nodos voluntarios de internet), los dos problemas más caros de este proyecto — DHT pública con NAT traversal, y pipeline-parallel servidor-a-servidor. Reescribirlos desde cero costaría meses sin aportar nada al diferencial real del proyecto (verificación + incentivos).

## Qué falta documentar

- `01-swarm-partitioning.md` — cómo se decide qué bloques hostea cada nodo, rebalanceo ante caída de nodos.
- `02-dht-discovery.md` — configuración concreta de bootstrap peers, relays.
- ~~`03-verification.md`~~ — **hecho**, ver [`03-verification.md`](03-verification.md) (Nivel 1 implementado, Nivel 2 diseñado con referencias concretas al código de petals/hivemind, pendiente de implementar).
- `04-incentive-ledger.md` — diseño detallado del contrato (hoy vive en `docs/roadmap.md`, mover acá cuando se implemente).

Estos se completan a medida que cada pieza se construye — no antes, para no documentar decisiones que todavía pueden cambiar con lo que se aprenda en la Fase 0.
