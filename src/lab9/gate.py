"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


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
    import math
    problems: list[str] = []
    ids = [m["id"] for m in spec["metrics"]]
    rows = pr.get("rows") or []
    man, bman = pr.get("manifest", {}), base.get("manifest", {})

    # 1. NaN / inf in the headline metrics
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf compares False against every threshold)")
    # 2. row count and duplicates
    want_rows = int(man.get("items", 0)) * len(man.get("seeds") or [])
    if len(rows) != want_rows:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want_rows}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"duplicate (item, seed) rows: {dup[:3]}")
    # 3. (item, seed) set must equal the baseline's; manifest must agree with the rows
    bkeys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != bkeys:
        problems.append(f"(item, seed) set differs from baseline: {len(set(keys) - bkeys)} extra, {len(bkeys - set(keys))} missing")
    if sorted(man.get("seeds") or []) != sorted({r.get("seed") for r in rows}):
        problems.append("manifest seeds do not match the seeds present in rows")
    if man.get("items") != bman.get("items"):
        problems.append(f"manifest items {man.get('items')} != baseline {bman.get('items')}")
    # 4. crashed graders: evaluator_failures, or a graded metric whose row value is None
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][0]}")
    graded = [m for m in ids if rows and m in (base.get("rows") or [{}])[0]]
    for m in graded:
        n_none = sum(1 for r in rows if r.get(m) is None)
        if n_none:
            problems.append(f"{n_none} row(s) with {m}=None (grader crashed; silently drops out of the mean)")
    # 5. headline metrics must be what the rows say (a hand-edited summary is not evidence)
    for m in graded:
        vals = [r[m] for r in rows if r.get(m) is not None]
        if not vals or m not in (pr.get("metrics") or {}):
            continue
        calc = sum(vals) if any(x["id"] == m and x.get("kind") == "safety" for x in spec["metrics"]) else sum(vals) / len(vals)
        got = pr["metrics"][m]
        if isinstance(got, (int, float)) and math.isfinite(got) and abs(got - calc) > 1e-3:
            problems.append(f"metric {m}={got} but rows give {calc:.4f} (summary not derived from rows)")
    # 6. slice tags must not be rewritten
    btags = {r["item_id"]: sorted(r.get("slices") or []) for r in base.get("rows") or []}
    for r in rows:
        if r.get("item_id") in btags and sorted(r.get("slices") or []) != btags[r["item_id"]]:
            problems.append(f"{r['item_id']}: slice tags {sorted(r.get('slices') or [])} differ from baseline {btags[r['item_id']]}")
            break
    # 7. ratchet: same eval-set version => thresholds may only get stricter
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec.get("metrics") or [], base_spec.get("metrics") or [], "id", "metric")
        problems += _ratchet(spec.get("slices") or [], base_spec.get("slices") or [], "name", "slice")
    return problems


def _ratchet(new: list[dict], old: list[dict], key: str, what: str) -> list[str]:
    out: list[str] = []
    cur = {x[key]: x for x in new}
    for o in old:
        n = cur.get(o[key])
        tag = f"{what} {o[key]}"
        if n is None:
            out.append(f"{tag} removed from the spec")
            continue
        ot, nt = _thresholds(o), _thresholds(n)
        if o.get("blocking") and not n.get("blocking"):
            out.append(f"{tag} no longer blocking")
        if "max" in ot and ("max" not in nt or nt["max"] > ot["max"]):
            out.append(f"{tag} max raised {ot['max']} -> {nt.get('max')}")
        if "max_increase" in ot and ("max_increase" not in nt or nt["max_increase"] > ot["max_increase"]):
            out.append(f"{tag} max_increase raised {ot['max_increase']} -> {nt.get('max_increase')}")
        if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
            out.append(f"{tag} min lowered {ot['min']} -> {nt.get('min')}")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            out.append(f"{tag} dropped no_significant_drop")
    return out


def _thresholds(entry: dict) -> dict:
    """Metrics keep thresholds under "threshold"; slices keep min / no_significant_drop on the entry."""
    return {**{k: entry[k] for k in ("min", "max", "no_significant_drop", "max_increase") if k in entry},
            **(entry.get("threshold") or {})}


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        ident = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        if not a:                                   # an empty slice cannot vouch for anything
            lines.append(f"  {ident:<34} no rows in PR for this slice{'':<20} {'BLOCK' if sl.get('blocking') else 'warn'}")
            if sl.get("blocking"):
                blocked.append(ident)
            continue
        val = sum(a.values()) / len(a)
        verdict, note = "ok", ""
        if "min" in sl and val < sl["min"]:
            verdict = "fail"
        if sl.get("no_significant_drop"):
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(ident)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {ident:<34} {val:<8.4f} {json.dumps({k: sl[k] for k in ('min',) if k in sl}):<14} {note:<28} {label}")
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
