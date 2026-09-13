# Sumar un nodo desde Windows (ej. ROG Ally X)

`infra/scripts/run-remote-node.sh` es un script de bash pensado para Linux —
en Windows el camino más simple es correrlo **dentro de WSL2**, no reescribirlo
para PowerShell. Docker Desktop en Windows ya usa WSL2 como motor por debajo,
así que es el mismo mecanismo, sin mantener una segunda versión del script.

No probado contra hardware Windows real todavía (mismo aviso que con ROCm) —
mandame el error exacto si algo no sale como acá.

## Paso 1 — instalar WSL2 + Ubuntu

En PowerShell **como administrador**:

```powershell
wsl --install
```

Instala WSL2 y Ubuntu por default. Reiniciá si te lo pide, y al abrir Ubuntu
por primera vez te va a pedir crear un usuario/contraseña de Linux (separado
de tu usuario de Windows).

## Paso 2 — instalar Docker Desktop

Descargar e instalar [Docker Desktop para Windows](https://www.docker.com/products/docker-desktop/).
Durante la instalación (o después, en Settings → General) confirmar que esté
tildado **"Use the WSL 2 based engine"** (es el default hoy). Después, en
Settings → Resources → WSL Integration, activar el toggle para la distro
"Ubuntu" — sin esto, Docker no es visible desde adentro de WSL.

## Paso 3 — correr el nodo desde la terminal de Ubuntu (WSL)

Abrí "Ubuntu" desde el menú de Windows (no PowerShell) y corré el mismo
comando que en cualquier máquina Linux — ver
[`docs/m0-5-remote-setup.md`](m0-5-remote-setup.md) para el flujo completo de
roles (ancla / se suma). Por ejemplo, para sumarse a un nodo ancla que ya está
corriendo en otra máquina:

```bash
curl -fsSL https://raw.githubusercontent.com/lautaroda/enjambre/main/infra/scripts/run-remote-node.sh -o run-remote-node.sh
chmod +x run-remote-node.sh
ROLE=follower INITIAL_PEERS=<multiaddr-del-nodo-ancla> ./run-remote-node.sh
```

## GPU (APU integrada Ryzen Z1 Extreme) — no por ahora

La Ally X tiene gráfica integrada (RDNA3 dentro del mismo chip, memoria
compartida con la CPU), no una placa aparte. El soporte de ROCm para APUs
integradas es todavía más incierto que para una GPU discreta como la RX 5700
XT (ver [`docs/gpu-node-setup.md`](gpu-node-setup.md)), y encima sumaría la
capa de WSL2 arriba — hoy no vale la pena esa complejidad. Arrancar por CPU acá
también.
