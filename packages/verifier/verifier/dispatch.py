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

from concurrent.futures import ThreadPoolExecutor

from .redundancy import RunResult


def _run_one(prompt, model_name, initial_peers, node_ids, tokenizer):
    from petals import AutoDistributedModelForCausalLM
    import torch

    model = AutoDistributedModelForCausalLM.from_pretrained(
        model_name, initial_peers=initial_peers
    ).eval()
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits[0, -1, :].numpy()
    return RunResult(node_ids=node_ids, logits=logits)


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
