"""Independent audit: recompute the headline figures from the raw CSVs.

    python -m evaluation.audit

Deliberately does NOT import the pipeline. Every figure is recomputed from
the six source files with plain pandas and compared with what the web app
shows (web/src/data/*.json). If the pipeline had a bug in a join, a
formula or an aggregation, the two would disagree here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "pipeline" / "data" / "raw"
WEB = ROOT / "web" / "src" / "data"

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok), detail))


def close(a, b, tol: float = 1.0) -> bool:
    """Rupees agree to within `tol` (JSON is rounded to 4 decimals)."""
    return bool(np.all(np.abs(np.asarray(a, float) - np.asarray(b, float)) <= tol))


def main() -> int:
    po = pd.read_csv(RAW / "purchase_orders.csv", parse_dates=["po_date", "delivery_promised_date"])
    gr = pd.read_csv(RAW / "goods_receipts.csv", parse_dates=["receipt_date"])
    rt = pd.read_csv(RAW / "customer_returns.csv", parse_dates=["return_date"])
    sm = pd.read_csv(RAW / "supplier_master.csv")
    web = {n: json.loads((WEB / f"{n}.json").read_text(encoding="utf-8"))
           for n in ("summary", "suppliers", "briefs")}
    s = pd.DataFrame(web["suppliers"]).set_index("supplier_id").sort_index()

    f = po.merge(gr, on="po_id", how="left", validate="one_to_one")
    check("Every purchase order has exactly one goods receipt", len(f) == len(po) and f["gr_id"].notna().all())

    # -- 1. short delivery: the assignment's formula, verbatim ----------------
    f["short"] = (f["invoice_amount_billed"] - f["quantity_received"] * f["unit_price_quoted"]).clip(lower=0)
    mine = f.groupby("supplier_id")["short"].sum().sort_index()
    check("Short delivery ₹ per supplier = Σ invoice − received × price",
          close(mine, s["short_loss"]), f"total ₹{mine.sum():,.0f} vs site ₹{s['short_loss'].sum():,.0f}")
    check("Billing is on ordered quantity (so the formula = undelivered qty × price)",
          close(f["invoice_amount_billed"], f["quantity_ordered"] * f["unit_price_quoted"], 1.0))

    # -- 2. rejected at the gate ------------------------------------------------
    rej = (f["rejection_qty"].fillna(0) * f["unit_price_quoted"]).groupby(f["supplier_id"]).sum().sort_index()
    check("Rejected-material ₹ per supplier = Σ rejected qty × price", close(rej, s["reject_loss"]))

    # -- 3. recorded customer returns ------------------------------------------
    price = f.groupby(["supplier_id", "material_id"])["unit_price_quoted"].median()
    rec = rt.dropna(subset=["supplier_id_traced"])
    val = [q * price.get((sup, m), f.loc[f["material_id"] == m, "unit_price_quoted"].median())
           for q, sup, m in zip(rec["quantity_returned"], rec["supplier_id_traced"], rec["material_id"], strict=True)]
    rec_loss = pd.Series(val, index=rec.index).groupby(rec["supplier_id_traced"]).sum()
    check("Recorded-return ₹ per supplier = Σ qty × supplier's median price",
          close(rec_loss.reindex(s.index, fill_value=0), s["return_loss_recorded"]))
    check("Every returned tonne is allocated exactly once",
          abs(s["qty_returned"].sum() - rt["quantity_returned"].sum()) < 0.01,
          f"{s['qty_returned'].sum():,.2f} MT allocated vs {rt['quantity_returned'].sum():,.2f} MT returned")
    inferred_qty = rt.loc[rt["supplier_id_traced"].isna(), "quantity_returned"].sum()
    check("Untraced-return value is fully shared out",
          s["return_loss_inferred"].sum() > 0 and abs(
              (s["qty_returned"].sum() - rec["quantity_returned"].sum()) - inferred_qty) < 0.01)

    # -- 4. totals add up ----------------------------------------------------------
    check("Short + returns = the headline figure", close(s["short_loss"] + s["return_loss"], s["rubric_core_total"]))
    check("Headline + rejected + handling + premium = total",
          close(s["rubric_core_total"] + s["reject_loss"] + s["handling_loss"] + s["premium_loss"], s["total_impact"]))
    check("Handling cost is 15% of return value", close(s["return_loss"] * 0.15, s["handling_loss"]))
    check("Site-wide totals equal the sum over suppliers",
          close(web["summary"]["totals"]["total_impact"], s["total_impact"].sum(), 5))

    # -- 5. the scorecard's raw rates ------------------------------------------------
    rate = f.groupby("supplier_id").apply(
        lambda g: (g["quantity_ordered"] - g["quantity_received"]).clip(lower=0).sum() / g["quantity_ordered"].sum() * 100,
        include_groups=False).sort_index()
    check("Short-delivery % per supplier", close(rate, s["short_delivery_pct"], 1e-3))
    late = (f["receipt_date"] - f["delivery_promised_date"]).dt.days.clip(lower=0).groupby(f["supplier_id"]).mean()
    check("Average days late per supplier", close(late.sort_index(), s["mean_days_late"], 1e-3))
    check("Years of relationship is not a column the scorecard carries", "years_of_relationship" not in s.columns)

    # -- 6. ranking and blind check ----------------------------------------------------
    flagged = set(sm.loc[sm["is_underperformer"].astype(str).str.lower() == "true", "supplier_id"])
    bottom = set(s.nsmallest(len(flagged), "score").index)
    check("Bottom suppliers by score = the data's own answer list", bottom == flagged,
          f"ours {sorted(bottom)} vs list {sorted(flagged)}")
    by_score = s.sort_values("score", ascending=False)
    check("Rank follows score: equal scores share a rank, lower scores rank lower",
          (by_score["rank"] == by_score["score"].round(6).rank(ascending=False, method="min")).all())
    check("Best supplier is ranked 1", by_score["rank"].iloc[0] == 1)

    # -- 7. the attribution baseline, rebuilt from scratch -----------------------------
    lab = rec[["return_id", "return_date", "material_id", "supplier_id_traced"]]
    b = f[["supplier_id", "material_id", "receipt_date"]]
    m = lab.merge(b, on="material_id")
    m = m[m["receipt_date"] <= m["return_date"]]
    # Everyone who delivered on the latest day before the return; ties share the credit.
    latest = m[m["receipt_date"] == m.groupby("return_id")["receipt_date"].transform("max")]
    latest = latest.drop_duplicates(["return_id", "supplier_id"])
    credit = latest.groupby("return_id").apply(
        lambda g: (g["supplier_id"] == g["supplier_id_traced"]).sum() / len(g), include_groups=False)
    ps_top1 = credit.reindex(lab["return_id"], fill_value=0).mean()
    site = web["summary"]["attribution"]["baselines"]["most_recent_batch"]["top1"]
    check("The assignment's 'most recent batch' rule, rebuilt independently, scores the same",
          abs(ps_top1 - site) < 0.01, f"independent {ps_top1:.1%} vs site {site:.1%}")

    # -- 8. briefs quote the same numbers -------------------------------------------------
    for br in web["briefs"]:
        sid = br["supplier_id"]
        check(f"Brief {sid}: short-delivery credit matches the scorecard",
              close(br["money"]["short_loss"], s.loc[sid, "short_loss"]))
        check(f"Brief {sid}: evidence POs satisfy the formula", all(
            abs(e["billed"] - e["received_value"] - e["short_loss"]) < 1 for e in br["evidence"]))

    width = max(len(n) for n, _, _ in checks)
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    failed = sum(not ok for _, ok, _ in checks)
    print(f"\n  {len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
