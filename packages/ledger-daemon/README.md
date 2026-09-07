# ledger-daemon

Servicio de créditos simple (SQLite, sin blockchain) para validar el loop económico
básico de la red antes de mover nada a un smart contract — ver
[`docs/roadmap.md`](../../docs/roadmap.md#fase-1--join-permissionless--ledger-simple).

Acredita `compute_units` a un nodo por cada request verificada (la acreditación es
idempotente por `request_id`, para que reintentos del `verifier` no dupliquen saldo).
No tiene autenticación ni ningún tipo de anti-abuso todavía — es intencionalmente el
mínimo necesario para probar el mecanismo, no algo listo para producción.

## Setup

```bash
cd packages/ledger-daemon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Correr

```bash
uvicorn ledger_daemon.main:app --reload
```

Por default guarda en `ledger.db` (configurable con `LEDGER_DB_PATH`).

## Tests

```bash
python -m pytest tests/ -v
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/nodes` | Registra o actualiza un nodo (`node_id`, `display_name` opcional) |
| `GET` | `/nodes` | Lista todos los nodos con su balance, ordenados de mayor a menor |
| `GET` | `/nodes/{node_id}` | Detalle de un nodo + balance |
| `POST` | `/usage` | Acredita una unidad de cómputo verificada (`node_id`, `request_id`, `compute_units`) |
| `GET` | `/nodes/{node_id}/balance` | Balance actual del nodo |
| `GET` | `/nodes/{node_id}/usage` | Historial de acreditaciones del nodo |

Un nodo no necesita registrarse antes de recibir crédito — `POST /usage` lo
auto-registra si no existe. `POST /nodes` sirve para setear un `display_name`
desde el arranque.
