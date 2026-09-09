# Verificación — diseño

## Nivel 1 (implementado)

Ver [`packages/verifier`](../../packages/verifier). Corre 2-3 pipelines end-to-end
con nodos disjuntos y compara logits vía similaridad coseno + norma relativa.
No dice cuál hop de una corrida divergente hizo trampa — solo que esa corrida
completa no es de confianza. Distingue `suspect_node_ids` (divergió sin
warnings — evidencia real) de `unreliable_node_ids` (divergió con warnings —
probable inestabilidad de red/carga, no penaliza).

## Nivel 2 — diseño (issue #5, investigación de código real)

Objetivo: acotar la disputa a un solo hop en vez de a la corrida completa,
para no tener que re-correr todo el pipeline ni penalizar nodos honestos que
comparten camino con uno tramposo.

### Hook point (confirmado en el código de petals)

`TransformerConnectionHandler.rpc_forward` / `rpc_forward_stream` en
`petals/src/petals/server/handler.py` (líneas ~352-410 en el commit que usa
[ADR 0001](../adr/0001-vendor-hivemind-petals.md)): el servidor calcula
`hidden_states = await run_rpc_forward(...)` y lo serializa de vuelta con
`self._serialize_outputs(...)`. Ese `hidden_states` es exactamente el output
intermedio del rango de bloques que hostea ese nodo — el punto correcto para
fingerprintear antes de que salga por la red.

### Qué fingerprintear

Hash (SHA256) de una versión redondeada/cuantizada de `hidden_states` (no el
tensor crudo — la aritmética de float no es asociativa entre hardware
distinto, así que dos nodos honestos con hardware diferente pueden dar
resultados bit-a-bit distintos aunque ambos sean correctos). El nivel de
redondeo es el mismo tipo de calibración empírica que ya hicimos para el
umbral de similaridad coseno de Nivel 1 — falta hacerla con hardware real
diverso (M0.5/M0.6), no se puede fijar un número a ciegas hoy.

### Correlacionar hops de la misma request

`rpc_inference` (la ruta de generación streaming) ya trae `session_id` en
`metadata` (`handler.py:152`, usado para gestión de sesión server-side) — se
puede reusar directo como correlador. `rpc_forward`/`rpc_forward_stream` (la
ruta que usan hoy `client-sdk` y `verifier/dispatch.py`, forward pass sin
sesión de generación) **no siempre trae ese campo** — hay que agregar un
`request_id` explícito al `metadata` desde el cliente (controlamos el fork en
los dos lados, así que es un cambio coordinado simple).

### Firma — hallazgo importante que cambia el enfoque inicial

La idea original (ver roadmap) era reusar la identidad P2P del nodo para
firmar. **No es directamente reusable**: en `hivemind/p2p/p2p_daemon.py:203`,
`identity_path` se pasa como argumento de arranque al daemon p2p (un binario
Go separado, `p2pd`) — la clave privada se carga y usa *dentro de ese proceso*,
no queda disponible como objeto Python en `TransformerConnectionHandler`.

Recomendación: generar y mantener un **par de claves de firma dedicado**, por
fuera de la identidad P2P (mismo espíritu que separar "identidad de red" de
"identidad de atestación" en el roadmap de contratos — reputación no
transferible separada del balance). `hivemind.utils.crypto.RSAPrivateKey` ya
está en el árbol de dependencias y tiene `.sign(data: bytes) -> bytes` listo
para usar — no hace falta traer una librería de crypto nueva. Cargar/generar
una vez al arrancar el servidor (análogo a `--identity_path`, ej.
`--fingerprint_key_path`), guardarlo en la instancia del handler.

### Dónde guardar los fingerprints

Store en memoria acotado (TTL corto, algunos minutos-horas, no la ventana de
disputa completa de 24-72h de Fase 2 — eso requeriría persistencia a disco,
queda como pregunta abierta), indexado por `(request_id, rango_de_bloques)`.
Expuesto vía un RPC nuevo (ej. `rpc_get_fingerprint`) que el `verifier` puede
llamar ante una disputa para pedirle a cada nodo candidato su
`(hash, firma)` de una request pasada, y así encontrar el primer hop donde
las firmas divergen entre caminos en desacuerdo.

### Complejidad real vs. Nivel 1

Nivel 1 fue un cambio solo del lado cliente (`packages/verifier`), no tocó
`petals`. Nivel 2 requiere modificar el server-side de **todos los nodos del
swarm** — hoy no vendoreamos petals en el repo (`infra/docker/swarm-node.Dockerfile`
lo instala vía `pip install` desde un commit pineado, ver ADR 0001), así que
antes de escribir el patch hace falta decidir *cómo* mantenerlo: fork propio
en GitHub, o un archivo de patch aplicado en el Dockerfile. Ninguna de las dos
está resuelta todavía.

### Por qué no se implementó ya

Probarlo en serio necesita un swarm real corriendo el fork modificado — Docker
estaba bloqueado en esta sesión (diálogo de permisos de macOS) cuando se hizo
esta investigación, así que se prioriza dejar el diseño concreto y fundamentado
en vez de escribir código sin poder correrlo ni verificarlo.

### Próximos pasos concretos

1. Decidir mecanismo de vendoring del fork (submodule vs. patch file).
2. Agregar `request_id` a `metadata` en el cliente para `rpc_forward`.
3. Generar/cargar el par de claves de firma dedicado en el arranque del servidor.
4. Hook en `rpc_forward`/`rpc_forward_stream`: hashear + firmar + guardar en el store con TTL.
5. Nuevo RPC `rpc_get_fingerprint` para consultar fingerprints pasados.
6. Calibrar el nivel de redondeo/cuantización con hardware real (M0.5/M0.6).
7. Integrar con `packages/verifier`: cuando `RedundancyVerifier` da un veredicto con `suspect_node_ids`, pedir fingerprints por hop a lo largo del camino sospechoso para acotar a un nodo específico.
