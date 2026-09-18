"""Stage 08 -- the negotiation brief Kiran carries into the meeting (D4).

Built in two steps so the same content feeds both the printable page and
the web app:

1. `compose()` turns the analysis into a plain dict: the rupee figures
   with their arithmetic, numbered asks, the evidence purchase orders,
   and the counter-arguments to expect.
2. `render()` fills an A4 HTML template and, when a Chromium-based
   browser is available, prints it to PDF.

Rules the asks follow:
- Every ask cites a number the supplier can check against their own
  paperwork (a PO, a GRN, a return note).
- Only *recorded* returns are claimed as a credit. Inferred returns are
  shown as an estimate, never demanded -- a supplier can dispute an
  inference, and one disputed figure undermines the rest.
- A price ask is made only when the supplier's premium across all their
  orders clears a minimum, and it is framed as a price-match clause
  quoting the panel median -- never a refund, unless the premium is
  statistically established.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline import config
from pipeline.score import DIMENSION_LABELS

STAGE = "08-brief"


# ---------------------------------------------------------------- format

def inr(x: float | None, decimals: int = 0) -> str:
    """Indian digit grouping: 12,34,56,789."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "-"
    neg = x < 0
    x = abs(round(float(x), decimals))
    whole, _, frac = f"{x:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    s = whole + (f".{frac}" if frac else "")
    return ("-" if neg else "") + "₹" + s


def lakh(x: float) -> str:
    """Compact form for headlines: ₹8.42L, ₹1.24Cr."""
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    return f"₹{x / 1e5:.2f} L"


# --------------------------------------------------------------- compose

def _late_penalty(g: pd.DataFrame) -> float:
    days = g["days_late_delivery"].clip(lower=0).fillna(0)
    rate = np.minimum(days * config.LATE_PENALTY_PER_DAY, config.LATE_PENALTY_CAP)
    return float((rate * g["invoice_amount_billed"]).sum())


def compose(sid: str, s: pd.DataFrame, cats: pd.DataFrame, orders: pd.DataFrame,
            alloc: pd.DataFrame, per_return: pd.DataFrame, master: pd.DataFrame,
            index_ctx: pd.DataFrame, replacements: list[dict]) -> dict:
    row = s.set_index("supplier_id").loc[sid]
    panel = s[s["supplier_id"] != sid]
    mine = orders[orders["supplier_id"] == sid]
    cat = cats[cats["supplier_id"] == sid].sort_values("leakage", ascending=False)
    info = master.set_index("supplier_id").loc[sid] if sid in set(master["supplier_id"]) else {}

    period = f"{orders['po_date'].min():%b %Y} – {orders['po_date'].max():%b %Y}"
    billed = float(mine["invoice_amount_billed"].sum())
    received_value = float((mine["quantity_received"] * mine["unit_price_quoted"]).sum())

    # -- the money, with arithmetic ------------------------------------
    rec = alloc[(alloc["supplier_id"] == sid) & (alloc["source"] == "recorded")]
    inf = alloc[(alloc["supplier_id"] == sid) & (alloc["source"] == "inferred")]
    inferred_confident = per_return[(per_return["source"] == "inferred")
                                    & (per_return["supplier_attributed"] == sid)]
    money = {
        "billed": billed,
        "received_value": received_value,
        "short_loss": float(row["short_loss"]),
        "short_orders": int(row["short_orders"]),
        "orders": int(row["orders"]),
        "qty_short": float(row["qty_short"]),
        "qty_ordered": float(row["qty_ordered"]),
        "short_pct": float(row["short_delivery_pct"]),
        "returns_recorded_n": int(len(rec)),
        "returns_recorded_qty": float(rec["return_qty"].sum()),
        "returns_recorded_loss": float(rec["return_loss"].sum()),
        "returns_inferred_expected": float(inf["probability"].sum()),
        "returns_inferred_top_pick": int(len(inferred_confident)),
        "returns_inferred_qty": float(inf["return_qty"].sum()),
        "returns_inferred_loss": float(inf["return_loss"].sum()),
        "return_loss": float(row["return_loss"]),
        "rubric_core_total": float(row["rubric_core_total"]),
        "reject_loss": float(row["reject_loss"]),
        "qty_rejected": float(row["qty_rejected"]),
        "handling_loss": float(row["handling_loss"]),
        "handling_pct": config.RETURN_HANDLING_FACTOR * 100,
        "premium_loss": float(row["premium_loss"]),
        "premium_significant": bool(row.get("premium_significant", False)),
        "total_impact": float(row["total_impact"]),
        "per_year": float(row["total_impact"]) / max(
            (orders["po_date"].max() - orders["po_date"].min()).days / 365.25, 1),
    }

    # -- asks -----------------------------------------------------------
    asks = []
    panel_short = float((panel["qty_short"].sum() / panel["qty_ordered"].sum()) * 100)
    asks.append({
        "topic": "Short delivery",
        "ask": f"Issue a credit note of {inr(money['short_loss'])} for material billed but "
               f"not delivered, and invoice on GRN-received quantity from the next order.",
        "evidence": f"{money['short_orders']} of {money['orders']} orders arrived short — "
                    f"{money['qty_short']:,.1f} MT of {money['qty_ordered']:,.1f} MT ordered "
                    f"({money['short_pct']:.1f}% vs {panel_short:.1f}% for the rest of our panel).",
    })

    quality_claim = money["reject_loss"] + money["returns_recorded_loss"]
    if quality_claim > 0:
        # The material with the most rupees actually failed -- measured
        # rejections first, recorded returns as the tie-break.
        worst_q = (cat.assign(_q=cat["reject_loss"] + cat["return_loss"])
                   .sort_values("_q", ascending=False).iloc[0])
        what = ("material rejected at our gate and returned by our customers"
                if money["reject_loss"] > 0 else "material returned by our customers")
        gate = (f"{money['qty_rejected']:,.1f} MT rejected at inspection "
                f"({inr(money['reject_loss'])}); " if money["reject_loss"] > 0 else "")
        asks.append({
            "topic": "Quality",
            "ask": f"Credit {inr(quality_claim)} for {what}, and send a mill test "
                   f"certificate with every {worst_q['material_id']} dispatch.",
            "evidence": f"{gate}{money['returns_recorded_n']} customer returns traced to you on "
                        f"our records ({inr(money['returns_recorded_loss'])}). A further "
                        f"~{money['returns_inferred_expected']:.0f} untraced returns are most likely "
                        f"yours (est. {inr(money['returns_inferred_loss'])}) — not claimed.",
        })

    panel_days = float(panel["mean_days_late"].mean())
    if row["mean_days_late"] > panel_days:
        late = mine[mine["days_late_delivery"] > 0]
        asks.append({
            "topic": "Delivery",
            "ask": f"Agree a late-delivery clause of {config.LATE_PENALTY_PER_DAY:.1%} of order "
                   f"value per day, capped at {config.LATE_PENALTY_CAP:.0%}. Applied to the last "
                   f"three years it would have been worth {inr(_late_penalty(late))}.",
            "evidence": f"Late on {len(late)} of {money['orders']} orders, by "
                        f"{row['mean_days_late_when_late']:.1f} days on average (up to "
                        f"{row['max_days_late']:.0f}). Panel average: {panel_days:.1f} days.",
        })

    # Price: judged on the supplier's premium across *all* their orders.
    # Per-material medians over a handful of orders swing by tens of
    # percent on this data's price noise, so a per-material "cut by X%"
    # would be indefensible. The ask is a price-match clause instead,
    # quoting the panel median on their largest material.
    premium = float(row["price_premium_pct"])
    if premium >= config.MIN_PRICE_ASK_PCT:
        top = cat.dropna(subset=["benchmark"]).sort_values("spend", ascending=False)
        if len(top):
            p = top.iloc[0]
            idx = (index_ctx[(index_ctx["material"] == p["material_id"]) & index_ctx["usable"]]
                   if len(index_ctx) else pd.DataFrame())
            idx_note = (f" Published index for {p['material_id']} ({idx.iloc[0]['index_month']}): "
                        f"{inr(idx.iloc[0]['index_price'])}/MT." if len(idx) else "")
            established = ("statistically established" if row.get("premium_significant")
                           else "within price noise, so asked as a clause, not a refund")
            asks.append({
                "topic": "Price",
                "ask": f"Agree to quote at or below our panel median for each material — "
                       f"for {p['material_id']}, your largest line, that is "
                       f"{inr(p['benchmark'])}/MT.",
                "evidence": f"Across {money['orders']} orders you averaged {premium:+.1f}% above "
                            f"other suppliers for the same material and quarter "
                            f"({established}).{idx_note}",
            })

    # -- where it goes wrong, by material --------------------------------
    materials = [{
        "material": r["material_id"],
        "orders": int(r["orders"]),
        "spend": float(r["spend"]),
        "short_pct": float(r["short_delivery_pct"]),
        "days_late": float(r["mean_days_late"]),
        "quality_pct": float(r["quality_rejection_pct"]),
        "leakage": float(r["leakage"]),
        "flags": [DIMENSION_LABELS[f] for f in r["flags"]],
    } for _, r in cat.head(6).iterrows()]

    # -- evidence POs ------------------------------------------------------
    ev = mine.assign(claim=mine["short_loss"] + mine["reject_loss"]) \
        .sort_values("claim", ascending=False).head(config.EVIDENCE_POS_PER_BRIEF)
    evidence = [{
        "po_id": r["po_id"], "gr_id": r.get("gr_id", ""),
        "date": f"{r['po_date']:%d %b %Y}", "material": r["material_id"],
        "ordered": float(r["quantity_ordered"]), "received": float(r["quantity_received"]),
        "rejected": float(r["rejection_qty"] or 0), "price": float(r["unit_price_quoted"]),
        "billed": float(r["invoice_amount_billed"]),
        "received_value": float(r["quantity_received"] * r["unit_price_quoted"]),
        "short_loss": float(r["short_loss"]), "reject_loss": float(r["reject_loss"]),
        "days_late": int(r["days_late_delivery"]) if pd.notna(r["days_late_delivery"]) else None,
    } for _, r in ev.iterrows()]

    # -- what they will say back -----------------------------------------
    pushback = []
    if row.get("arora_paid_days_late", 0) and row["arora_paid_days_late"] > 1:
        pushback.append(f"We paid their invoices {row['arora_paid_days_late']:.0f} days late on "
                        f"average. Expect this to be raised — offer on-time payment in "
                        f"exchange for the asks above.")
    pushback.append("Every figure is from our PO, GRN and invoice records; the PO numbers "
                    "on page 2 let them check any line against their own copies.")
    alt = next((r for r in replacements if r["supplier_id"] == sid), None)
    if alt and alt["materials"] and alt["materials"][0]["alternatives"]:
        m0 = alt["materials"][0]
        names = ", ".join(a["supplier_name"] for a in m0["alternatives"])
        pushback.append(f"Walk-away position: {names} already supply {m0['material']} to us "
                        f"with a far better record.")

    return {
        "supplier_id": sid,
        "supplier_name": row["supplier_name"],
        "city": info.get("city", "") if len(info) else "",
        "contact": info.get("contact_name", "") if len(info) else "",
        "years": int(info["years_of_relationship"]) if len(info) and pd.notna(
            info.get("years_of_relationship")) else None,
        "credit_days": int(info["credit_days_agreed"]) if len(info) and pd.notna(
            info.get("credit_days_agreed")) else None,
        "period": period,
        "generated": f"{date.today():%d %b %Y}",
        "score": float(row["score"]),
        "rank": int(row["rank"]),
        "n_suppliers": int(len(s)),
        "drivers": [DIMENSION_LABELS[d] for d in row["drivers"]],
        "money": money,
        "asks": asks,
        "materials": materials,
        "evidence": evidence,
        "pushback": pushback,
        "replace": alt is not None,
    }


# ---------------------------------------------------------------- render

def _browser() -> str | None:
    candidates = [
        os.environ.get("BROWSER_PDF", ""),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for name in ("chromium", "chromium-browser", "google-chrome", "msedge"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    return next((c for c in candidates if c and Path(c).exists()), None)


def _to_pdf(html: Path, pdf: Path, browser: str) -> bool:
    # A throwaway profile per print: a running browser holding the default
    # profile would otherwise swallow the headless request.
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        try:
            subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-first-run",
                 "--no-pdf-header-footer", f"--user-data-dir={profile}",
                 f"--print-to-pdf={pdf}", html.resolve().as_uri()],
                check=True, capture_output=True, timeout=90)
        except (subprocess.SubprocessError, OSError):
            return False
        # Edge's launcher can exit before its renderer has written the
        # file. Wait until it exists and its size stops changing.
        deadline, last = time.monotonic() + 45, -1
        while time.monotonic() < deadline:
            size = pdf.stat().st_size if pdf.exists() else -1
            if size > 0 and size == last:
                return True
            last = size
            time.sleep(0.4)
    return False


def render(briefs: list[dict], out_dir: Path, pdf: bool = True) -> dict[str, dict]:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters["inr"] = inr
    env.filters["lakh"] = lakh
    template = env.get_template("brief.html.j2")

    out_dir.mkdir(parents=True, exist_ok=True)
    browser = _browser() if pdf else None
    files: dict[str, dict] = {}
    for b in briefs:
        html_path = out_dir / f"{b['supplier_id']}.html"
        html_path.write_text(template.render(b=b), encoding="utf-8")
        entry = {"html": html_path.name}
        if browser:
            pdf_path = out_dir / f"{b['supplier_id']}.pdf"
            if _to_pdf(html_path, pdf_path, browser):
                entry["pdf"] = pdf_path.name
                entry["pages"] = len(re.findall(rb"/Type\s*/Page(?!s)", pdf_path.read_bytes()))
        files[b["supplier_id"]] = entry
    return files
