from dataclasses import dataclass, field

from .compare import (
    DEFAULT_COSINE_THRESHOLD,
    DEFAULT_RELATIVE_NORM_THRESHOLD,
    logits_match,
)


@dataclass
class RunResult:
    """Una corrida end-to-end del pipeline distribuido.

    node_ids: los nodos que sirvieron esta corrida. Hoy los provee quien llama
    (ver dispatch.py) - atribuir esto automaticamente a partir de una sesion de
    petals queda para la verificacion Nivel 2 (issue #5), que ademas permite
    acotar la disputa a un solo hop en vez de a la corrida completa.
    """

    node_ids: list[str]
    logits: object


@dataclass
class VerificationVerdict:
    credited_node_ids: set[str] = field(default_factory=set)
    suspect_node_ids: set[str] = field(default_factory=set)
    inconclusive: bool = False


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[rx] = ry


class RedundancyVerifier:
    """Verificacion Nivel 1 (ver docs/roadmap.md): corre 2-3 pipelines end-to-end
    con nodos disjuntos y compara sus logits. No dice CUAL hop de una corrida
    divergente hizo trampa - solo que esa corrida completa no es de confianza.
    """

    def __init__(
        self,
        cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
        relative_norm_threshold: float = DEFAULT_RELATIVE_NORM_THRESHOLD,
    ):
        self.cosine_threshold = cosine_threshold
        self.relative_norm_threshold = relative_norm_threshold

    def verify(self, runs: list[RunResult]) -> VerificationVerdict:
        n = len(runs)
        if n < 2:
            raise ValueError("hacen falta al menos 2 corridas para verificar por redundancia")

        uf = _UnionFind(n)
        for i in range(n):
            for j in range(i + 1, n):
                if logits_match(
                    runs[i].logits, runs[j].logits, self.cosine_threshold, self.relative_norm_threshold
                ):
                    uf.union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(n):
            groups.setdefault(uf.find(i), []).append(i)
        majority = max(groups.values(), key=len)

        if len(majority) <= n / 2:
            # empate o nadie coincide con nadie - ningun resultado es confiable,
            # no se acredita ni se acusa a nadie todavia (revision manual/N+1 corrida)
            all_node_ids = {node_id for run in runs for node_id in run.node_ids}
            return VerificationVerdict(suspect_node_ids=all_node_ids, inconclusive=True)

        credited = {node_id for i in majority for node_id in runs[i].node_ids}
        suspect = {
            node_id
            for i in range(n)
            if i not in majority
            for node_id in runs[i].node_ids
        }
        # un nodo que aparece tanto en una corrida creditada como en una sospechosa
        # (comparte camino con ambos grupos) se queda con el beneficio de la duda
        suspect -= credited

        return VerificationVerdict(credited_node_ids=credited, suspect_node_ids=suspect)
