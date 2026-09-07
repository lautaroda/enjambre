import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    display_name TEXT,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL REFERENCES nodes(node_id),
    request_id TEXT NOT NULL UNIQUE,
    compute_units REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_events_node_id ON usage_events(node_id);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_node(conn: sqlite3.Connection, node_id: str, display_name: str | None) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO nodes (node_id, display_name, registered_at)
        VALUES (?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            display_name = COALESCE(excluded.display_name, nodes.display_name)
        """,
        (node_id, display_name, _now()),
    )
    conn.commit()
    return get_node(conn, node_id)


def get_node(conn: sqlite3.Connection, node_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()


def record_usage(
    conn: sqlite3.Connection, node_id: str, request_id: str, compute_units: float
) -> sqlite3.Row:
    # Idempotente: si ya se acredito este request_id, devolvemos el registro
    # existente en vez de acreditar dos veces (ej. reintentos del verifier).
    existing = conn.execute(
        "SELECT * FROM usage_events WHERE request_id = ?", (request_id,)
    ).fetchone()
    if existing is not None:
        return existing

    if get_node(conn, node_id) is None:
        upsert_node(conn, node_id, display_name=None)

    cursor = conn.execute(
        """
        INSERT INTO usage_events (node_id, request_id, compute_units, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (node_id, request_id, compute_units, _now()),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM usage_events WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()


def get_balance(conn: sqlite3.Connection, node_id: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(compute_units), 0) AS balance FROM usage_events WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    return row["balance"]


def get_usage_history(conn: sqlite3.Connection, node_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM usage_events WHERE node_id = ? ORDER BY created_at DESC",
        (node_id,),
    ).fetchall()


def list_nodes_with_balances(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            n.node_id,
            n.display_name,
            n.registered_at,
            COALESCE(SUM(u.compute_units), 0) AS balance
        FROM nodes n
        LEFT JOIN usage_events u ON u.node_id = n.node_id
        GROUP BY n.node_id
        ORDER BY balance DESC
        """
    ).fetchall()
