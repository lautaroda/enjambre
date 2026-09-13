"""SDK para pedir inferencia a la red sin hablar directo con hivemind/petals.

IMPORTANTE - initial_peers en swarms chicos: hay que pasar la direccion de
TODOS los nodos del swarm, no solo la del ancla. Encontrado en la prueba real
de M0.5 (3 maquinas): con solo el ancla, el DHT le dice al cliente "el peer X
sirve los bloques 8-16" pero el cliente tiene el ID del peer sin su direccion,
y cae a resolverla via DHT FindPeer - que en un swarm de pocos nodos falla con
`routing: not found` y la inferencia nunca arranca. Pasando todas las
direcciones, el cliente llena su peerstore al conectar y no depende del DHT
para eso. En un swarm grande (ej. el publico de petals) esto no hace falta
porque el cliente termina conectado a muchos servidores igual.

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

    def format_chat(self, messages: list[dict]) -> str:
        """Arma el prompt final a partir de una lista de mensajes
        {role, content}, usando la chat_template propia del tokenizer si el
        modelo tiene una definida - asi el modelo ve el formato con el que
        fue afinado. Encontrado real: deepseek-coder-instruct espera un
        formato especifico ("### Instruction:" / "### Response:" + un system
        prompt fijo), no texto plano concatenado - sin esto las respuestas
        salian entrecortadas, no por ser un modelo chico sino por el prompt
        mal formado. Si el modelo no tiene chat_template (ej. un modelo base
        como bloom-560m), cae a concatenar el contenido de los mensajes."""
        self._load()
        if getattr(self._tokenizer, "chat_template", None):
            return self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        return "\n".join(m["content"] for m in messages) + "\n"

    def _generate_once(self, prompt: str, max_new_tokens: int, **gen_kwargs) -> str:
        inputs = self._tokenizer(prompt, return_tensors="pt")
        outputs = self._model.generate(
            inputs["input_ids"], max_new_tokens=max_new_tokens, **gen_kwargs
        )
        return self._tokenizer.decode(outputs[0])

    def generate(
        self, prompt: str, max_new_tokens: int = 20, stream: bool = False, **gen_kwargs
    ) -> str:
        """Genera texto. Si un nodo falla a mitad de pipeline, reintenta con
        backoff exponencial (max_retries intentos) antes de levantar
        EnjambreConnectionError. petals ya reintenta internamente errores de
        red puntuales; esto cubre el caso en que esos reintentos internos no
        alcanzan (ej. el nodo que se cayó no vuelve en el timeout de petals).

        Defaults de sampling: sin esto, generate() hace decodificación greedy y
        un modelo base chico como bloom-560m entra en loop enseguida ("Estoy
        bien. ¿Estás bien? Estoy bien...") - visto en la primera prueba real de
        chat. do_sample + repetition_penalty lo corta. Cualquiera se puede
        pisar pasandolo explicito en gen_kwargs.

        stream=True imprime el texto a stdout token por token a medida que se
        genera (via transformers.TextStreamer), en vez de esperar la respuesta
        completa - el valor de retorno sigue siendo el texto final completo,
        igual que sin stream. Un streamer nuevo por intento (no se reusa entre
        reintentos)."""
        self._load()
        base_params = {
            "do_sample": True,
            "temperature": 0.8,
            "top_p": 0.9,
            "repetition_penalty": 1.2,
            **gen_kwargs,
        }

        def _call():
            params = dict(base_params)
            if stream:
                from transformers import TextStreamer

                params["streamer"] = TextStreamer(
                    self._tokenizer, skip_prompt=True, skip_special_tokens=True
                )
            return self._generate_once(prompt, max_new_tokens, **params)

        return self._with_retries(_call)

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
