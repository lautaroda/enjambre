"""Esquemas de la API de OpenAI (el subconjunto que implementamos).

Se respetan los nombres de campo exactos de OpenAI aunque no sean los que
elegiriamos: el objetivo del gateway es que herramientas existentes (aider,
Continue, Open WebUI) funcionen sin parches, y esas herramientas parsean
estos nombres literalmente.
"""

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    # OpenAI no pone tope por defecto. Aca SI hay que ponerlo: el swarm genera
    # ~0.9 tokens/seg en CPU, asi que una peticion sin limite puede tardar
    # horas y bloquear la cola entera (ver el lock en backend.py).
    max_tokens: int = 256
    temperature: float = 0.4
    top_p: float = 0.9
    stream: bool = False
    # Se aceptan y se ignoran: varias herramientas los mandan siempre, y
    # rechazar la peticion por un campo que no usamos seria peor que ignorarlo.
    stop: Optional[list[str]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    n: Optional[int] = None
    user: Optional[str] = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Literal["stop", "length"]


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: Usage


class DeltaMessage(BaseModel):
    role: Optional[Literal["assistant"]] = None
    content: Optional[str] = None


class ChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[Literal["stop", "length"]] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChunkChoice]


class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "enjambre"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]


class HealthOut(BaseModel):
    status: Literal["ok", "loading", "error"]
    model: str
    peers: list[str]
    detail: Optional[str] = None
