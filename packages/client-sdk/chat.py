#!/usr/bin/env python3
"""CLI de chat contra el swarm de Enjambre - REPL simple sobre EnjambreClient.

Uso:
    python3 chat.py --peers /ip4/192.168.1.135/tcp/31337/p2p/<peer-id>

Ojo: bloom-560m (el modelo con el que venimos probando) es un modelo base,
no ajustado para chat/instrucciones - completa texto, no "responde" como un
asistente. Para algo mas parecido a una conversacion real hace falta un
modelo instruct/chat (ver docs/gpu-node-setup.md sobre probar algo mas
grande una vez validada la conectividad de 3 nodos).
"""

import argparse

from client_sdk import EnjambreClient, EnjambreConnectionError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--peers", required=True, nargs="+", help="multiaddr(s) de initial_peers del swarm"
    )
    parser.add_argument("--model", default="bigscience/bloom-560m")
    parser.add_argument("--max-new-tokens", type=int, default=60)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument(
        "--repetition-penalty",
        type=float,
        default=1.2,
        help="Sin esto (o en 1.0) un modelo base chico entra en loop enseguida",
    )
    args = parser.parse_args()

    print(f"Conectando a {args.model} via {args.peers}...")
    client = EnjambreClient(initial_peers=args.peers, model_name=args.model)

    history = ""
    print("Chat con el swarm de Enjambre. 'salir' o Ctrl+C para terminar.\n")
    while True:
        try:
            user_input = input("vos> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChau.")
            break
        if user_input.lower() in ("salir", "exit", "quit"):
            break
        if not user_input:
            continue

        history += f"{user_input}\n"
        try:
            response = client.generate(
                history,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
                repetition_penalty=args.repetition_penalty,
            )
        except EnjambreConnectionError as exc:
            print(f"[error de conexión al swarm: {exc}]")
            continue

        new_text = response[len(history):] if response.startswith(history) else response
        print(f"swarm> {new_text.strip()}\n")
        history += new_text


if __name__ == "__main__":
    main()
