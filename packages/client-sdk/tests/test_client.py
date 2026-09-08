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
