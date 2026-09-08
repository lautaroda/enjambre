import numpy as np

# Calibrado con datos reales de M0.4 (3 nodos locales, bloom-560m): la corrida
# distribuida dio cos_sim=1.000012 y norma relativa=0.000167 contra la ruta local
# plana - practicamente ruido de punto flotante. Estos defaults dejan margen
# generoso para variacion real de hardware entre nodos distintos, sin dejar
# pasar una divergencia real. Ajustar con mas datos de M0.5/M0.6 (ver issue #4).
DEFAULT_COSINE_THRESHOLD = 0.999
DEFAULT_RELATIVE_NORM_THRESHOLD = 0.01


def cosine_similarity(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def relative_norm(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    norm_a = np.linalg.norm(a)
    if norm_a == 0:
        return float(np.linalg.norm(b))
    return float(np.linalg.norm(a - b) / norm_a)


def logits_match(
    a,
    b,
    cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
    relative_norm_threshold: float = DEFAULT_RELATIVE_NORM_THRESHOLD,
) -> bool:
    return (
        cosine_similarity(a, b) >= cosine_threshold
        and relative_norm(a, b) <= relative_norm_threshold
    )
