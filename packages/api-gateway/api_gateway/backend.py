"""Puente entre la API HTTP y el swarm.

Dos cosas que este modulo resuelve y que no son obvias:

1. **Una peticion por vez.** Un modelo de petals mantiene una sesion de
   inferencia con estado (el cache de atencion repartido entre los nodos);
   dos `generate()` concurrentes sobre el mismo objeto se pisan. Se serializa
   con un lock. No es una limitacion que duela: a ~0.9 tokens/seg en CPU,
   atender dos pedidos a la vez solo lograria que los dos tarden el doble.

2. **Generar bloquea durante minutos.** `generate()` es sincronico y puede
   tardar varios minutos. Si se llamara desde el event loop de FastAPI,
   /health y /v1/models dejarian de responder mientras tanto. Por eso main.py
   lo corre en un threadpool; este modulo es deliberadamente sincronico y no
   sabe nada de asyncio.

La clase `SwarmBackend` define la interfaz para que los tests puedan inyectar
una implementacion falsa sin instalar torch ni petals (mismo criterio que el
client-sdk).
"""

import threading
from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str  # "stop" | "length"


class SwarmBackend(Protocol):
    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, top_p: float
    ) -> GenerationResult: ...

    def stream(
        self, messages: list[dict], max_tokens: int, temperature: float, top_p: float
    ) -> Iterator[str]: ...

    def count_prompt_tokens(self, messages: list[dict]) -> int: ...


class PetalsBackend:
    """Implementacion real: habla con el swarm via client-sdk."""

    def __init__(self, peers: list[str], model_name: str):
        self.peers = peers
        self.model_name = model_name
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self):
        if self._client is None:
            from client_sdk import EnjambreClient

            self._client = EnjambreClient(initial_peers=self.peers, model_name=self.model_name)
        return self._client

    def warmup(self) -> None:
        """Fuerza la carga del modelo. Conviene llamarlo al arrancar: la
        primera carga baja las capas de embeddings (~260MB para un 6.7B) y
        tarda minutos, y es mejor pagarlo al arranque que en la primera
        peticion de un usuario."""
        self._get_client().tokenizer

    def count_prompt_tokens(self, messages: list[dict]) -> int:
        client = self._get_client()
        prompt = client.format_chat(messages)
        return len(client.tokenizer(prompt)["input_ids"])

    def _gen_kwargs(self, temperature: float, top_p: float) -> dict:
        # temperature=0 en la API de OpenAI significa "determinista". En
        # transformers eso no es do_sample con temperature 0 (division por
        # cero), es do_sample=False.
        if temperature <= 0:
            return {"do_sample": False}
        return {
            "do_sample": True,
            "temperature": temperature,
            "top_p": top_p,
            "repetition_penalty": 1.05,
        }

    def generate(
        self, messages: list[dict], max_tokens: int, temperature: float, top_p: float
    ) -> GenerationResult:
        client = self._get_client()
        with self._lock:
            prompt = client.format_chat(messages)
            tok = client.tokenizer
            inputs = tok(prompt, return_tensors="pt")
            n_prompt = inputs["input_ids"].shape[1]
            outputs = client.model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                pad_token_id=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id,
                max_new_tokens=max_tokens,
                **self._gen_kwargs(temperature, top_p),
            )
            new_ids = outputs[0][n_prompt:]
            text = tok.decode(new_ids, skip_special_tokens=True)
            n_new = len(new_ids)
        return GenerationResult(
            text=text,
            prompt_tokens=n_prompt,
            completion_tokens=n_new,
            # Si consumio todo el presupuesto, para OpenAI es "length"; si corto
            # antes fue por el token de fin, o sea "stop".
            finish_reason="length" if n_new >= max_tokens else "stop",
        )

    def stream(
        self, messages: list[dict], max_tokens: int, temperature: float, top_p: float
    ) -> Iterator[str]:
        from transformers import TextIteratorStreamer

        client = self._get_client()
        with self._lock:
            prompt = client.format_chat(messages)
            tok = client.tokenizer
            inputs = tok(prompt, return_tensors="pt")
            streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
            error: list[BaseException] = []

            def _run():
                try:
                    client.model.generate(
                        inputs["input_ids"],
                        attention_mask=inputs["attention_mask"],
                        pad_token_id=(
                            tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
                        ),
                        max_new_tokens=max_tokens,
                        streamer=streamer,
                        **self._gen_kwargs(temperature, top_p),
                    )
                except BaseException as exc:  # se re-lanza en el hilo que consume
                    error.append(exc)
                finally:
                    # Sin esto, un fallo a mitad de generacion deja al consumidor
                    # colgado para siempre esperando tokens que nunca llegan.
                    streamer.end()

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            for piece in streamer:
                yield piece
            thread.join()
            if error:
                raise error[0]
