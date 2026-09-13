# api-gateway

Expone el swarm de Enjambre detrás de la **API de OpenAI**, para que cualquier
herramienta que ya hable ese protocolo pueda usar la red sin escribir código.

Hasta este paquete, la única forma de consumir la red era Python contra el
`client-sdk`. Si la idea del proyecto es que alguien sin GPU aproveche el
cómputo de otros, tiene que poder apuntarle las herramientas que ya usa.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/v1/chat/completions` | Completions de chat, con y sin streaming (SSE) |
| `GET` | `/v1/models` | El modelo que sirve el swarm |
| `GET` | `/health` | `ok` / `loading` / `error`, con los peers configurados |

## Levantarlo

```bash
MODEL=deepseek-ai/deepseek-coder-6.7b-instruct \
  ./infra/scripts/run-gateway.sh \
  /ip4/192.168.1.135/tcp/31337/p2p/Qm... \
  /ip4/192.168.1.136/tcp/31337/p2p/Qm...
```

`MODEL` tiene que coincidir **exacto** con lo que sirven los nodos, y hay que
pasar las direcciones de **todos** — mismas dos reglas que `chat.sh`, por las
mismas razones (ver `client-sdk/README.md`).

## Usarlo

```bash
aider --openai-api-base http://localhost:8000/v1 \
      --openai-api-key enjambre \
      --model deepseek-ai/deepseek-coder-6.7b-instruct
```

También funciona con Continue y Cline en VS Code, y con Open WebUI. La API key
se ignora: el gateway no autentica todavía (ver *Limitaciones*).

## Decisiones de diseño

**Una petición por vez.** Un modelo de petals mantiene una sesión de inferencia
con estado, repartida entre los nodos; dos `generate()` concurrentes sobre el
mismo objeto se pisan. Se serializa con un lock. No duele: a ~0.9 tokens/seg,
atender dos pedidos a la vez solo haría que los dos tarden el doble.

**Generar bloquea minutos, así que va a un threadpool.** Si se llamara desde el
event loop, `/health` dejaría de responder durante toda la generación.

**Tope duro de `max_tokens` (512 por defecto, `ENJAMBRE_MAX_TOKENS`).** OpenAI
no pone tope; acá hace falta. A 0.9 tokens/seg, 512 tokens ya son casi 10
minutos — sin tope, una herramienta que pida 4096 bloquea la cola una hora.

**El `model` que manda el cliente se ignora.** Varias herramientas mandan su
default sin consultar `/v1/models` primero; rechazarlas por el nombre rompería
la compatibilidad, que es el único motivo por el que este paquete existe.

**Los errores a mitad de streaming van como evento, no como 502.** Una vez
emitidos los headers 200 ya no se puede cambiar el status, así que el error
viaja como un evento SSE y el stream cierra con `[DONE]` igual — que es lo que
hace OpenAI.

## Limitaciones

- **Sin autenticación.** No lo expongas fuera de tu red. Es lo primero a
  resolver antes de que la red sea pública de verdad, junto con asociar cada
  petición a una cuenta del `ledger-daemon` para cobrarla.
- **Sin *function calling*.** `deepseek-coder-6.7b-instruct` no fue entrenado
  para eso, así que las herramientas agénticas que dependen de `tools` no van a
  funcionar aunque el protocolo las acepte.
- **Un solo modelo por gateway**, el que sirvan los nodos.
- **Velocidad.** ~0.9 tokens/seg con nodos CPU. Alcanza para consultas
  puntuales, no para trabajo agéntico — el cuello de botella es el hardware,
  no este paquete.

## Tests

```bash
python3 -m pytest tests/ -q
```

Inyectan un backend falso en `app.state.backend`, así que corren sin torch ni
petals instalados (mismo criterio que el `client-sdk`).
