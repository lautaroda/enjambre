import httpx

from .redundancy import VerificationVerdict


class LedgerClient:
    """Cliente HTTP minimo hacia packages/ledger-daemon."""

    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"))

    def credit(self, node_id: str, request_id: str, compute_units: float) -> dict:
        resp = self._client.post(
            "/usage",
            json={"node_id": node_id, "request_id": request_id, "compute_units": compute_units},
        )
        resp.raise_for_status()
        return resp.json()

    def credit_verdict(
        self, verdict: VerificationVerdict, request_id: str, compute_units_per_node: float
    ) -> list[dict]:
        """Acredita solo a los nodos confirmados por el verdict.

        ledger-daemon exige request_id UNICO por evento (su idempotencia es
        justamente evitar acreditar dos veces el mismo request_id). Como una
        sola request de inferencia acredita a VARIOS nodos (uno por corrida
        ganadora), namespaceamos con el node_id para no chocar entre si.
        """
        return [
            self.credit(node_id, f"{request_id}:{node_id}", compute_units_per_node)
            for node_id in sorted(verdict.credited_node_ids)
        ]
