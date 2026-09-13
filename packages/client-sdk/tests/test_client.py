import pytest

from client_sdk.client import EnjambreClient, EnjambreConnectionError


def _client(**kwargs):
    sleeps = []
    c = EnjambreClient(
        initial_peers=["/ip4/1.2.3.4/tcp/31337/p2p/fake"],
        model_name="bigscience/bloom-560m",
        sleep_fn=sleeps.append,
        **kwargs,
    )
    return c, sleeps


def test_succeeds_on_first_try_without_sleeping():
    client, sleeps = _client()
    result = client._with_retries(lambda: "ok")
    assert result == "ok"
    assert sleeps == []


def test_succeeds_after_transient_failures():
    client, sleeps = _client(max_retries=3, retry_backoff=1.0)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("nodo caido, reintentando")
        return "ok"

    result = client._with_retries(flaky)
    assert result == "ok"
    assert calls["n"] == 3
    # durmio entre el intento 1->2 y 2->3, con backoff exponencial
    assert sleeps == [1.0, 2.0]


def test_raises_enjambre_connection_error_after_exhausting_retries():
    client, sleeps = _client(max_retries=2, retry_backoff=0.5)

    def always_fails():
        raise RuntimeError("swarm inalcanzable")

    with pytest.raises(EnjambreConnectionError) as exc_info:
        client._with_retries(always_fails)

    assert "2 intentos" in str(exc_info.value)
    assert "swarm inalcanzable" in str(exc_info.value)
    assert sleeps == [0.5]  # durmio entre el intento 1 y el 2, no despues del ultimo


def test_default_max_retries_is_reasonable():
    client, _ = _client()
    assert client.max_retries >= 1


# --- tokens de respaldo a nivel byte (acentos rotos en deepseek-coder) ---

from client_sdk import byte_fallback_token_ids  # noqa: E402

# Los added_tokens reales de deepseek-coder-6.7b-instruct, leidos del
# tokenizer con `json.loads(tok._tokenizer.to_str())`.
ADDED_TOKENS_DEEPSEEK = (
    [{"id": i, "content": c, "special": False} for i, c in enumerate(
        ["õ", "÷", "Á", "ý", "À", "ÿ", "ø", "ú", "þ", "ü", "ù", "ö", "û"], start=32000)]
    + [
        {"id": 32013, "content": "<｜begin▁of▁sentence｜>", "special": True},
        {"id": 32014, "content": "<｜end▁of▁sentence｜>", "special": True},
        {"id": 32015, "content": "<｜fim▁hole｜>", "special": False},
        {"id": 32016, "content": "<｜fim▁begin｜>", "special": False},
        {"id": 32017, "content": "<｜fim▁end｜>", "special": False},
        {"id": 32018, "content": "<pad>", "special": False},
        {"id": 32019, "content": "<|User|>", "special": False},
        {"id": 32020, "content": "<|Assistant|>", "special": False},
        {"id": 32021, "content": "<|EOT|>", "special": True},
    ]
)


def test_detecta_los_13_tokens_de_byte_fallback():
    assert byte_fallback_token_ids(ADDED_TOKENS_DEEPSEEK) == list(range(32000, 32013))


def test_no_toca_los_tokens_especiales_legitimos():
    """<pad> y <|User|> tienen special=False igual que los rotos: lo que los
    distingue es el largo, no esa bandera."""
    ids = byte_fallback_token_ids(ADDED_TOKENS_DEEPSEEK)
    for legitimo in (32013, 32015, 32018, 32019, 32020, 32021):
        assert legitimo not in ids


def test_ignora_ascii_de_un_caracter():
    """Un token de un caracter ASCII no es respaldo a nivel byte."""
    assert byte_fallback_token_ids([{"id": 5, "content": "a", "special": False}]) == []


def test_ignora_multicaracter_aunque_sea_latin1():
    assert byte_fallback_token_ids([{"id": 5, "content": "úü", "special": False}]) == []


def test_lista_vacia():
    assert byte_fallback_token_ids([]) == []
