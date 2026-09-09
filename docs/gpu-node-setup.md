# Provisionar un nodo con GPU AMD (ROCm)

Guía para sumar una máquina Ubuntu con GPU AMD (ej. RX 5700 XT, 8GB) como nodo
de Enjambre. **No probado contra hardware real todavía** — lo armé investigando
cómo funciona ROCm/PyTorch en general, sin acceso a una GPU AMD para
verificarlo yo mismo. Es muy probable que algún paso necesite ajustes reales —
mandame el error exacto que te tire y lo resolvemos juntos, como hicimos con
los bugs de Docker/CPU.

## Aviso importante sobre la RX 5700 XT específicamente

Es una GPU RDNA1 (arquitectura `gfx1010`). El soporte oficial de ROCm para
RDNA1 en consumo (no datacenter) fue históricamente inconsistente entre
versiones — puede que necesites forzar la variable de entorno
`HSA_OVERRIDE_GFX_VERSION=10.3.0` (le dice a ROCm que trate la GPU como si
fuera una arquitectura más nueva y sí soportada — truco de comunidad conocido,
no garantizado) o que la versión de ROCm que instales directamente no la
reconozca. Verificá la [matriz de compatibilidad oficial](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html)
para la versión de ROCm que vayas a instalar antes de invertir tiempo.

## Paso 1 — instalar ROCm en el host Ubuntu (no dentro de Docker)

El driver del kernel (`amdgpu-dkms`) tiene que estar en el host — no se puede
meter dentro de un contenedor. Seguí la [guía oficial de instalación de AMD](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/)
para tu versión exacta de Ubuntu. Después de instalar y reiniciar, verificá:

```bash
rocminfo | grep -A 3 "Marketing Name"
rocm-smi
```

Si `rocminfo` no lista tu GPU, no sigas con los pasos de abajo — es un
problema de la instalación de ROCm en el host, previo a todo lo de Enjambre.

## Paso 2 — permisos de Docker para acceder a la GPU

Tu usuario necesita estar en los grupos `video` y `render` (además de `docker`,
que ya instala `run-remote-node.sh` si hace falta):

```bash
sudo usermod -aG video,render $USER
# cerrar sesion y volver a entrar para que tome efecto
```

## Paso 3 — correr el nodo

Mismo script que para cualquier nodo remoto ([`infra/scripts/run-remote-node.sh`](../infra/scripts/run-remote-node.sh),
ver [`docs/m0-5-remote-setup.md`](m0-5-remote-setup.md) para el resto del
flujo de M0.5), agregando `BACKEND=rocm`. Empezá con `bloom-560m` (rápido,
ya validado en M0.1-M0.4) para confirmar que ROCm+petals funciona en esta
máquina antes de probar algo más grande:

```bash
curl -fsSL https://raw.githubusercontent.com/lautaroda/enjambre/main/infra/scripts/run-remote-node.sh -o run-remote-node.sh
chmod +x run-remote-node.sh
BACKEND=rocm ROLE=anchor PUBLIC_IP=<ip-de-esta-maquina-en-tu-red> ./run-remote-node.sh
docker logs -f enjambre-node
```

Si la GPU no arranca (`HSA_OVERRIDE_GFX_VERSION`), agregalo a mano una vez que
tengas el contenedor corriendo:

```bash
docker rm -f enjambre-node
docker run -d --name enjambre-node --restart unless-stopped \
  --device=/dev/kfd --device=/dev/dri --group-add=video --group-add=render \
  --security-opt seccomp=unconfined \
  -e HSA_OVERRIDE_GFX_VERSION=10.3.0 \
  -p 31337:31337 -v enjambre-node-identity:/root/.hivemind \
  enjambre/swarm-node:rocm bigscience/bloom-560m --new_swarm \
  --device cuda --identity_path /root/.hivemind/node.id \
  --host_maddrs /ip4/0.0.0.0/tcp/31337 --announce_maddrs /ip4/<tu-ip>/tcp/31337
```

## Paso 4 — una vez que bloom-560m funciona: modelo más grande

Con 8GB de VRAM alcanza para algo bastante más interesante que bloom-560m —
esto sería ya cubrir [M0.6](https://github.com/lautaroda/enjambre/issues/2).
Probá con `--quant_type none` primero (evita depender de `bitsandbytes`, que
tiene soporte ROCm más parchado que CUDA):

```bash
MODEL="meta-llama/Llama-2-7b-hf" BACKEND=rocm ROLE=anchor PUBLIC_IP=<tu-ip> ./run-remote-node.sh
```

Llama-2 requiere aceptar su licencia en Hugging Face y pasar un token
(`--token`) — si da error de acceso, es por eso, no un problema de ROCm.

## Qué anotar si algo falla

Mandame el `docker logs enjambre-node` completo del error — con eso puedo
ajustar el Dockerfile o el comando, igual que fuimos resolviendo cada bug real
del setup de CPU en esta misma sesión.
