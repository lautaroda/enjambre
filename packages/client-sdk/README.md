# client-sdk

SDK para que un usuario final pida inferencia al swarm sin tener que hablar
directo con `hivemind`/`petals`: carga el modelo una sola vez (reusable entre
llamadas a `generate()`, a diferencia de instanciar `AutoDistributedModelForCausalLM`
cada vez) y reintenta con backoff exponencial si un nodo falla a mitad de pipeline.

## Uso

> **Ojo con `initial_peers` en swarms chicos**: pasá la dirección de **todos**
> los nodos, no solo la del ancla. Con solo el ancla, el cliente obtiene del
> DHT el *ID* del peer que sirve cada rango de bloques pero no su *dirección*,
> y al resolverla por DHT falla con `routing: not found` (en un swarm de pocos
> nodos no hay suficiente red para resolverlo). Hallazgo real de M0.5 — ver
> [`docs/phase0-poc-report.md`](../../docs/phase0-poc-report.md).

```python
from client_sdk import EnjambreClient

client = EnjambreClient(
    initial_peers=[
        "/ip4/<ip-nodo-1>/tcp/31337/p2p/<peer-id-1>",
        "/ip4/<ip-nodo-2>/tcp/31337/p2p/<peer-id-2>",
        "/ip4/<ip-nodo-3>/tcp/31337/p2p/<peer-id-3>",
    ],
    model_name="bigscience/bloom-560m",
)

texto = client.generate("A short story about a robot who", max_new_tokens=20)
print(texto)

# el modelo queda cargado - la siguiente llamada no vuelve a pagar el costo
# de conexion/carga
texto2 = client.generate("Otro prompt distinto")
```

Si la generación falla (ej. un nodo del pipeline se cae y los reintentos
internos de `petals` no alcanzan), reintenta hasta `max_retries` veces con
backoff exponencial (default: 3 intentos, arrancando en 2s) antes de levantar
`EnjambreConnectionError` con el motivo original adentro.

## Setup para USAR el SDK (entorno pesado - torch + petals)

Igual que `packages/verifier/dispatch.py`, esto necesita el mismo entorno que
`swarm-node` — correr dentro de `infra/docker/swarm-node.Dockerfile`, no en un
venv con `pip install` directo (las mismas razones documentadas ahí: pin de
`setuptools`, commit exacto de `hivemind`, etc.).

## Tests (livianos, no necesitan torch/petals)

`test_client.py` testea la lógica de reintentos/backoff directamente (sin
cargar ningún modelo real — `_load()` hace el import de `petals` de forma
diferida a propósito para esto). Alcanza con:

```bash
cd packages/client-sdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```
