import httpx
import numpy as np
import pytest

from verifier.compare import cosine_similarity, logits_match, relative_norm
from verifier.ledger_client import LedgerClient
from verifier.redundancy import RedundancyVerifier, RunResult, VerificationVerdict


# --- compare.py ---


def test_identical_vectors_match():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert cosine_similarity(a, a) == pytest.approx(1.0)
    assert relative_norm(a, a) == 0.0
    assert logits_match(a, a)


def test_tiny_floating_point_noise_still_matches():
    rng = np.random.default_rng(0)
    a = rng.normal(size=128)
    b = a + rng.normal(scale=1e-5, size=128)
    assert logits_match(a, b)


def test_clearly_different_vectors_dont_match():
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 1.0, 0.0])
    assert not logits_match(a, b)


# --- redundancy.py ---


def _vec(seed: int, noise: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.normal(size=64)
    if noise:
        base = base + rng.normal(scale=noise, size=64)
    return base


def test_all_runs_agree_credits_everyone():
    base = _vec(1)
    runs = [
        RunResult(node_ids=["a"], logits=base),
        RunResult(node_ids=["b"], logits=base + np.random.default_rng(2).normal(scale=1e-6, size=64)),
        RunResult(node_ids=["c"], logits=base + np.random.default_rng(3).normal(scale=1e-6, size=64)),
    ]
    verdict = RedundancyVerifier().verify(runs)
    assert verdict.credited_node_ids == {"a", "b", "c"}
    assert verdict.suspect_node_ids == set()
    assert not verdict.inconclusive


def test_one_diverging_run_is_flagged_suspect():
    base = _vec(1)
    diverging = _vec(99)  # vector no relacionado, claramente distinto
    runs = [
        RunResult(node_ids=["a"], logits=base),
        RunResult(node_ids=["b"], logits=base + np.random.default_rng(2).normal(scale=1e-6, size=64)),
        RunResult(node_ids=["evil"], logits=diverging),
    ]
    verdict = RedundancyVerifier().verify(runs)
    assert verdict.credited_node_ids == {"a", "b"}
    assert verdict.suspect_node_ids == {"evil"}
    assert not verdict.inconclusive


def test_two_runs_that_disagree_is_inconclusive():
    runs = [
        RunResult(node_ids=["a"], logits=_vec(1)),
        RunResult(node_ids=["b"], logits=_vec(99)),
    ]
    verdict = RedundancyVerifier().verify(runs)
    assert verdict.credited_node_ids == set()
    assert verdict.suspect_node_ids == {"a", "b"}
    assert verdict.inconclusive


def test_node_shared_between_agreeing_and_suspect_run_gets_benefit_of_doubt():
    base = _vec(1)
    runs = [
        RunResult(node_ids=["shared", "a"], logits=base),
        RunResult(node_ids=["shared", "a"], logits=base + np.random.default_rng(2).normal(scale=1e-6, size=64)),
        RunResult(node_ids=["shared", "evil"], logits=_vec(99)),
    ]
    verdict = RedundancyVerifier().verify(runs)
    assert verdict.credited_node_ids == {"shared", "a"}
    assert verdict.suspect_node_ids == {"evil"}  # no "shared", pese a estar en la corrida divergente


def test_verify_requires_at_least_two_runs():
    with pytest.raises(ValueError):
        RedundancyVerifier().verify([RunResult(node_ids=["a"], logits=_vec(1))])


# --- ledger_client.py ---


def test_credit_verdict_posts_one_usage_event_per_credited_node():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    client = LedgerClient(
        base_url="http://ledger.test",
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ledger.test"),
    )
    verdict = VerificationVerdict(credited_node_ids={"a", "b"}, suspect_node_ids={"evil"})

    client.credit_verdict(verdict, request_id="req-1", compute_units_per_node=2.0)

    assert len(calls) == 2
    bodies = [c.read() for c in calls]
    assert any(b'"node_id":"a"' in b for b in bodies)
    assert any(b'"node_id":"b"' in b for b in bodies)
    assert all(b'"request_id":"req-1:' in b for b in bodies)
