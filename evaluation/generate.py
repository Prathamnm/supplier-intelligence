"""Synthetic datasets with a known answer.

Each scenario writes the same six CSVs the assignment supplies, in the
same schema, plus a `truth.json` the pipeline never sees: which
suppliers were planted as bad and how, the true supplier behind every
customer return (including the ones blanked out), and the exact rupee
short-delivery each supplier caused.

Unlike the assignment data, returns here are generated from actual
deliveries: a return comes from a specific batch, with probability rising
with that supplier's defect rate, some weeks after the batch arrived. So
the test also checks that the model adapts to a different mechanism
rather than memorising the assignment's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

MATERIALS = [
    "MS Pipes", "GI Pipes", "SS Pipes", "ERW Pipes", "MS Sheets", "HR Coils",
    "CR Sheets", "GI Sheets", "SS Sheets", "MS Rods", "MS Flats", "Hex Bars",
    "GI Wire", "Spring Steel", "Structural Steel", "Angles & Channels",
    "Square/Rect Tubes", "Fasteners & Fittings",
]
REASONS = ["Bend/warp", "Edge damage", "Wrong dimensions", "Surface rust", "Weight short", "Grade mismatch"]
CITIES = ["Pune", "Mumbai", "Nashik", "Aurangabad", "Nagpur", "Kolhapur", "Ahmedabad", "Chennai"]


@dataclass
class Profile:
    """How one supplier behaves. Defaults are a normal, decent supplier."""
    short: float = 0.005        # mean fraction of ordered qty not delivered
    late: float = 1.5           # mean days late
    reject: float = 0.0         # mean fraction rejected at inspection
    defect: float = 1.0         # multiplier on the chance a batch triggers customer returns
    premium: float = 0.0        # systematic price premium, fraction
    # material -> overrides, for a supplier that is bad on one line only
    by_material: dict[str, dict] = field(default_factory=dict)
    # ISO date from which the behaviour above applies; before it, a normal
    # supplier. Models a supplier that deteriorated recently.
    bad_from: str | None = None


@dataclass
class Scenario:
    name: str
    title: str
    purpose: str
    n_suppliers: int
    n_orders: int
    bad: dict[str, Profile]            # supplier_id -> planted behaviour
    price_noise: float = 0.10          # sd of per-order price noise (fraction)
    label_share: float = 0.65          # share of returns with supplier recorded
    # If set, returns from planted offenders are recorded at this rate instead:
    # clerks write the supplier down more often when it's a known problem one.
    label_share_bad: float | None = None
    return_rate: float = 0.0045        # returns per MT received, for a normal supplier
    materials: int = 18
    index_materials: int = 6
    years: int = 3
    tiny_suppliers: dict[str, int] = field(default_factory=dict)  # id -> order count
    # Behaviour that is *not* a planted offence -- e.g. a tiny supplier whose
    # two orders happened to go badly. The pipeline should not condemn them.
    unlucky: dict[str, Profile] = field(default_factory=dict)
    messy: bool = False
    # "batch": a return comes from a specific delivery, weeks after it arrived.
    # "propensity": as observed in the assignment data -- the supplier is
    # drawn by volume x defect rate, but the returned material and date are
    # unrelated to any particular batch.
    returns: str = "batch"
    # "iso" or "indian": how a spreadsheet/Tally export would actually look.
    export: str = "iso"
    seed: int = 0


def _profile(sc: Scenario, sid: str) -> Profile:
    return sc.bad.get(sid) or sc.unlucky.get(sid) or Profile()


def generate(sc: Scenario, root: Path) -> dict:
    rng = np.random.default_rng(sc.seed)
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    sups = [f"S{i:03d}" for i in range(1, sc.n_suppliers + 1)]
    mats = MATERIALS[: sc.materials]
    base_price = dict(zip(mats, rng.uniform(55_000, 115_000, len(mats)), strict=True))
    start = pd.Timestamp("2022-01-01")
    days = 365 * sc.years

    # -- orders: tiny suppliers get a fixed handful, the rest share the remainder
    tiny_total = sum(sc.tiny_suppliers.values())
    regular = [s for s in sups if s not in sc.tiny_suppliers]
    sup_col = list(rng.choice(regular, sc.n_orders - tiny_total))
    for sid, n in sc.tiny_suppliers.items():
        sup_col += [sid] * n
    sup_col = np.array(sup_col)
    rng.shuffle(sup_col)
    n = len(sup_col)

    po_date = start + pd.to_timedelta(rng.integers(0, days, n), "D")
    mat = rng.choice(mats, n)
    qty = rng.uniform(4, 50, n).round(2)
    drift = 1 + 0.06 * np.sin((po_date - start).days.to_numpy() / 365 * 2 * np.pi)

    short, late, reject, prem, defect = (np.empty(n) for _ in range(5))
    normal = Profile()
    for i, (s, m) in enumerate(zip(sup_col, mat, strict=True)):
        p = _profile(sc, s)
        if p.bad_from and po_date[i] < pd.Timestamp(p.bad_from):
            p = normal
        o = p.by_material.get(m, {})
        short[i] = max(0.0, rng.normal(o.get("short", p.short), max(o.get("short", p.short) * 0.35, 0.002)))
        late[i] = max(0.0, round(rng.normal(o.get("late", p.late), 1.0)))
        r = o.get("reject", p.reject)
        reject[i] = max(0.0, rng.normal(r, r * 0.5)) if r > 0 else 0.0
        prem[i] = o.get("premium", p.premium)
        defect[i] = o.get("defect", p.defect)
    short = np.minimum(short, 0.2)

    price = np.array([base_price[m] for m in mat]) * drift * (1 + prem) \
        * rng.lognormal(0, sc.price_noise, n)
    price = price.round(2)
    promised = po_date + pd.to_timedelta(rng.integers(4, 12, n), "D")
    receipt = promised + pd.to_timedelta(late, "D")
    received = (qty * (1 - short)).round(2)
    rejected = (received * reject).round(2)
    billed = (qty * price).round(2)

    po_ids = [f"PO-{d.year}-{i:05d}" for i, d in enumerate(po_date)]
    po = pd.DataFrame({
        "po_id": po_ids, "po_date": po_date.strftime("%Y-%m-%d"), "supplier_id": sup_col,
        "material_id": mat, "quantity_ordered": qty, "unit": "MT", "unit_price_quoted": price,
        "delivery_promised_date": promised.strftime("%Y-%m-%d"),
        "payment_terms_days": rng.choice([15, 21, 30, 45], n)})
    grade = np.where(rejected > 0, rng.choice(["B", "C"], n), rng.choice(["A", "B"], n, p=[.7, .3]))
    gr = pd.DataFrame({
        "gr_id": [f"GR-{i:05d}" for i in range(n)], "po_id": po_ids,
        "receipt_date": receipt.strftime("%Y-%m-%d"), "quantity_received": received,
        "quality_grade": grade, "rejection_qty": rejected,
        "rejection_reason": np.where(rejected > 0, "Dimensional deviation", None),
        "invoice_amount_billed": billed})
    inv = receipt + pd.to_timedelta(rng.integers(0, 4, n), "D")
    agreed = po["payment_terms_days"].to_numpy()
    paid = inv + pd.to_timedelta(agreed + rng.integers(-3, 15, n), "D")
    pay = pd.DataFrame({
        "po_id": po_ids, "supplier_id": sup_col, "invoice_date": inv.strftime("%Y-%m-%d"),
        "agreed_payment_days": agreed, "actual_payment_date": paid.strftime("%Y-%m-%d"),
        "days_late": np.maximum((paid - inv).days.to_numpy() - agreed, 0)})

    # -- returns: each comes from a real batch, weeks after it arrived
    lam = (received - rejected) * sc.return_rate * defect
    counts = rng.poisson(lam)
    rows = []
    for i in np.flatnonzero(counts):
        for _ in range(counts[i]):
            rdate = receipt[i] + pd.Timedelta(days=int(rng.gamma(2.0, 25.0)) + 3)
            if rdate > start + pd.Timedelta(days=days):
                continue
            if sc.returns == "propensity":
                rdate = receipt[i] + pd.Timedelta(days=int(rng.integers(3, 300)))
                if rdate > start + pd.Timedelta(days=days):
                    continue
            rows.append({"return_date": rdate,
                         "material_id": mat[i] if sc.returns == "batch" else rng.choice(mats),
                         "quantity_returned": round(float(min(rng.uniform(0.1, 5), received[i])), 2),
                         "true_supplier": sup_col[i], "reason": rng.choice(REASONS)})
    ret = pd.DataFrame(rows).sort_values("return_date").reset_index(drop=True)
    ret.insert(0, "return_id", [f"RET-{i:05d}" for i in range(len(ret))])
    ret["client_id"] = [f"Client-{c:03d}" for c in rng.integers(0, 90, len(ret))]
    share = np.where(ret["true_supplier"].isin(list(sc.bad)) & (sc.label_share_bad is not None),
                     sc.label_share_bad if sc.label_share_bad is not None else sc.label_share, sc.label_share)
    labelled = rng.random(len(ret)) < share
    ret["supplier_id_traced"] = np.where(labelled, ret["true_supplier"], None)
    ret["return_date"] = ret["return_date"].dt.strftime("%Y-%m-%d")

    # -- market index: a subset of materials, deliberately below transacted prices
    idx_mats = mats[: sc.index_materials]
    months = pd.period_range(start, periods=12 * sc.years, freq="M")
    mpi = pd.DataFrame([{
        "month": str(m), "material_category": mat_name,
        "market_price_per_mt": round(base_price[mat_name] * 0.85
                                     * (1 + 0.06 * np.sin((m.start_time - start).days / 365 * 2 * np.pi)), 0),
        "source": "Synthetic index"} for m in months for mat_name in idx_mats])

    sm = pd.DataFrame({
        "supplier_id": sups,
        "supplier_name": [f"Supplier {s}" for s in sups],
        "material_categories": [",".join(rng.choice(mats, 3, replace=False)) for _ in sups],
        "city": rng.choice(CITIES, len(sups)),
        # Bad suppliers get *long* relationships, as in the brief: this must not help them.
        "years_of_relationship": [int(rng.integers(8, 20)) if s in sc.bad else int(rng.integers(1, 15))
                                  for s in sups],
        "contact_name": "Contact", "credit_days_agreed": rng.choice([15, 21, 30], len(sups)),
        "is_underperformer": [s in sc.bad and _is_underperformer(sc.bad[s]) for s in sups]})

    frames = {"purchase_orders": po, "goods_receipts": gr, "payment_records": pay,
              "market_price_index": mpi, "supplier_master": sm,
              "customer_returns": ret.drop(columns=["true_supplier"])[
                  ["return_id", "return_date", "client_id", "material_id", "quantity_returned",
                   "reason", "supplier_id_traced"]]}
    names = {k: k for k in frames}
    if sc.messy:
        frames, names = _make_messy(frames, rng)
    if sc.export == "indian":
        for k, df in frames.items():
            _indian_export(df, rng).to_csv(raw / f"{names[k]}.csv", index=False, encoding="utf-8-sig")
    else:
        for k, df in frames.items():
            df.to_csv(raw / f"{names[k]}.csv", index=False)

    truth = {
        "scenario": sc.name,
        "bad": {s: {"short": p.short, "late": p.late, "reject": p.reject, "defect": p.defect,
                    "premium": p.premium, "by_material": p.by_material, "bad_from": p.bad_from,
                    "underperformer": _is_underperformer(p)} for s, p in sc.bad.items()},
        "return_truth": dict(zip(ret["return_id"], ret["true_supplier"], strict=True)),
        "blank_ids": ret.loc[~labelled, "return_id"].tolist(),
        "short_rs": (pd.Series(billed - received * price).groupby(sup_col).sum()).to_dict(),
        "return_qty_true": ret.groupby("true_supplier")["quantity_returned"].sum().to_dict(),
        "counts": {"suppliers": len(sups), "orders": n, "returns": len(ret),
                   "returns_blank": int((~labelled).sum())},
    }
    (root / "truth.json").write_text(json.dumps(truth, indent=1, default=float), encoding="utf-8")
    return truth


def _is_underperformer(p: Profile) -> bool:
    """The answer key flags any supplier planted with a supplier-wide fault."""
    return (p.short > 0.015 or p.late > 3.5 or p.reject > 0.005 or p.defect > 2 or p.premium > 0.03)


def _make_messy(frames: dict, rng) -> tuple[dict, dict]:
    """What real exports look like: odd names, duplicates, a few broken cells."""
    po = frames["purchase_orders"]
    dup = po.sample(12, random_state=1)
    frames["purchase_orders"] = pd.concat([po, dup]).sample(frac=1, random_state=2)   # duplicate POs
    gr = frames["goods_receipts"].copy()
    bad = gr.sample(5, random_state=3).index
    gr.loc[bad, "receipt_date"] = "not recorded"                                       # unparseable dates
    frames["goods_receipts"] = gr
    names = {"purchase_orders": "PO export 2024 (final)", "goods_receipts": "GRN_dump",
             "payment_records": "tally_payments", "market_price_index": "steel prices",
             "supplier_master": "vendors", "customer_returns": "Book1"}
    return frames, names


DATE_COLS = {"po_date", "delivery_promised_date", "receipt_date", "invoice_date",
             "actual_payment_date", "return_date"}
MONEY_COLS = {"unit_price_quoted", "invoice_amount_billed", "market_price_per_mt"}
ID_COLS = {"supplier_id", "supplier_id_traced", "po_id"}


def _inr_grouping(x: float) -> str:
    """1234567.5 -> '12,34,567.50', as Excel shows it with an en-IN locale."""
    whole, frac = f"{x:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail]) + "." + frac


def _indian_export(df: pd.DataFrame, rng) -> pd.DataFrame:
    """How the same table looks exported from Excel/Tally in India."""
    out = df.copy()
    for c in out.columns:
        if c in DATE_COLS:                       # 2023-04-02 -> 02/04/2023
            out[c] = pd.to_datetime(out[c]).dt.strftime("%d/%m/%Y")
        elif c in MONEY_COLS:                    # 2326836.99 -> "23,26,836.99"
            out[c] = out[c].map(_inr_grouping)
        elif c in ID_COLS:                       # stray spaces from manual entry
            out[c] = out[c].map(lambda v: f" {v} " if isinstance(v, str) and rng.random() < 0.1 else v)
    out["remarks"] = ""                          # an extra column nobody asked for
    return out[list(reversed(out.columns))]      # and a different column order
