from pydantic import BaseModel, Field


class NodeRegisterRequest(BaseModel):
    node_id: str
    display_name: str | None = None


class NodeOut(BaseModel):
    node_id: str
    display_name: str | None
    registered_at: str
    balance: float


class UsageRecordRequest(BaseModel):
    node_id: str
    request_id: str
    compute_units: float = Field(gt=0)


class UsageEventOut(BaseModel):
    id: int
    node_id: str
    request_id: str
    compute_units: float
    created_at: str


class BalanceOut(BaseModel):
    node_id: str
    balance: float
