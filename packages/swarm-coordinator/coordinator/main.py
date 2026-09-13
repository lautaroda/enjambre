from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from coordinator.models import MetricsReport, NodeMetricsOut

# Nodo se considera offline si no reporto en esta ventana - las metricas son
# efimeras (estado en vivo, no historico), por eso un dict en memoria alcanza
# y no hace falta una DB como en ledger-daemon.
STALE_AFTER = timedelta(seconds=30)

app = FastAPI(title="Enjambre swarm-coordinator")
_metrics_store: dict[str, dict] = {}


def _is_online(updated_at: datetime) -> bool:
    return datetime.now(timezone.utc) - updated_at < STALE_AFTER


@app.post("/nodes/{node_id}/metrics")
def report_metrics(node_id: str, body: MetricsReport):
    _metrics_store[node_id] = {**body.model_dump(), "updated_at": datetime.now(timezone.utc)}
    return {"ok": True}


@app.get("/nodes", response_model=list[NodeMetricsOut])
def list_nodes():
    return [
        NodeMetricsOut(
            node_id=node_id,
            cpu_percent=data["cpu_percent"],
            mem_used_mb=data["mem_used_mb"],
            mem_total_mb=data["mem_total_mb"],
            throughput_tokens_per_sec=data["throughput_tokens_per_sec"],
            updated_at=data["updated_at"].isoformat(),
            online=_is_online(data["updated_at"]),
        )
        for node_id, data in sorted(_metrics_store.items())
    ]


def _fmt(value, suffix=""):
    return f"{value:.1f}{suffix}" if value is not None else "—"


@app.get("/", response_class=HTMLResponse)
def dashboard():
    rows = ""
    for node in list_nodes():
        status_class = "online" if node.online else "offline"
        status_label = "en línea" if node.online else "sin reportar"
        mem = (
            f"{_fmt(node.mem_used_mb)} / {_fmt(node.mem_total_mb)} MB"
            if node.mem_used_mb is not None
            else "—"
        )
        rows += f"""
        <tr>
          <td>{node.node_id}</td>
          <td><span class="dot {status_class}"></span>{status_label}</td>
          <td>{_fmt(node.cpu_percent, "%")}</td>
          <td>{mem}</td>
          <td>{_fmt(node.throughput_tokens_per_sec, " tok/s")}</td>
          <td class="ts">{node.updated_at}</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" class="empty">Ningún nodo reportó todavía.</td></tr>'

    return f"""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Enjambre — swarm dashboard</title>
      <meta http-equiv="refresh" content="5">
      <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; background: #0f1115; color: #e6e6e6; margin: 2rem; }}
        h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; }}
        table {{ border-collapse: collapse; width: 100%; max-width: 860px; }}
        th, td {{ text-align: left; padding: 0.5rem 0.9rem; border-bottom: 1px solid #2a2d34; }}
        th {{ color: #9aa0aa; font-weight: 500; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }}
        .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.5rem; }}
        .dot.online {{ background: #3ecf8e; }}
        .dot.offline {{ background: #666; }}
        .ts {{ color: #6b7280; font-size: 0.8rem; }}
        .empty {{ color: #6b7280; text-align: center; padding: 2rem; }}
      </style>
    </head>
    <body>
      <h1>Enjambre — estado del swarm (se refresca solo cada 5s)</h1>
      <table>
        <thead>
          <tr><th>Nodo</th><th>Estado</th><th>CPU</th><th>Memoria</th><th>Throughput</th><th>Último reporte</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </body>
    </html>
    """
