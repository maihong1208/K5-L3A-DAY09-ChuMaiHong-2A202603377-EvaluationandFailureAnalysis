"""M5-M7 self-check (Advanced/Expert). Run: python -m pytest -q -m student -o addopts= -k advanced
Public vectors only; the instructor grades with hidden ones."""
import copy
import math

import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def stats():
    from lab9 import stats

    return stats


@pytest.mark.parametrize("n,c,k,want", [(5, 5, 5, 1.0), (5, 0, 1, 0.0), (5, 2, 1, 0.4), (10, 3, 3, 1 - 35 / 120)])
def test_pass_at_k(stats, n, c, k, want):
    assert math.isclose(stats.pass_at_k(n, c, k), want, abs_tol=1e-9)


@pytest.mark.parametrize("n,c,k,want", [(5, 5, 5, 1.0), (5, 4, 5, 0.0), (5, 4, 3, 0.4), (10, 8, 2, 28 / 45)])
def test_pass_hat_k(stats, n, c, k, want):
    assert math.isclose(stats.pass_hat_k(n, c, k), want, abs_tol=1e-9)


def test_pass_k_rejects_bad_args(stats):
    for args in [(5, 6, 1), (5, 2, 0), (3, 1, 4)]:
        with pytest.raises(ValueError):
            stats.pass_at_k(*args)


def test_pass_k_rejects_all_invalid_ranges(stats):
    for bad in [(0, 0, 1), (-1, 0, 1), (5, -1, 1), (5, 6, 1), (5, 2, 0), (5, 2, -1), (3, 1, 4)]:
        with pytest.raises(ValueError):
            stats.pass_at_k(*bad)
        with pytest.raises(ValueError):
            stats.pass_hat_k(*bad)


def _report(rows, metrics, items=4, seeds=(1, 2)):
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
            "rows": rows, "metrics": metrics, "evaluator_failures": []}


ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                                               "threshold": {"min": 0.8}}]}


def test_integrity_flags_nan_and_dropped_rows():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    assert gate.integrity_check(base, base, SPEC) == []
    nan = _report(copy.deepcopy(ROWS), {"pass_rate": float("nan")})
    assert gate.integrity_check(nan, base, SPEC)
    dropped = _report(copy.deepcopy(ROWS[:-1]), {"pass_rate": 1.0})
    assert gate.integrity_check(dropped, base, SPEC)


def test_integrity_flags_loosened_spec():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    loose = copy.deepcopy(SPEC)
    loose["metrics"][0]["threshold"]["min"] = 0.5
    assert gate.integrity_check(base, base, loose, SPEC)
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_slice_check_blocks_a_slice_below_floor():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if "denial" in r["slices"] and r["seed"] == 1:
            r["pass_rate"] = False
    spec = dict(SPEC, slices=[{"name": "denial", "metric": "pass_rate", "min": 0.9, "blocking": True}])
    blocked, _ = gate.slice_check(_report(rows, {"pass_rate": 0.75}), base, spec)
    assert blocked == ["slice:denial/pass_rate"]


def test_slice_check_blocks_significant_drop_above_floor():
    from lab9 import gate

    # 6 items in denial slice with 0.80 PR vs 1.00 baseline so floor 0.75 passes but CI < 0
    rows_base = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["denial"]}
                 for i in range(6) for s in (1, 2, 3, 4, 5)]
    rows_pr = [dict(r, pass_rate=(r["seed"] != 5)) for r in rows_base]
    spec = dict(SPEC, slices=[{"name": "denial", "metric": "pass_rate", "min": 0.75,
                               "no_significant_drop": True, "blocking": True}])
    blocked, _ = gate.slice_check(_report(rows_pr, {"pass_rate": 0.8}, items=6, seeds=(1, 2, 3, 4, 5)),
                                  _report(rows_base, {"pass_rate": 1.0}, items=6, seeds=(1, 2, 3, 4, 5)), spec)
    assert blocked == ["slice:denial/pass_rate"]


def test_integrity_flags_inf_duplicate_rows_failures_none_and_relabeled_slices():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    inf_rep = _report(copy.deepcopy(ROWS), {"pass_rate": float("inf")})
    assert gate.integrity_check(inf_rep, base, SPEC)

    neg_inf_rows = copy.deepcopy(ROWS)
    neg_inf_rows[0]["cost"] = float("-inf")
    assert gate.integrity_check(_report(neg_inf_rows, {"pass_rate": 1.0}), base, SPEC)

    # Same row count (8) by dropping E-003@2 and duplicating E-000@1
    dup_rows = copy.deepcopy(ROWS[:-1]) + [copy.deepcopy(ROWS[0])]
    assert gate.integrity_check(_report(dup_rows, {"pass_rate": 1.0}), base, SPEC)

    # All (item_id, seed) keys present, plus one duplicated row (len 9)
    dup_all_present = copy.deepcopy(ROWS) + [copy.deepcopy(ROWS[0])]
    assert gate.integrity_check(_report(dup_all_present, {"pass_rate": 1.0}), base, SPEC)

    # Cherry-picked seeds (subset of seeds in both rows and manifest)
    seed1_rows = [copy.deepcopy(r) for r in ROWS if r["seed"] == 1]
    assert gate.integrity_check(_report(seed1_rows, {"pass_rate": 1.0}, items=4, seeds=(1,)), base, SPEC)

    # Evaluator failure on an otherwise green run
    fail_rep = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})
    fail_rep["evaluator_failures"] = ["E-000@1:TrialPass:boom"]
    assert gate.integrity_check(fail_rep, base, SPEC)

    # None in a graded row
    none_rows = copy.deepcopy(ROWS)
    none_rows[0]["pass_rate"] = None
    assert gate.integrity_check(_report(none_rows, {"pass_rate": 1.0}), base, SPEC)

    # Slice tag relabeled away from baseline
    relabel_rows = copy.deepcopy(ROWS)
    relabel_rows[0]["slices"] = []
    assert gate.integrity_check(_report(relabel_rows, {"pass_rate": 1.0}), base, SPEC)


def test_integrity_ratchet_checks_slices_and_blocking():
    from lab9 import gate

    rows = [dict(r, approval_bypass=False) for r in ROWS]
    base = _report(copy.deepcopy(rows), {"pass_rate": 1.0, "approval_bypass": 0, "cost_per_success": 50.0})
    strict = {
        "eval_set_version": "v2",
        "metrics": [
            {"id": "pass_rate", "kind": "capability", "blocking": True,
             "threshold": {"min": 0.8, "no_significant_drop": True}},
            {"id": "approval_bypass", "kind": "safety", "blocking": True, "threshold": {"max": 0}},
            {"id": "cost_per_success", "kind": "system", "blocking": False, "threshold": {"max_increase": 0.1}},
        ],
        "slices": [
            {"name": "denial", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True}
        ],
    }
    assert gate.integrity_check(base, base, strict, strict) == []

    for mutate in [
        lambda s: s.__setitem__("slices", []),
        lambda s: s["slices"][0].pop("no_significant_drop"),
        lambda s: s["slices"][0].__setitem__("min", 0.85),
        lambda s: s["slices"][0].pop("min"),
        lambda s: s["slices"][0].__setitem__("blocking", False),
        lambda s: s["metrics"][0].__setitem__("blocking", False),
        lambda s: s["metrics"][0]["threshold"].pop("min"),
        lambda s: s["metrics"][0]["threshold"].pop("no_significant_drop"),
        lambda s: s["metrics"][1]["threshold"].__setitem__("max", 1),
        lambda s: s["metrics"][1]["threshold"].pop("max"),
        lambda s: s["metrics"][2]["threshold"].__setitem__("max_increase", 0.2),
        lambda s: s["metrics"][2]["threshold"].pop("max_increase"),
        lambda s: s.__setitem__("metrics", []),
    ]:
        cand = copy.deepcopy(strict)
        mutate(cand)
        assert gate.integrity_check(base, base, cand, strict)

    # Tightening on the same eval_set_version is allowed
    tighter = copy.deepcopy(strict)
    tighter["metrics"][0]["threshold"]["min"] = 0.85
    tighter["metrics"][2]["threshold"]["max_increase"] = 0.05
    tighter["metrics"][2]["blocking"] = True
    tighter["slices"][0]["min"] = 0.95
    assert gate.integrity_check(base, base, tighter, strict) == []

    # Loosening thresholds across DIFFERENT eval_set_version (v1 -> v2) is allowed
    strict_v1 = copy.deepcopy(strict)
    strict_v1["eval_set_version"] = "v1"
    looser_v2 = copy.deepcopy(strict)
    looser_v2["eval_set_version"] = "v2"
    looser_v2["metrics"][0]["threshold"]["min"] = 0.5
    looser_v2["metrics"][0]["blocking"] = False
    looser_v2["slices"] = []
    assert gate.integrity_check(base, base, looser_v2, strict_v1) == []
