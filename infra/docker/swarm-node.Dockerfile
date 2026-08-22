# Milestone M0.1 — spike de entorno. Ver docs/roadmap.md.
# Vendoring real (git submodules) queda para después de validar este spike — ver docs/adr/0001.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

# Tanto petals como el commit de hivemind que necesita (ver mas abajo) hacen
# `import pkg_resources` directo en su setup.py (patron legacy); setuptools
# recientes ya no lo incluyen por default, lo que rompe su build aislada. Fijamos
# una version que todavia lo trae, y build isolation queda desactivado para ambos
# (mas abajo) para que reutilicen esta version en vez de bajar la ultima.
#
# Al desactivar build isolation, cada paquete pierde el auto-provisioning de SUS
# propias build-dependencies declaradas (normalmente resuelto por el venv aislado).
# hivemind necesita grpcio-tools en build-time para compilar sus .proto - lo
# instalamos ya en el entorno principal para que lo encuentre.
RUN pip install --no-cache-dir "setuptools<81" wheel grpcio-tools

# petals declara en su propio setup.py una dependencia de un commit especifico de
# hivemind (no el HEAD de main, que ya expone una API distinta: hivemind.PeerID no
# existe en HEAD actual).
RUN pip install --no-cache-dir --no-build-isolation \
    "hivemind @ git+https://github.com/learning-at-home/hivemind.git@213bff98a62accb91f254e2afdccbf1d69ebdea9"

# petals pinea tambien transformers==4.43.1 y bitsandbytes==0.41.1 (este ultimo orientado
# a CUDA: si el import falla en CPU puro, correr los nodos sin --load_in_8bit / en fp32).
RUN git clone --depth 1 https://github.com/bigscience-workshop/petals.git /opt/petals \
    && pip install --no-cache-dir --no-build-isolation /opt/petals

ENTRYPOINT ["python", "-m", "petals.cli.run_server"]
