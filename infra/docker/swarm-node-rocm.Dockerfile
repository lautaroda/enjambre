# Variante GPU (AMD/ROCm) de swarm-node.Dockerfile - misma logica de instalacion
# de hivemind/petals (ver ese archivo para el detalle de cada fix de dependencias:
# setuptools<81, no-build-isolation, commit exacto de hivemind), pero con torch
# para ROCm en vez de CPU. NO probado contra hardware real todavia (ver
# docs/gpu-node-setup.md) - el host necesita el driver/stack de ROCm instalado
# ANTES de correr esto (no se puede instalar el kernel driver dentro de un
# contenedor).
#
# Verificar el tag exacto disponible antes de buildear:
# https://hub.docker.com/r/rocm/dev-ubuntu-22.04/tags - la version de ROCm de la
# imagen debe ser compatible con la que instalaste en el host.
FROM rocm/dev-ubuntu-22.04:6.1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --extra-index-url, NO --index-url (el segundo reemplaza TODO el indice de
# PyPI, no solo agrega uno nuevo - bug real que ya pisamos una vez con la
# variante CPU, ver infra/docker/swarm-node.Dockerfile).
RUN pip3 install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/rocm6.1

# Mismos 3 fixes que la variante CPU (ver ese Dockerfile para el detalle de por
# que hace falta cada uno): pkg_resources faltante en setuptools recientes,
# grpc_tools faltante al desactivar build isolation, y el commit exacto de
# hivemind que petals espera (no el HEAD de main).
RUN pip3 install --no-cache-dir "setuptools<81" wheel grpcio-tools

RUN pip3 install --no-cache-dir --no-build-isolation \
    "hivemind @ git+https://github.com/learning-at-home/hivemind.git@213bff98a62accb91f254e2afdccbf1d69ebdea9"

RUN git clone --depth 1 https://github.com/bigscience-workshop/petals.git /opt/petals \
    && pip3 install --no-cache-dir --no-build-isolation /opt/petals

ENTRYPOINT ["python3", "-m", "petals.cli.run_server"]
