"""Tests del gateway con un backend falso.

No se instala torch ni petals para correrlos: el backend se inyecta en
`app.state.backend`, igual criterio que en el client-sdk.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api_gateway.backend import GenerationResult
from api_gateway.main import app


class FakeBackend:
    def __init__(self, text="hola mundo", raise_on=None, pieces=None):
        self.text = text
        self.raise_on = raise_on
        self.pieces = pieces if pieces is not None else ["ho", "la ", "mundo"]
        self.calls = []

    def generate(self, messages, max_tokens, temperature, top_p):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }
        )
        if self.raise_on == "generate":
            raise RuntimeError("el swarm se cayo")
        return GenerationResult(
            text=self.text, prompt_tokens=7, completion_tokens=3, finish_reason="stop"
        )

    def stream(self, messages, max_tokens, temperature, top_p):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        for p in self.pieces:
            yield p
        if self.raise_on == "stream":
            raise RuntimeError("se corto a mitad")

    def count_prompt_tokens(self, messages):
        return 7


@pytest.fixture()
def fake():
    return FakeBackend()


@pytest.fixture()
def client(fake):
    with TestClient(app) as c:
        app.state.backend = fake
        yield c


def _sse_events(text):
    """Parsea el cuerpo SSE a una lista de payloads (sin el [DONE])."""
    out = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            continue
        out.append(json.loads(payload))
    return out


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "loading")


def test_list_models(client):
    r = client.get("/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 1
    assert body["data"][0]["object"] == "model"


def test_chat_completion_shape(client):
    r = client.post(
        "/v1/chat/completions",
        json={"model": "cualquiera", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "hola mundo"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}


def test_model_del_cliente_se_ignora(client, fake):
    """Varias herramientas mandan su modelo por defecto sin consultar
    /v1/models. Rechazarlas romperia la compatibilidad, que es el unico
    motivo por el que existe este gateway."""
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4-turbo", "messages": [{"role": "user", "content": "hola"}]},
    )
    assert r.status_code == 200
    assert r.json()["model"] != "gpt-4-turbo"


def test_max_tokens_se_limita(client, fake):
    r = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 999999},
    )
    assert r.status_code == 200
    assert fake.calls[0]["max_tokens"] == 512  # el tope por defecto


def test_max_tokens_minimo_uno(client, fake):
    client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 0},
    )
    assert fake.calls[0]["max_tokens"] == 1


def test_messages_vacio_da_400(client):
    r = client.post("/v1/chat/completions", json={"model": "m", "messages": []})
    assert r.status_code == 400


def test_campos_extra_no_rompen(client):
    """aider y Continue mandan siempre estos campos; aceptarlos e ignorarlos
    es mejor que devolver 422."""
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "x"}],
            "stop": ["\n\n"],
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "n": 1,
            "user": "lauta",
        },
    )
    assert r.status_code == 200


def test_error_del_swarm_da_502():
    with TestClient(app) as c:
        app.state.backend = FakeBackend(raise_on="generate")
        r = c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
        )
        assert r.status_code == 502
        assert "swarm" in r.json()["detail"]


def test_streaming_formato_openai(client):
    r = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}], "stream": True},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text.rstrip().endswith("data: [DONE]")

    events = _sse_events(r.text)
    # primer chunk: solo el role, sin contenido
    assert events[0]["choices"][0]["delta"] == {"role": "assistant", "content": None}
    assert all(e["object"] == "chat.completion.chunk" for e in events)
    # un unico id para todo el stream
    assert len({e["id"] for e in events}) == 1
    # el contenido reconstruido
    texto = "".join(
        e["choices"][0]["delta"].get("content") or ""
        for e in events
        if e["choices"][0]["delta"].get("content")
    )
    assert texto == "hola mundo"
    # ultimo chunk: delta vacio + finish_reason
    assert events[-1]["choices"][0]["finish_reason"] == "stop"
    assert events[-1]["choices"][0]["delta"].get("content") is None


def test_streaming_error_va_como_evento_no_como_500():
    """Cuando falla a mitad del stream ya se mandaron los headers 200, asi que
    el error tiene que viajar como un evento mas y el stream cerrar igual."""
    with TestClient(app) as c:
        app.state.backend = FakeBackend(raise_on="stream")
        r = c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "x"}], "stream": True},
        )
        assert r.status_code == 200
        events = _sse_events(r.text)
        assert any("error" in e for e in events)
        assert r.text.rstrip().endswith("data: [DONE]")
