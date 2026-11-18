"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"Mismatched lengths: human={len(human)}, judge={len(judge)}")
    tp = fp = fn = tn = 0
    for h_raw, j_raw in zip(human, judge):
        h_pos = h_raw.strip().upper() == POS
        j_pos = j_raw.strip().upper() == POS
        if h_pos and j_pos:
            tp += 1
        elif not h_pos and j_pos:
            fp += 1
        elif h_pos and not j_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    """Return (precision, recall) with FAIL as positive, returning 0.0 on zero denominators."""
    cm = confusion(human, judge)
    p_denom = cm["tp"] + cm["fp"]
    r_denom = cm["tp"] + cm["fn"]
    precision = cm["tp"] / p_denom if p_denom else 0.0
    recall = cm["tp"] / r_denom if r_denom else 0.0
    return (precision, recall)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = cm["tp"] + cm["fp"] + cm["fn"] + cm["tn"]
    if n == 0:
        raise ValueError("Cannot compute Cohen's kappa on empty sequences")
    p_o = (cm["tp"] + cm["tn"]) / n
    p_h_pos = (cm["tp"] + cm["fn"]) / n
    p_j_pos = (cm["tp"] + cm["fp"]) / n
    p_h_neg = (cm["tn"] + cm["fp"]) / n
    p_j_neg = (cm["tn"] + cm["fn"]) / n
    p_e = p_h_pos * p_j_pos + p_h_neg * p_j_neg
    if abs(1.0 - p_e) <= 1e-12:
        raise ValueError("Cohen's kappa is undefined when p_e == 1.0")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if denom <= 1e-12:
        return min(1.0, max(0.0, observed_rate))
    return min(1.0, max(0.0, (observed_rate + specificity - 1.0) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy import stats as scipy_stats

    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    if a_arr.ndim != 1 or b_arr.ndim != 1 or a_arr.size == 0 or len(a_arr) != len(b_arr):
        raise ValueError(
            f"Expected non-empty 1D sequences of equal length, got shapes {a_arr.shape} and {b_arr.shape}"
        )
    if np.array_equal(a_arr, b_arr):
        return (0.0, 0.0, 0.0)
    diff = float(np.mean(a_arr - b_arr))
    res = scipy_stats.bootstrap(
        (a_arr, b_arr),
        statistic=lambda x, y, axis: np.mean(x - y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    return (diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _validate_n_c_k(n: int, c: int, k: int) -> None:
    """Validate integer trial counts for pass@k and pass^k."""
    for name, val in (("n", n), ("c", c), ("k", k)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(f"{name} must be an int, got {type(val).__name__}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if not (1 <= k <= n):
        raise ValueError(f"k must satisfy 1 <= k <= n ({n}), got {k}")
    if not (0 <= c <= n):
        raise ValueError(f"c must satisfy 0 <= c <= n ({n}), got {c}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _validate_n_c_k(n, c, k)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _validate_n_c_k(n, c, k)
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)
