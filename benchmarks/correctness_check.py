#!/usr/bin/env python3
"""
M0.4 - compara los logits de bloom-560m corrido (a) localmente con transformers
y (b) distribuido via petals, para calibrar el umbral de similaridad coseno que
despues usa la capa de verificacion por redundancia (docs/roadmap.md).

Se corre DENTRO del contenedor `client` (infra/docker-compose.dev.yml), no en el
host, porque depende de torch/transformers/petals instalados ahi.
"""
import argparse
import os
import sys

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_NAME = "bigscience/bloom-560m"
DEFAULT_PROMPT = "The quick brown fox"
DEFAULT_COSINE_THRESHOLD = 0.999


def local_logits(prompt, tokenizer):
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME).eval()
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        return model(**inputs).logits[0, -1, :]


def distributed_logits(prompt, tokenizer, initial_peers):
    from petals import AutoDistributedModelForCausalLM

    model = AutoDistributedModelForCausalLM.from_pretrained(
        MODEL_NAME, initial_peers=initial_peers
    ).eval()
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        return model(**inputs).logits[0, -1, :]


def compare(a, b):
    cos_sim = F.cosine_similarity(a.unsqueeze(0), b.unsqueeze(0)).item()
    rel_norm = (a - b).norm().item() / a.norm().item()
    return cos_sim, rel_norm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_COSINE_THRESHOLD,
        help="Umbral minimo de similaridad coseno para considerar la corrida 'valida'",
    )
    args = parser.parse_args()

    initial_peers_env = os.environ.get("BOOTSTRAP_MADDR")
    if not initial_peers_env:
        print(
            "Falta la variable de entorno BOOTSTRAP_MADDR (ver infra/docker-compose.dev.yml)",
            file=sys.stderr,
        )
        return 1

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    print(f"Corriendo '{args.prompt}' localmente (transformers)...")
    baseline = local_logits(args.prompt, tokenizer)

    print(f"Corriendo '{args.prompt}' distribuido (petals, peers={initial_peers_env})...")
    distributed = distributed_logits(args.prompt, tokenizer, [initial_peers_env])

    cos_sim, rel_norm = compare(baseline, distributed)
    print(f"similaridad coseno = {cos_sim:.6f}   norma relativa = {rel_norm:.6f}")

    if cos_sim >= args.threshold:
        print("OK - dentro del umbral de tolerancia.")
        return 0

    print(f"FALLO - por debajo del umbral ({args.threshold}).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
