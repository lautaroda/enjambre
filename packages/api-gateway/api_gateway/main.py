"""Gateway compatible con la API de OpenAI, por delante del swarm de Enjambre.

Existe para que cualquier herramienta que ya hable el protocolo de OpenAI
(aider, Continue, Cline, Open WebUI) pueda usar la red sin escribir codigo
contra el SDK. Es tambien la pieza que le faltaba al proyecto: hasta ahora la
unica forma de consumir la red era Python.

    ENJAMBRE_PEERS=/ip4/.../p2p/Qm...,/ip4/.../p2p/Qm... \
    ENJAMBRE_MODEL=deepseek-ai/deepseek-coder-6.7b-instruct \
    uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000

    aider --openai-api-base http://localhost:8000/v1 --openai-api-key enjambre \
          --model deepseek-ai/deepseek-coder-6.7b-instruct
"""

import json
import os
from contextlib import asynccontextmanager

from anyio import to_thread
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from api_gateway.backend import PetalsBackend
from api_gateway.models import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChatMessage,
    ChunkChoice,
    DeltaMessage,
    HealthOut,
    ModelCard,
    ModelList,
    Usage,
)

MODEL = os.environ.get("ENJAMBRE_MODEL", "deepseek-ai/deepseek-coder-6.7b-instruct")
PEERS = [p for p in os.environ.get("ENJAMBRE_PEERS", "").split(",") if p.strip()]
# Tope duro de tokens por peticion. A ~0.9 tokens/seg, 512 tokens ya son casi
# 10 minutos: sin tope, una herramienta que pida 4096 bloquea la cola una hora.
MAX_TOKENS_CAP = int(os.environ.get("ENJAMBRE_MAX_TOKENS", "512"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.backend = PetalsBackend(peers=PEERS, model_name=MODEL)
    app.state.ready = False
    app.state.error = None
    yield


app = FastAPI(title="Enjambre api-gateway", lifespan=lifespan)


def _backend():
    return app.state.backend


@app.get("/health", response_model=HealthOut)
async def health():
    if app.state.error:
        return HealthOut(status="error", model=MODEL, peers=PEERS, detail=str(app.state.error))
    return HealthOut(status="ok" if app.state.ready else "loading", model=MODEL, peers=PEERS)


@app.get("/v1/models", response_model=ModelList)
async def list_models():
    return ModelList(data=[ModelCard(id=MODEL)])


@app.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages no puede estar vacio")
    # El `model` que manda el cliente se ignora a proposito: el swarm sirve un
    # solo modelo y rechazar la peticion por un nombre distinto rompe a varias
    # herramientas que mandan su default sin preguntar /v1/models primero.
    max_tokens = max(1, min(body.max_tokens, MAX_TOKENS_CAP))
    messages = [m.model_dump() for m in body.messages]
    backend = _backend()

    if body.stream:
        return StreamingResponse(
            _sse(backend, messages, max_tokens, body, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        result = await to_thread.run_sync(
            lambda: backend.generate(messages, max_tokens, body.temperature, body.top_p)
        )
    except Exception as exc:
        app.state.error = exc
        raise HTTPException(status_code=502, detail=f"el swarm no pudo responder: {exc}") from exc
    app.state.ready = True
    app.state.error = None

    return ChatCompletionResponse(
        model=MODEL,
        choices=[
            Choice(
                message=ChatMessage(role="assistant", content=result.text),
                finish_reason=result.finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.prompt_tokens + result.completion_tokens,
        ),
    )


async def _sse(backend, messages, max_tokens, body, request: Request):
    """Emite el stream en el formato SSE de OpenAI.

    Detalles del protocolo que las herramientas dan por sentados: el primer
    chunk lleva `delta.role` y ningun contenido, el ultimo lleva `delta` vacio
    con `finish_reason`, y el stream cierra con la linea literal
    `data: [DONE]`. Sin eso, varios clientes se quedan esperando.
    """
    import uuid

    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    def _first():
        return ChatCompletionChunk(
            id=chunk_id, model=MODEL, choices=[ChunkChoice(delta=DeltaMessage(role="assistant"))]
        )

    yield f"data: {_first().model_dump_json()}\n\n"

    n = 0
    try:
        iterator = backend.stream(messages, max_tokens, body.temperature, body.top_p)
        while True:
            piece = await to_thread.run_sync(lambda: next(iterator, None))
            if piece is None:
                break
            if await request.is_disconnected():
                break
            n += 1
            chunk = ChatCompletionChunk(
                id=chunk_id, model=MODEL, choices=[ChunkChoice(delta=DeltaMessage(content=piece))]
            )
            yield f"data: {chunk.model_dump_json()}\n\n"
    except Exception as exc:
        # En SSE ya se mandaron headers 200, asi que no se puede devolver un
        # 502: el error va como un evento mas, que es lo que hace OpenAI.
        yield f"data: {json.dumps({'error': {'message': str(exc), 'type': 'swarm_error'}})}\n\n"
        yield "data: [DONE]\n\n"
        return

    final = ChatCompletionChunk(
        id=chunk_id,
        model=MODEL,
        choices=[ChunkChoice(delta=DeltaMessage(), finish_reason="stop")],
    )
    yield f"data: {final.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
