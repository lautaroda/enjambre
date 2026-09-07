import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException

from ledger_daemon import db
from ledger_daemon.models import (
    BalanceOut,
    NodeOut,
    NodeRegisterRequest,
    UsageEventOut,
    UsageRecordRequest,
)

DB_PATH = os.environ.get("LEDGER_DB_PATH", "ledger.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.get_connection(DB_PATH)
    db.init_db(conn)
    app.state.conn = conn
    yield
    conn.close()


app = FastAPI(title="Enjambre ledger-daemon", lifespan=lifespan)


def get_db() -> sqlite3.Connection:
    return app.state.conn


def _node_to_out(row: sqlite3.Row, balance: float) -> NodeOut:
    return NodeOut(
        node_id=row["node_id"],
        display_name=row["display_name"],
        registered_at=row["registered_at"],
        balance=balance,
    )


@app.post("/nodes", response_model=NodeOut)
def register_node(body: NodeRegisterRequest, conn: sqlite3.Connection = Depends(get_db)):
    row = db.upsert_node(conn, body.node_id, body.display_name)
    return _node_to_out(row, db.get_balance(conn, body.node_id))


@app.get("/nodes", response_model=list[NodeOut])
def list_nodes(conn: sqlite3.Connection = Depends(get_db)):
    rows = db.list_nodes_with_balances(conn)
    return [
        NodeOut(
            node_id=r["node_id"],
            display_name=r["display_name"],
            registered_at=r["registered_at"],
            balance=r["balance"],
        )
        for r in rows
    ]


@app.get("/nodes/{node_id}", response_model=NodeOut)
def get_node(node_id: str, conn: sqlite3.Connection = Depends(get_db)):
    row = db.get_node(conn, node_id)
    if row is None:
        raise HTTPException(status_code=404, detail="node not found")
    return _node_to_out(row, db.get_balance(conn, node_id))


@app.post("/usage", response_model=UsageEventOut)
def record_usage(body: UsageRecordRequest, conn: sqlite3.Connection = Depends(get_db)):
    row = db.record_usage(conn, body.node_id, body.request_id, body.compute_units)
    return UsageEventOut(**dict(row))


@app.get("/nodes/{node_id}/balance", response_model=BalanceOut)
def get_balance(node_id: str, conn: sqlite3.Connection = Depends(get_db)):
    if db.get_node(conn, node_id) is None:
        raise HTTPException(status_code=404, detail="node not found")
    return BalanceOut(node_id=node_id, balance=db.get_balance(conn, node_id))


@app.get("/nodes/{node_id}/usage", response_model=list[UsageEventOut])
def get_usage_history(node_id: str, conn: sqlite3.Connection = Depends(get_db)):
    if db.get_node(conn, node_id) is None:
        raise HTTPException(status_code=404, detail="node not found")
    return [UsageEventOut(**dict(r)) for r in db.get_usage_history(conn, node_id)]
