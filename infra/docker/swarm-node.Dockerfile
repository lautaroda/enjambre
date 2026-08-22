# Milestone M0.1 — spike de entorno. Ver docs/roadmap.md.
# Vendoring real (git submodules) queda para después de validar este spike — ver docs/adr/0001.
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN git clone --depth 1 https://github.com/learning-at-home/hivemind.git /opt/hivemind \
    && pip install --no-cache-dir /opt/hivemind

# petals pinea transformers==4.43.1 y bitsandbytes==0.41.1 (este último orientado a CUDA:
# si el import falla en CPU puro, correr los nodos sin --load_in_8bit / en fp32).
RUN git clone --depth 1 https://github.com/bigscience-workshop/petals.git /opt/petals \
    && pip install --no-cache-dir /opt/petals

ENTRYPOINT ["python", "-m", "petals.cli.run_server"]
