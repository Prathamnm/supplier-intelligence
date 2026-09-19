"""One command, raw CSVs in, every deliverable out.

    python -m pipeline.run                # full run, PDFs if a browser is found
    python -m pipeline.run --no-pdf       # HTML briefs only
    python -m pipeline.run --raw path/    # a different dataset

Stages:
    01 load & validate      load.py      seals the answer key
    02 map & join           prepare.py   one row per purchase order
    03 attribution          attribute.py the model -- fills untraced returns
    04 rupees               money.py     the rubric formula, verbatim
    05 score                score.py     4 dimensions, shrinkage, 0-100
    06 validate             score.py     weight stability + blind check
    07 briefs               brief.py     A4 negotiation briefs, HTML + PDF
    08 export               export.py    JSON for the web app, CSV for humans
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from pipeline import attribute, brief, config, export, load, money, prepare, report, schema, score
from pipeline.attribute import FEATURE_LABELS
from pipeline.quality import PipelineError, Quality
from pipeline.score import DIMENSION_LABELS, METRIC


class Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.marks: dict[str, float] = {}
        self._last = self.t0

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.marks[name] = round(now - self._last, 3)
        self._last = now
        print(f"  {name:<22} {self.marks[name]:6.2f}s")

    @property
    def total(self) -> float:
        return round(time.perf_counter() - self.t0, 3)


def run(raw: Path | None = None, pdf: bool = True, web: bool = True,
        out: Path | None = None) -> dict:
    out = out or config.OUT
    q = Quality()
    t = Timer()
    print("Supplier intelligence pipeline")

    ds = load.load_all(raw, q)
    t.mark("01 load")

    fact, mapping = prepare.build_fact_table(ds, q)
    t.mark("02 prepare")

    fact = money.attach_benchmarks(fact, q)
    idx_ctx = money.index_context(fact, ds.market_price_index, q)
    att = attribute.run(ds.customer_returns, fact, q)
    t.mark("03 attribute")

    orders = money.per_order_losses(fact, q)
    premium = money.price_premium(orders, q)
    alloc = money.return_losses(ds.customer_returns, att.pairs, orders, q)
    totals = money.supplier_totals(orders, alloc, premium)
    cats = money.category_totals(orders, alloc)
    years = money.year_totals(orders, alloc)
    t.mark("04 money")

    sc = score.build(totals, orders, cats, q)
    cat_sc = score.category_scorecard(cats, sc)
    t.mark("05 score")

    stab = score.stability(sc)
    # Only now, with the ranking frozen, is the answer key opened.
    validation = score.blind_validation(sc, ds._sealed_labels, q)
    replacements = score.recommend(sc, cat_sc)
    t.mark("06 validate")

    worst = list(sc.nsmallest(config.TOP_N_BRIEFS, "score")["supplier_id"])
    briefs = [brief.compose(sid, sc, cat_sc, orders, alloc, att.per_return,
                            ds.supplier_master, idx_ctx, replacements) for sid in worst]

    out_briefs = config.WEB_BRIEFS if web else out / "briefs"
    company = config.COMPANY if raw is None or Path(raw).resolve() == config.RAW.resolve() else None
    files = brief.render(briefs, out_briefs, pdf=pdf, company=company)
    for b in briefs:
        b["files"] = files.get(b["supplier_id"], {})
    t.mark("07 briefs")

    summary = _summary(ds, fact, sc, totals, att, stab, validation, replacements,
                       idx_ctx, premium, q, t)
    payload = {
        "summary.json": summary,
        "suppliers.json": _suppliers(sc),
        "supplier_details.json": _details(cat_sc, years),
        "returns.json": _returns(att),
        "briefs.json": briefs,
        "quality.json": q.to_dict(),
        # The file rules, bundled into the site so the Upload page can check
        # files instantly, before the API has even woken up.
        "schema.json": {"files": {n: sorted(c) for n, c in schema.SIGNATURES.items()}},
    }
    targets = [out / "data"] + ([config.WEB_DATA] if web else [])
    for target in targets:
        for name, obj in payload.items():
            export.write_json(target / name, obj)
    export.write_csv(out / "scorecard.csv", sc)
    export.write_csv(out / "scorecard_by_material.csv", cat_sc)
    export.write_csv(out / "returns_attributed.csv", att.per_return)
    export.write_csv(out / "orders_with_losses.csv", orders)
    doc = report.render(export._clean(summary), payload["suppliers.json"], briefs,
                        payload["quality.json"], config.WEB / "public" if web else out, pdf=pdf)
    t.mark("08 export")

    print(f"\n  done in {t.total:.2f}s · {len(sc)} suppliers · {len(orders):,} orders · "
          f"{q.warnings} warnings")
    print(f"  bottom {config.TOP_N_REPLACE}: {', '.join(validation.get('our_bottom', worst[:3]))}"
          + (f" · blind check {len(validation['hits'])}/{len(validation['flagged'])}"
             if validation.get("available") else ""))
    print(f"  attribution: top-3 {att.metrics.get('top3', 0):.1%}, "
          f"misallocation {att.metrics.get('misallocation', 0):.1%}")
    print(f"  approach document: {doc.get('pdf', doc['html'])}")
    printed = (f"{k} ({v.get('pages', '?')}p)" if "pdf" in v else k for k, v in files.items())
    print(f"  briefs: {', '.join(printed)}")
    return summary


# ----------------------------------------------------------------- shapes

def _summary(ds, fact, sc, totals, att, stab, validation, replacements, idx_ctx,
             premium, q, t) -> dict:
    span_days = (fact["po_date"].max() - fact["po_date"].min()).days
    years = max(span_days / 365.25, 1)
    bottom = sc.nsmallest(config.TOP_N_REPLACE, "score")
    rest = sc[~sc["supplier_id"].isin(bottom["supplier_id"])]
    months = fact["month"].nunique()
    annual_spend = fact["invoice_amount_billed"].sum() / years
    excess = (bottom["total_impact"].sum()
              - (rest["total_impact"].sum() / rest["spend"].sum()) * bottom["spend"].sum())
    excess_rate = excess / years / annual_spend

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "runtime_s": t.total,
        "stage_times": t.marks,
        "period": {"start": fact["po_date"].min(), "end": fact["po_date"].max(),
                   "years": round(years, 2), "months": int(months)},
        "counts": {
            "suppliers": int(len(sc)),
            "orders": int(len(fact)),
            "materials": int(fact["material_id"].nunique()),
            "returns": q.counts.get("returns_total"),
            "returns_labelled": q.counts.get("returns_labelled"),
            "returns_blank": q.counts.get("returns_blank"),
            "spend": float(fact["invoice_amount_billed"].sum()),
            "monthly_spend": float(fact["invoice_amount_billed"].sum() / max(months, 1)),
        },
        "totals": {
            "short_loss": float(totals["short_loss"].sum()),
            "return_loss": float(totals["return_loss"].sum()),
            "return_loss_inferred": float(totals["return_loss_inferred"].sum()),
            "rubric_core_total": float(totals["rubric_core_total"].sum()),
            "reject_loss": float(totals["reject_loss"].sum()),
            "handling_loss": float(totals["handling_loss"].sum()),
            "premium_loss": float(totals["premium_loss"].sum()),
            "total_impact": float(totals["total_impact"].sum()),
        },
        "bottom": {
            "suppliers": list(bottom["supplier_id"]),
            "rubric_core_total": float(bottom["rubric_core_total"].sum()),
            "total_impact": float(bottom["total_impact"].sum()),
            "per_year": float(bottom["total_impact"].sum() / years),
            # What the bottom three cost beyond what the rest of the panel
            # would have leaked on the same spend.
            "excess_over_panel": float(excess),
            "excess_per_year": float(excess / years),
            "excess_rate_of_spend": float(excess_rate),
            "scaled_to_ps_low": float(excess_rate * config.PS_MONTHLY_PROCUREMENT_LOW * 12),
            "scaled_to_ps_high": float(excess_rate * config.PS_MONTHLY_PROCUREMENT_HIGH * 12),
            "share_of_spend": float(bottom["spend"].sum() / sc["spend"].sum()),
            "share_of_impact": float(bottom["total_impact"].sum() / sc["total_impact"].sum()),
            "ps_estimate_low": config.PS_ANNUAL_LOSS_LOW,
            "ps_estimate_high": config.PS_ANNUAL_LOSS_HIGH,
        },
        "weights": config.WEIGHTS,
        "dimensions": [{"key": d, "label": DIMENSION_LABELS[d], "metric": METRIC[d],
                        "weight": config.WEIGHTS[d]} for d in DIMENSION_LABELS],
        "stability": stab,
        "validation": validation,
        "replacements": replacements,
        "attribution": {
            "method": att.method,
            "metrics": att.metrics,
            "baselines": att.baselines,
            "coefficients": att.coefficients,
            "feature_labels": FEATURE_LABELS,
            "calibration": att.calibration,
        },
        "premium": {
            "significant": list(premium.loc[premium["premium_significant"], "supplier_id"]),
            "fdr": config.PREMIUM_FDR,
        },
        "index_context": export.records(idx_ctx) if len(idx_ctx) else [],
        "config": {
            "shrinkage_k": config.SHRINKAGE_K,
            "handling_factor": config.RETURN_HANDLING_FACTOR,
            "peer_period": config.PEER_PERIOD,
            "material_window_days": config.MATERIAL_SHARE_WINDOW_DAYS,
            "recency_halflife_days": config.RECENCY_HALFLIFE_DAYS,
            "cv_folds": config.CV_FOLDS,
        },
        "quality": {"warnings": q.warnings, "errors": q.errors},
    }


SUPPLIER_COLS = [
    "supplier_id", "supplier_name", "score", "rank", "risk_rank", "band", "drivers",
    "low_confidence", "orders", "spend", "qty_ordered", "qty_received", "qty_short",
    "qty_rejected", "qty_returned",
    "short_delivery_pct", "late_orders_pct", "mean_days_late", "mean_days_late_when_late",
    "max_days_late", "receiving_rejection_pct", "customer_return_pct",
    "quality_rejection_pct", "price_premium_pct", "premium_ci_low", "premium_ci_high",
    "premium_q", "premium_significant",
    "score_short_delivery", "score_late_delivery", "score_quality_rejection",
    "score_price_premium",
    "short_loss", "return_loss", "return_loss_recorded", "return_loss_inferred",
    "returns_recorded", "returns_inferred", "reject_loss", "handling_loss",
    "premium_loss", "premium_net_rs", "rubric_core_total", "additional_total",
    "total_impact", "impact_pct_of_spend", "arora_paid_days_late",
]

CATEGORY_COLS = [
    "supplier_id", "material_id", "orders", "spend", "short_delivery_pct",
    "late_orders_pct", "mean_days_late", "quality_rejection_pct", "price_premium_pct",
    "median_price", "benchmark", "short_loss", "reject_loss", "return_loss",
    "leakage", "score", "flags", "low_confidence",
]


def _suppliers(sc) -> list[dict]:
    return export.records(sc, [c for c in SUPPLIER_COLS if c in sc.columns])


def _details(cat_sc, years) -> dict[str, dict]:
    """Per-supplier drill-down, kept apart so the overview stays light."""
    by_year = {sid: export.records(g.sort_values("year")) for sid, g in years.groupby("supplier_id")}
    return {sid: {"categories": export.records(g.sort_values("spend", ascending=False), CATEGORY_COLS),
                  "years": by_year.get(sid, [])}
            for sid, g in cat_sc.groupby("supplier_id")}


def _returns(att) -> list[dict]:
    cols = ["return_id", "return_date", "client_id", "material_id", "quantity_returned",
            "reason", "source", "supplier_attributed", "confidence", "top3", "model_agrees"]
    pr = att.per_return
    return export.records(pr, [c for c in cols if c in pr.columns])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=None, help="folder of source CSVs")
    ap.add_argument("--no-pdf", action="store_true", help="skip PDF printing")
    ap.add_argument("--no-web", action="store_true", help="do not write into web/")
    args = ap.parse_args(argv)
    try:
        run(args.raw, pdf=not args.no_pdf, web=not args.no_web)
    except PipelineError as e:
        print(f"\n  STOPPED: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
