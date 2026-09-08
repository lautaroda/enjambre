"""SDK para pedir inferencia a la red sin hablar directo con hivemind/petals.

La carga del modelo (`_load`) importa torch/petals de forma diferida (dentro
del metodo, no a nivel de modulo) para que la logica de reintentos/backoff se
pueda testear sin esas dependencias pesadas instaladas - ver tests/test_client.py
y el README de este paquete.
"""

import time


class EnjambreConnectionError(Exception):
    """No se pudo completar la generación tras los reintentos configurados."""


class EnjambreClient:
    def __init__(
        self,
        initial_peers: list[str],
        model_name: str,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        sleep_fn=time.sleep,
    ):
        self.initial_peers = initial_peers
        self.model_name = model_name
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._sleep = sleep_fn
        self._model = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from petals import AutoDistributedModelForCausalLM
        from transformers import AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoDistributedModelForCausalLM.from_pretrained(
            self.model_name, initial_peers=self.initial_peers
        ).eval()

    def _generate_once(self, prompt: str, max_new_tokens: int) -> str:
        inputs = self._tokenizer(prompt, return_tensors="pt")
        outputs = self._model.generate(inputs["input_ids"], max_new_tokens=max_new_tokens)
        return self._tokenizer.decode(outputs[0])

    def generate(self, prompt: str, max_new_tokens: int = 20) -> str:
        """Genera texto. Si un nodo falla a mitad de pipeline, reintenta con
        backoff exponencial (max_retries intentos) antes de levantar
        EnjambreConnectionError. petals ya reintenta internamente errores de
        red puntuales; esto cubre el caso en que esos reintentos internos no
        alcanzan (ej. el nodo que se cayó no vuelve en el timeout de petals)."""
        self._load()
        return self._with_retries(lambda: self._generate_once(prompt, max_new_tokens))

    def _with_retries(self, fn):
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return fn()
            except Exception as exc:  # petals no expone una jerarquia de excepciones estable
                last_error = exc
                if attempt < self.max_retries - 1:
                    self._sleep(self.retry_backoff * (2**attempt))
        raise EnjambreConnectionError(
            f"No se pudo completar la generación tras {self.max_retries} intentos "
            f"contra {self.initial_peers}: {last_error}"
        ) from last_error
