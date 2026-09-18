"""Run the pipeline on synthetic datasets and score it against the truth.

    python -m evaluation.run            # all scenarios -> evaluation/REPORT.md

The pipeline is run unchanged, exactly as on the assignment data. Only
this harness reads truth.json.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.generate import Profile, Scenario, generate
from pipeline import attribute, load, money, prepare, score
from pipeline.quality import Quality
from pipeline.run import run

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"

DIM_OF = {"short": "short_delivery", "late": "late_delivery", "reject": "quality_rejection",
          "defect": "quality_rejection", "premium": "price_premium"}

SCENARIOS = [
    Scenario(
        name="A_large_subtle", title="Larger panel, subtler offenders",
        purpose="2x the suppliers and 3x the orders of the assignment. Five offenders, each only "
                "moderately worse than normal -- a harder separation than the assignment's.",
        n_suppliers=70, n_orders=14_000, seed=11,
        bad={s: Profile(short=0.02, late=3.5, reject=0.012, defect=3.0, premium=0.02)
             for s in ["S004", "S017", "S029", "S041", "S063"]}),
    Scenario(
        name="B_failure_modes", title="Different failure modes",
        purpose="Each offender fails in exactly one way. Checks the scorecard names the right "
                "dimension, that a genuine overcharger is caught by the price test (with low price "
                "noise), and that a supplier bad on one material only is flagged on that material.",
        n_suppliers=30, n_orders=6_000, price_noise=0.06, seed=22,
        bad={"S003": Profile(premium=0.08),
             "S007": Profile(late=6.5),
             "S011": Profile(reject=0.03, defect=4.0),
             "S015": Profile(short=0.04),
             "S020": Profile(by_material={"MS Pipes": {"short": 0.05, "reject": 0.04, "defect": 6.0}})}),
    Scenario(
        name="C_sparse_messy", title="Sparse and messy",
        purpose="Small panel, only 15% of returns labelled, three tiny suppliers (one of whose few "
                "orders went badly by chance), duplicated POs, unparseable dates, a 2-material "
                "index and meaningless file names.",
        n_suppliers=25, n_orders=1_800, label_share=0.15, index_materials=2, messy=True, seed=33,
        tiny_suppliers={"S022": 3, "S023": 2, "S024": 4},
        unlucky={"S023": Profile(short=0.035, late=4.0)},
        bad={s: Profile(short=0.035, late=5.0, reject=0.025, defect=4.0, premium=0.03)
             for s in ["S002", "S009", "S016"]}),
    Scenario(
        name="D_control_no_offenders", title="Control: nobody is bad",
        purpose="Every supplier drawn from the same distribution. Any supplier flagged 'act now' "
                "here is a false alarm.",
        n_suppliers=30, n_orders=5_000, seed=44, bad={}),
]


# ------------------------------------------------------------------ scoring

def _misallocation(prob: pd.DataFrame, truth: pd.Series) -> float:
    pred = prob.groupby("supplier_id")["probability"].sum()
    act = truth.value_counts()
    sups = pred.index.union(act.index)
    return float((pred.reindex(sups, fill_value=0) - act.reindex(sups, fill_value=0)).abs().sum()
                 / 2 / len(truth))


def _ranked(prob: pd.DataFrame, truth: pd.Series) -> tuple[float, float]:
    d = prob.copy()
    d["rank"] = d.groupby("return_id")["probability"].rank(ascending=False, method="first")
    d = d.merge(truth.rename("truth"), left_on="return_id", right_index=True)
    hit = d[d["supplier_id"] == d["truth"]]
    return float((hit["rank"] == 1).sum() / len(truth)), float((hit["rank"] <= 3).sum() / len(truth))


def _ps_rule(returns: pd.DataFrame, fact: pd.DataFrame, ids: list[str]) -> pd.DataFrame:
    """The problem statement's rule: most recent batch of that material."""
    b = fact.dropna(subset=["receipt_date"])[["supplier_id", "material_id", "receipt_date"]]
    r = returns[returns["return_id"].isin(ids)][["return_id", "return_date", "material_id"]]
    m = r.merge(b, on="material_id")
    m = m[m["receipt_date"] <= m["return_date"]]
    pick = m.sort_values("receipt_date").groupby("return_id").tail(1)
    return pick[["return_id", "supplier_id"]].assign(probability=1.0)


def _auc(scores: pd.Series, positive: set[str]) -> float | None:
    pos = scores[scores.index.isin(positive)]
    neg = scores[~scores.index.isin(positive)]
    if pos.empty or neg.empty:
        return None
    # probability a random offender scores below a random normal supplier
    return float(np.mean([(p < neg).mean() + 0.5 * (p == neg).mean() for p in pos]))


def evaluate(sc: Scenario) -> dict:
    root = RUNS / sc.name
    shutil.rmtree(root, ignore_errors=True)
    truth = generate(sc, root)

    # End to end, exactly as a user would run it.
    t0 = time.perf_counter()
    summary = run(root / "raw", pdf=False, web=False, out=root / "out")
    runtime = time.perf_counter() - t0

    # Stage by stage again, to reach the full probability tables.
    q = Quality()
    ds = load.load_all(root / "raw", q)
    fact, _ = prepare.build_fact_table(ds, q)
    fact = money.attach_benchmarks(fact, q)
    att = attribute.run(ds.customer_returns, fact, q)
    orders = money.per_order_losses(fact, q)
    premium = money.price_premium(orders, q)
    alloc = money.return_losses(ds.customer_returns, att.pairs, orders, q)
    totals = money.supplier_totals(orders, alloc, premium)
    cats = money.category_totals(orders, alloc)
    sc_df = score.build(totals, orders, cats, q)
    cat_sc = score.category_scorecard(cats, sc_df)

    s = sc_df.set_index("supplier_id")
    offenders = {k for k, v in truth["bad"].items() if v["underperformer"]}
    out: dict = {"scenario": sc.name, "title": sc.title, "purpose": sc.purpose,
                 "counts": truth["counts"], "runtime_s": runtime,
                 "warnings": q.warnings, "attribution_method": att.method}

    # -- detection
    k = len(offenders)
    bottom = list(sc_df.nsmallest(max(k, 3), "score")["supplier_id"])
    out["detection"] = {
        "planted": sorted(offenders),
        "bottom_k": bottom[:k] if k else bottom,
        "precision_at_k": (len(set(bottom[:k]) & offenders) / k) if k else None,
        "offender_ranks": {o: int(s.loc[o, "rank"]) for o in sorted(offenders)},
        "auc": _auc(s["score"], offenders),
        "blind_check": summary["validation"].get("hits"),
        "gap_to_next": summary["validation"].get("gap_to_next") if k else None,
        "flagged_act": sorted(s.index[s["band"] == "act"]),
        "score_range": [float(s["score"].min()), float(s["score"].max())],
    }

    # -- right dimension for single-fault offenders
    dims = {}
    for sid, p in truth["bad"].items():
        faults = [f for f in ("short", "late", "reject", "premium")
                  if p[f] > Profile().__getattribute__(f) * 1.5 and p[f] > 0.01]
        if len(faults) == 1 and not p["by_material"]:
            expected = DIM_OF[faults[0]]
            worst = min(("short_delivery", "late_delivery", "quality_rejection", "price_premium"),
                        key=lambda d: s.loc[sid, f"score_{d}"])
            dims[sid] = {"planted": expected, "worst_dimension": worst, "ok": worst == expected}
    out["dimensions"] = dims

    # -- price test
    planted_premium = {k for k, v in truth["bad"].items() if v["premium"] > 0}
    out["price"] = {"planted_overchargers": sorted(planted_premium),
                    "flagged_significant": sorted(premium.loc[premium["premium_significant"], "supplier_id"]),
                    "premium_rs": {sid: float(s.loc[sid, "premium_loss"]) for sid in planted_premium}}

    # -- one-material offenders
    cat_hits = {}
    for sid, p in truth["bad"].items():
        for m in p["by_material"]:
            rows = cat_sc[cat_sc["supplier_id"] == sid].set_index("material_id")
            cat_hits[sid] = {"material": m, "flags_on_that_material": list(rows.loc[m, "flags"]),
                             "other_materials_flagged": int(sum(bool(f) for mat, f in rows["flags"].items()
                                                               if mat != m)),
                             "overall_rank": int(s.loc[sid, "rank"])}
    out["category"] = cat_hits

    # -- shrinkage: unlucky tiny suppliers must not be condemned
    out["unlucky"] = {sid: {"orders": int(s.loc[sid, "orders"]), "rank": int(s.loc[sid, "rank"]),
                            "band": s.loc[sid, "band"], "in_bottom_k": sid in bottom[:max(k, 3)]}
                      for sid in sc.unlucky}

    # -- attribution, on the returns whose supplier was blanked (true hold-out)
    rt = pd.Series(truth["return_truth"])
    blank = [b for b in truth["blank_ids"] if b in set(ds.customer_returns["return_id"])]
    hidden = rt.loc[blank]
    model = att.pairs[att.pairs["return_id"].isin(blank)][["return_id", "supplier_id", "probability"]]
    rule = _ps_rule(ds.customer_returns, fact, blank)
    vol = fact.groupby("supplier_id")["quantity_received"].sum()
    uniform_share = pd.DataFrame([{"return_id": r, "supplier_id": sup, "probability": v / vol.sum()}
                                  for r in blank for sup, v in vol.items()])
    m1, m3 = _ranked(model, hidden)
    r1, r3 = _ranked(rule, hidden.loc[hidden.index.isin(rule["return_id"])]) if len(rule) else (0, 0)
    out["attribution"] = {
        "hidden_returns": len(blank),
        "model": {"top1": m1, "top3": m3, "misallocation": _misallocation(model, hidden)},
        "ps_rule": {"top1": r1, "top3": r3, "misallocation": _misallocation(rule, hidden)},
        "volume_share": {"misallocation": _misallocation(uniform_share, hidden)},
        "cv_on_labelled": {k2: att.metrics.get(k2) for k2 in ("top1", "top3", "misallocation", "n")},
    }

    # -- rupees: pipeline vs an independent computation from the generator
    true_short = pd.Series(truth["short_rs"])
    got = s["short_loss"].reindex(true_short.index)
    # Duplicate POs in the messy scenario are removed at load, as they should be.
    out["rupees"] = {"short_total_true": float(true_short.sum()), "short_total_pipeline": float(got.sum()),
                     "max_supplier_abs_diff": float((got - true_short).abs().max())}
    tq = pd.Series(truth["return_qty_true"])
    aq = s["qty_returned"].reindex(tq.index.union(s.index), fill_value=0)
    tq = tq.reindex(aq.index, fill_value=0)
    out["rupees"]["return_qty_misallocated"] = float((aq - tq).abs().sum() / 2 / tq.sum())
    return out


# ------------------------------------------------------------------ report

def _pct(x: float | None, d: int = 0) -> str:
    return "—" if x is None else f"{x * 100:.{d}f}%"


def report(results: list[dict]) -> str:
    L = ["# Evaluation on synthetic datasets with a known answer", "",
         "Generated by `python -m evaluation.run`. Each dataset uses the assignment's schema; the pipeline "
         "runs unchanged and never sees the ground truth. Attribution is scored on the returns whose "
         "supplier was blanked out — a true hold-out, which the assignment data cannot offer.", ""]
    L += ["## Summary", "",
          "| Scenario | Suppliers · orders · returns | Offenders found | AUC | Hidden-return value misallocated: model vs PS rule | ₹ short-delivery vs truth | Runtime |",
          "|---|---|---|---|---|---|---|"]
    for r in results:
        d, a, c = r["detection"], r["attribution"], r["counts"]
        found = (f"{len(set(d['bottom_k']) & set(d['planted']))}/{len(d['planted'])}" if d["planted"]
                 else f"control · {len(d['flagged_act'])} flagged")
        L.append(f"| {r['title']} | {c['suppliers']} · {c['orders']:,} · {c['returns']:,} | {found} | "
                 f"{'—' if d['auc'] is None else format(d['auc'], '.3f')} | "
                 f"{_pct(a['model']['misallocation'], 1)} vs {_pct(a['ps_rule']['misallocation'], 1)} | "
                 f"diff ≤ ₹{r['rupees']['max_supplier_abs_diff']:,.0f} | {r['runtime_s']:.1f}s |")
    for r in results:
        d, a = r["detection"], r["attribution"]
        L += ["", f"## {r['title']}", "", r["purpose"], ""]
        if d["planted"]:
            L.append(f"- **Detection.** Planted {', '.join(d['planted'])}; bottom {len(d['planted'])} by score: "
                     f"{', '.join(d['bottom_k'])} (precision {_pct(d['precision_at_k'])}). Ranks "
                     f"{', '.join(f'{k} #{v}' for k, v in d['offender_ranks'].items())} of {r['counts']['suppliers']}. "
                     f"Blind check via the answer-key column: {len(d['blind_check'] or [])}/{len(d['planted'])}.")
        else:
            L.append(f"- **False alarms.** Suppliers marked 'Act now': {', '.join(d['flagged_act']) or 'none'}. "
                     f"Score range {d['score_range'][0]:.0f}–{d['score_range'][1]:.0f}.")
        for sid, v in r["dimensions"].items():
            L.append(f"- **{sid}** planted as {v['planted'].replace('_', ' ')} only → weakest dimension found: "
                     f"{v['worst_dimension'].replace('_', ' ')} {'✓' if v['ok'] else '✗'}")
        pr = r["price"]
        if pr["planted_overchargers"]:
            L.append(f"- **Price test.** Planted overchargers {pr['planted_overchargers']}; flagged significant: "
                     f"{pr['flagged_significant'] or 'none'}; premium charged: "
                     + ", ".join(f"{k} ₹{v:,.0f}" for k, v in pr["premium_rs"].items()))
        elif pr["flagged_significant"]:
            L.append(f"- **Price test.** No overcharger planted; flagged anyway: {pr['flagged_significant']}")
        for sid, v in r["category"].items():
            L.append(f"- **{sid}** bad on {v['material']} only → flags on {v['material']}: "
                     f"{', '.join(v['flags_on_that_material']) or 'none'}; other materials flagged: "
                     f"{v['other_materials_flagged']}; overall rank {v['overall_rank']}")
        for sid, v in r["unlucky"].items():
            L.append(f"- **{sid}** ({v['orders']} orders, unlucky) → rank {v['rank']}, band '{v['band']}', "
                     f"{'in' if v['in_bottom_k'] else 'not in'} the bottom group")
        L.append(f"- **Attribution** ({a['hidden_returns']} hidden returns, method: {r['attribution_method']}). "
                 f"Model top-1 {_pct(a['model']['top1'])}, top-3 {_pct(a['model']['top3'])}, value misallocated "
                 f"{_pct(a['model']['misallocation'], 1)}. PS rule: top-1 {_pct(a['ps_rule']['top1'])}, misallocated "
                 f"{_pct(a['ps_rule']['misallocation'], 1)}. Volume split: misallocated "
                 f"{_pct(a['volume_share']['misallocation'], 1)}. Cross-validation on labelled: top-3 "
                 f"{_pct(a['cv_on_labelled'].get('top3'))}.")
        ru = r["rupees"]
        L.append(f"- **Rupees.** Short delivery ₹{ru['short_total_pipeline']:,.0f} vs truth "
                 f"₹{ru['short_total_true']:,.0f} (largest per-supplier difference ₹{ru['max_supplier_abs_diff']:,.0f}); "
                 f"returned tonnage misallocated across suppliers: {_pct(ru['return_qty_misallocated'], 1)}.")
        L.append(f"- Data-quality warnings raised: {r['warnings']}. Runtime {r['runtime_s']:.1f}s.")
    return "\n".join(L) + "\n"


def main() -> int:
    only = set(sys.argv[1:])
    results = []
    for sc in SCENARIOS:
        if only and sc.name not in only:
            continue
        print(f"\n=== {sc.name}")
        results.append(evaluate(sc))
    (HERE / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    (HERE / "REPORT.md").write_text(report(results), encoding="utf-8")
    print("\n" + report(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
