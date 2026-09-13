# M0.5 — setup de nodos reales (cloud + gente de confianza)

Objetivo: medir latencia de red real y ejercitar el NAT traversal de hivemind, que
M0.3 (todo en localhost vía docker-compose) no puede probar. Usa
[`infra/scripts/run-remote-node.sh`](../infra/scripts/run-remote-node.sh) — un
script standalone (no depende de docker-compose) pensado para correr en una VM
cloud o en la máquina de un amigo, sin que tengan que clonar nada a mano.

## Roles

- **Nodo ancla**: necesita **IP pública** — una VM cloud barata. Es el primer nodo,
  ancla el DHT (`--new_swarm`) y anuncia su IP para que el resto lo encuentre.
- **Nodos que se suman**: **no necesitan IP pública** — funcionan detrás de NAT
  doméstico (la máquina de un amigo, o una segunda VM). Esto es justo lo que el
  NAT traversal de hivemind resuelve — es la parte que este milestone valida.

Con la decisión ya tomada (cloud + amigos en paralelo): 1 VM cloud como ancla,
+ otra VM cloud y/o 1-2 amigos como nodos que se suman.

**¿Tenés una máquina con GPU propia?** Es un nodo mucho más interesante que
una VM cloud CPU-only, y de paso empieza a cubrir M0.6 (modelo grande) además
de M0.5. Para GPU AMD/ROCm (ej. RX 5700 XT), ver
[`docs/gpu-node-setup.md`](gpu-node-setup.md) antes de seguir con los pasos de
abajo. Para sumar una máquina Windows (ej. una ROG Ally X), ver
[`docs/windows-node-setup.md`](windows-node-setup.md).

## Paso 1 — provisionar la VM ancla

Una instancia chica alcanza (bloom-560m corre bien en CPU): Hetzner CX22 o
DigitalOcean basic droplet, Ubuntu 22.04/24.04, ~USD 4-6/mes. Esto lo hacés vos
directamente en la consola del proveedor — implica poner una tarjeta, así que no
es algo que yo pueda iniciar por vos.

Abrí el puerto **31337/tcp** en el firewall del proveedor (Hetzner Cloud Firewall
/ DigitalOcean Cloud Firewall) o con `ufw allow 31337/tcp` en la VM. Sin esto, los
demás nodos no van a poder alcanzar el ancla.

## Paso 2 — arrancar el nodo ancla

SSH a la VM y corré:

```bash
curl -fsSL https://raw.githubusercontent.com/lautaroda/enjambre/main/infra/scripts/run-remote-node.sh -o run-remote-node.sh
chmod +x run-remote-node.sh
ROLE=anchor PUBLIC_IP=<ip-publica-de-la-vm> ./run-remote-node.sh
```

Mirá los logs hasta ver `Announced that blocks ... are joining`:

```bash
docker logs -f enjambre-node
```

Copiá la línea que empieza con `/ip4/<ip-publica>/tcp/31337/p2p/...` — es el
`INITIAL_PEERS` que necesita todo el que se sume.

## Paso 3 — sumar el resto de los nodos

Mandale a cada amigo (o corré vos mismo en la segunda VM) el mismo script, con
`ROLE=follower` y el `INITIAL_PEERS` del paso anterior:

```bash
curl -fsSL https://raw.githubusercontent.com/lautaroda/enjambre/main/infra/scripts/run-remote-node.sh -o run-remote-node.sh
chmod +x run-remote-node.sh
ROLE=follower INITIAL_PEERS=/ip4/<ip-del-ancla>/tcp/31337/p2p/<peer-id> ./run-remote-node.sh
```

No necesitan abrir ningún puerto en su router — eso es justo lo que se está
probando. Por defecto cada nodo pide 8 bloques (`NUM_BLOCKS=8`); con 3 nodos
sumados (ancla + 2) alcanza para cubrir los 24 de bloom-560m. Si se suma más o
menos gente, ajustá `NUM_BLOCKS` para que la suma dé ~24.

## Paso 4 — verificar y medir

Desde cualquier máquina con Docker (puede ser tu Mac), corré el mismo harness de
M0.4 apuntando al `INITIAL_PEERS` del ancla en vez de a un servicio local:

```bash
export BOOTSTRAP_MADDR=/ip4/<ip-del-ancla>/tcp/31337/p2p/<peer-id>
docker compose -f infra/docker-compose.dev.yml run --rm --no-deps --entrypoint python3 \
  -e BOOTSTRAP_MADDR="$BOOTSTRAP_MADDR" client benchmarks/correctness_check.py
```

Anotá en [`docs/phase0-poc-report.md`](phase0-poc-report.md):

- Latencia por token / tokens por segundo (compará contra el resultado de M0.3
  en localhost — la diferencia es el costo real de la red).
- Si la generación se recupera o se rompe si matás uno de los contenedores
  `enjambre-node` a mitad de una respuesta (`docker stop enjambre-node` en uno de
  los nodos que se sumaron, no en el ancla).
- Cualquier problema de conectividad/NAT que haya aparecido.

Con esos datos, M0.7 puede cerrar con una recomendación go/no-go para Fase 1.
