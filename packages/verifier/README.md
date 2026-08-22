# verifier

Servicio de verificación por redundancia: despacha el mismo tramo de cómputo a 2-3 pipelines con nodos disjuntos y compara logits (similaridad coseno + norma relativa). Ver el diseño en [`docs/roadmap.md`](../../docs/roadmap.md#verificación-por-redundancia-fase-01).

**Pendiente — Fase 0/1.** El harness `benchmarks/correctness_check.py` (M0.4) es la semilla directa de este servicio: calibra el umbral de tolerancia antes de que exista un servicio real.
