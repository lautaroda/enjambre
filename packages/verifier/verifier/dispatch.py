"""Despacha la misma request a N pipelines del swarm en paralelo, para que
RedundancyVerifier compare los resultados.

Necesita el mismo entorno que swarm-node (torch + petals) - correr dentro de
infra/docker/swarm-node.Dockerfile, NO en el venv liviano del resto de este
paquete (compare.py/redundancy.py/ledger_client.py solo necesitan numpy+httpx
a proposito, para poder testearlos rapido sin la imagen pesada). Ver README.

Atribucion de node_ids: hoy el llamador tiene que saber de antemano que nodos
sirven cada peer_set (ej. porque el swarm todavia se arma con --block_indices
explicitos, como en M0.3). Determinar automaticamente que nodos sirvieron una
corrida a partir de una sesion de petals queda para la Verificacion Nivel 2
(issue #5).
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from .redundancy import RunResult


class _ThreadWarningCapture(logging.Handler):
    """Captura warnings emitidos SOLO por el hilo que corre esta corrida
    (filtra por thread id) - varias corridas se despachan en paralelo via
    threads, y un logger compartido recibe records de todos los hilos a la
    vez, no solo del propio."""

    def __init__(self, thread_id: int):
        super().__init__(level=logging.WARNING)
        self._thread_id = thread_id
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self._thread_id:
            self.messages.append(record.getMessage())


def _run_one(prompt, model_name, initial_peers, node_ids, tokenizer):
    from petals import AutoDistributedModelForCausalLM
    import torch

    capture = _ThreadWarningCapture(threading.get_ident())
    # se engancha al logger raiz y explicitamente a hivemind/petals, por si
    # alguno de los dos desactiva propagate en su propio logger interno
    loggers = [logging.getLogger(), logging.getLogger("hivemind"), logging.getLogger("petals")]
    for logger in loggers:
        logger.addHandler(capture)
    try:
        model = AutoDistributedModelForCausalLM.from_pretrained(
            model_name, initial_peers=initial_peers
        ).eval()
        inputs = tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits[0, -1, :].numpy()
    finally:
        for logger in loggers:
            logger.removeHandler(capture)

    return RunResult(node_ids=node_ids, logits=logits, had_warnings=bool(capture.messages))


def run_redundant(
    prompt: str, model_name: str, peer_sets: list[tuple[list[str], list[str]]]
) -> list[RunResult]:
    """peer_sets: una entrada (initial_peers, node_ids) por corrida a lanzar
    en paralelo - 2-3 en la practica (ver docs/roadmap.md)."""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    with ThreadPoolExecutor(max_workers=len(peer_sets)) as pool:
        futures = [
            pool.submit(_run_one, prompt, model_name, initial_peers, node_ids, tokenizer)
            for initial_peers, node_ids in peer_sets
        ]
        return [f.result() for f in futures]
