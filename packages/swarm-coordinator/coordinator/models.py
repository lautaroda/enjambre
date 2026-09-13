from pydantic import BaseModel


class MetricsReport(BaseModel):
    cpu_percent: float | None = None
    mem_used_mb: float | None = None
    mem_total_mb: float | None = None
    throughput_tokens_per_sec: float | None = None


class NodeMetricsOut(BaseModel):
    node_id: str
    cpu_percent: float | None
    mem_used_mb: float | None
    mem_total_mb: float | None
    throughput_tokens_per_sec: float | None
    updated_at: str
    online: bool
