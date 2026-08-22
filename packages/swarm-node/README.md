# swarm-node

Nodo que hostea uno o más bloques del modelo y sirve inferencia pipelineada al resto del swarm. Construido sobre `hivemind` + `petals` (ver [`docs/adr/0001-vendor-hivemind-petals.md`](../../docs/adr/0001-vendor-hivemind-petals.md)).

**Fase 0.** Hoy el código de hivemind/petals se trae vía `git clone` en build-time (`infra/docker/swarm-node.Dockerfile`), no vendorizado en este directorio. Vendoring real (git submodules acá) queda como fast-follow una vez que el spike M0.1 valide el enfoque.
