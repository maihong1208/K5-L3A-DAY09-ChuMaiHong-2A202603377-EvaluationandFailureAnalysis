"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _is_nonfinite(val: Any) -> bool:
    return _is_number(val) and not math.isfinite(val)


def _check_ratchet_entry(
    label: str,
    base_entry: dict[str, Any],
    cur_entry: dict[str, Any],
    base_th: dict[str, Any],
    cur_th: dict[str, Any],
) -> list[str]:
    """Compare one metric or slice against base_spec; return problems if any rule loosened."""
    problems: list[str] = []
    if base_entry.get("blocking") and not cur_entry.get("blocking"):
        problems.append(f"ratchet: {label} changed blocking True -> False")
    for key, upper_bound in (("min", False), ("max", True), ("max_increase", True)):
        bval = base_th.get(key)
        if bval is None:
            continue
        cval = cur_th.get(key)
        if not (_is_number(cval) and math.isfinite(cval)) or (cval > bval if upper_bound else cval < bval):
            problems.append(f"ratchet: {label} loosened {key} ({bval} -> {cval})")
    if base_th.get("no_significant_drop") and not cur_th.get("no_significant_drop"):
        problems.append(f"ratchet: {label} dropped no_significant_drop")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    pr_manifest = pr.get("manifest") or {}

    for k, v in (pr.get("metrics") or {}).items():
        if _is_nonfinite(v):
            problems.append(f"metric {k} is non-finite ({v})")
    for r in pr_rows:
        for k, v in r.items():
            if _is_nonfinite(v):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} field {k} is non-finite ({v})")
                break

    items = pr_manifest.get("items")
    seeds = pr_manifest.get("seeds") or []
    if not isinstance(items, int) or isinstance(items, bool) or items < 0 or not seeds:
        problems.append(f"invalid manifest items={items!r} or seeds={seeds!r}")
    else:
        if len(set(seeds)) != len(seeds):
            problems.append("manifest seeds contain duplicates")
        expected_rows = items * len(seeds)
        if len(pr_rows) != expected_rows:
            problems.append(f"row count {len(pr_rows)} != manifest {items} x {len(seeds)} ({expected_rows})")

    pr_pairs = {(r.get("item_id"), r.get("seed")) for r in pr_rows}
    if len(pr_pairs) != len(pr_rows):
        problems.append(f"duplicate (item_id, seed) rows in PR ({len(pr_rows) - len(pr_pairs)} duplicate(s))")
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if pr_pairs != base_pairs:
        problems.append(
            f"(item_id, seed) set differs from baseline "
            f"(missing={len(base_pairs - pr_pairs)}, extra={len(pr_pairs - base_pairs)})"
        )

    failures = pr.get("evaluator_failures") or []
    if failures:
        problems.append(f"evaluator_failures non-empty ({len(failures)} failure(s), first: {failures[0]})")

    graded_metrics = {
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or (base_rows and m["id"] in base_rows[0])
    } | {
        s["metric"]
        for s in (spec.get("slices") or [])
        if s.get("metric") in GRADERS or (base_rows and s.get("metric") in base_rows[0])
    }
    for mid in sorted(graded_metrics):
        none_rows = [r for r in pr_rows if r.get(mid) is None]
        if none_rows:
            first = none_rows[0]
            problems.append(
                f"graded metric {mid} is None in {len(none_rows)} row(s) "
                f"(first: {first.get('item_id')}@{first.get('seed')})"
            )

    base_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    relabeled = [
        (r.get("item_id"), r.get("seed"))
        for r in pr_rows
        if (r.get("item_id"), r.get("seed")) in base_slices
        and sorted(r.get("slices") or []) != base_slices[(r.get("item_id"), r.get("seed"))]
    ]
    if relabeled:
        problems.append(f"slice tags differ from baseline on {len(relabeled)} row(s), first: {relabeled[0]}")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        spec_metrics = spec.get("metrics") or []
        cur_metrics = {m["id"]: m for m in spec_metrics}
        if len(cur_metrics) != len(spec_metrics):
            problems.append("ratchet: duplicate metric id in spec")
        for bm in base_spec.get("metrics") or []:
            mid = bm["id"]
            if mid not in cur_metrics:
                problems.append(f"ratchet: metric {mid} removed")
                continue
            cm = cur_metrics[mid]
            problems.extend(
                _check_ratchet_entry(
                    f"metric {mid}", bm, cm, bm.get("threshold") or {}, cm.get("threshold") or {}
                )
            )
        spec_slices = spec.get("slices") or []
        cur_slices = {(s["name"], s["metric"]): s for s in spec_slices}
        if len(cur_slices) != len(spec_slices):
            problems.append("ratchet: duplicate slice entry in spec")
        for bs in base_spec.get("slices") or []:
            skey = (bs["name"], bs["metric"])
            if skey not in cur_slices:
                problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} removed")
                continue
            cs = cur_slices[skey]
            problems.extend(_check_ratchet_entry(f"slice {bs['name']}/{bs['metric']}", bs, cs, bs, cs))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        slice_id = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        verdict, note = "ok", ""
        val: float | None = None
        if not a:
            verdict = "missing"
        else:
            val = sum(a.values()) / len(a)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict = "missing"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(slice_id)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        val_str = f"{val:.4f}" if val is not None else "None"
        th_str = json.dumps({k: s[k] for k in ("min", "max", "no_significant_drop") if k in s})
        lines.append(f"  {slice_id:<22} {val_str:<8} {th_str:<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
