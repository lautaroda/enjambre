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

import json
import time


class EnjambreConnectionError(Exception):
    """No se pudo completar la generación tras los reintentos configurados."""


def byte_fallback_token_ids(added_tokens: list[dict]) -> list[int]:
    """IDs de los "added tokens" que en realidad son bytes crudos, no texto.

    El tokenizer de deepseek-coder registra 13 tokens (32000-32012) cuyo
    contenido es un caracter Latin-1 suelto ('ú', 'ü', 'Á', 'ö'...) pero que
    NO representan esa letra: son el respaldo a nivel byte del vocabulario
    (el token 'ú' vale el byte 0xFA). El problema es que el matcher de added
    tokens los busca como texto literal ANTES de aplicar BPE, asi que al
    escribir "número" la 'ú' se mapea al token 32007 y al decodificar sale el
    byte 0xFA suelto, que es UTF-8 invalido -> 'n�mero'.

    Esto corrompe el texto **antes de que el modelo lo vea**, no solo la
    salida. Verificado con un ida y vuelta puro del tokenizer, sin modelo:

        'números únicos, pingüino, Álvaro'  ->  'n?meros ?nicos, ping?ino, ?lvaro'

    Afecta a u-acento, dieresis y A-acento mayuscula, entre otros; a-e-i-o
    acentuadas y enie no estan en la lista y funcionan bien. Pasa igual con
    el tokenizer rapido y con el lento, asi que no es un bug de implementacion
    sino de como vienen declarados los tokens.

    El criterio para identificarlos es preciso: no son especiales, miden un
    solo caracter, y ese caracter cae en el suplemento Latin-1 (128-255).
    Ningun token legitimo cumple las tres cosas - los de verdad
    ('<|EOT|>', '<pad>', '<|Assistant|>') miden 5 caracteres o mas.

    Se expone aparte de la lógica que lo aplica para poder testear la regla
    sin cargar un tokenizer real."""
    ids = []
    for tok in added_tokens:
        content = tok.get("content", "")
        if tok.get("special", False):
            continue
        if len(content) == 1 and 128 <= ord(content) <= 255:
            ids.append(tok["id"])
    return ids


def strip_byte_fallback_tokens(tokenizer) -> int:
    """Saca del matcher los tokens que documenta byte_fallback_token_ids.

    Sin ellos el texto cae al BPE normal del vocabulario base, que si maneja
    bien los bytes multibyte de UTF-8. Devuelve cuantos se sacaron (0 si el
    tokenizer no los tiene o no es de los rapidos, en cuyo caso no hace nada).
    """
    fast = getattr(tokenizer, "_tokenizer", None)
    if fast is None:  # tokenizer lento: no expone el matcher, se deja como esta
        return 0
    try:
        import tokenizers

        data = json.loads(fast.to_str())
        added = data.get("added_tokens", [])
        malos = set(byte_fallback_token_ids(added))
        if not malos:
            return 0
        data["added_tokens"] = [t for t in added if t["id"] not in malos]
        tokenizer._tokenizer = tokenizers.Tokenizer.from_str(json.dumps(data))
        return len(malos)
    except Exception:
        # Nunca romper la carga del modelo por esto: en el peor caso quedan
        # los acentos rotos, que es mucho mejor que no poder usar la red.
        return 0


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
        # Ver strip_byte_fallback_tokens: sin esto el tokenizer de
        # deepseek-coder rompe los acentos del español antes de que el
        # modelo vea el texto.
        self.stripped_byte_tokens = strip_byte_fallback_tokens(self._tokenizer)
        self._model = AutoDistributedModelForCausalLM.from_pretrained(
            self.model_name, initial_peers=self.initial_peers
        ).eval()

    @property
    def tokenizer(self):
        """Tokenizer ya cargado (dispara la carga si hace falta).

        Lo necesita quien tenga que contar tokens o construir un streamer
        propio - por ejemplo el api-gateway, que reporta `usage` al estilo
        OpenAI y emite deltas token a token, dos cosas que `generate()` no
        expone."""
        self._load()
        return self._tokenizer

    @property
    def model(self):
        """Modelo distribuido ya cargado (dispara la carga si hace falta)."""
        self._load()
        return self._model

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
        """Pasa attention_mask y pad_token_id explicitos.

        Sin esto transformers escupe tres warnings por cada turno de chat
        ("The attention mask and the pad token id were not set...", "Setting
        `pad_token_id` to `eos_token_id`...", "The attention mask is not set and
        cannot be inferred..."), que en un REPL tapan la respuesta del modelo.
        No es solo ruido: deepseek-coder no define pad_token, asi que
        transformers lo iguala al eos_token y despues no puede distinguir
        padding real de un fin de secuencia legitimo. Pasando la mascara que el
        tokenizer ya calcula, el problema desaparece de raiz.
        """
        inputs = self._tokenizer(prompt, return_tensors="pt")
        pad_id = self._tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self._tokenizer.eos_token_id
        outputs = self._model.generate(
            inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            pad_token_id=pad_id,
            max_new_tokens=max_new_tokens,
            **gen_kwargs,
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
