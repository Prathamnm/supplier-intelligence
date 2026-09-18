"""Shared fixtures.

`real` runs stages 01-06 once on the supplied data. `synthetic_raw`
writes a small, differently-shaped dataset -- different supplier IDs,
materials, file names and size -- to prove nothing in the pipeline is
tuned to the assignment's CSVs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import attribute, config, load, money, prepare, score
from pipeline.quality import Quality


@dataclass
class Run:
    ds: load.Dataset
    fact: pd.DataFrame
    att: attribute.Attribution
    orders: pd.DataFrame
    alloc: pd.DataFrame
    totals: pd.DataFrame
    sc: pd.DataFrame
    q: Quality


def run_stages(raw: Path) -> Run:
    q = Quality()
    ds = load.load_all(raw, q)
    fact, _ = prepare.build_fact_table(ds, q)
    fact = money.attach_benchmarks(fact, q)
    att = attribute.run(ds.customer_returns, fact, q)
    orders = money.per_order_losses(fact, q)
    premium = money.price_premium(orders, q)
    alloc = money.return_losses(ds.customer_returns, att.pairs, orders, q)
    totals = money.supplier_totals(orders, alloc, premium)
    cats = money.category_totals(orders, alloc)
    sc = score.build(totals, orders, cats, q)
    return Run(ds, fact, att, orders, alloc, totals, sc, q)


@pytest.fixture(scope="session")
def real() -> Run:
    if not any(config.RAW.glob("*.csv")):
        pytest.skip("source CSVs not present in pipeline/data/raw")
    return run_stages(config.RAW)


def make_synthetic(root: Path, n_suppliers: int = 9, n_orders: int = 900,
                   n_returns: int = 160, label_share: float = 0.6,
                   bad: tuple[int, ...] = (1, 4), seed: int = 7) -> Path:
    """A small panel where suppliers `bad` short-ship, run late and fail QC."""
    rng = np.random.default_rng(seed)
    sups = [f"SUP-{i:03d}" for i in range(n_suppliers)]
    mats = ["Copper Rod", "Brass Sheet", "Alu Tube", "Zinc Plate"]
    bad_ids = {sups[i] for i in bad}

    po_date = pd.Timestamp("2022-01-01") + pd.to_timedelta(rng.integers(0, 700, n_orders), "D")
    sup = rng.choice(sups, n_orders)
    mat = rng.choice(mats, n_orders)
    qty = rng.uniform(5, 40, n_orders).round(2)
    price = rng.uniform(40_000, 90_000, n_orders).round(2)
    is_bad = np.isin(sup, list(bad_ids))
    short = np.where(is_bad, rng.uniform(.02, .05, n_orders), rng.uniform(0, .01, n_orders))
    late = np.where(is_bad, rng.integers(2, 9, n_orders), rng.integers(0, 3, n_orders))
    promised = po_date + pd.to_timedelta(rng.integers(5, 12, n_orders), "D")
    received = (qty * (1 - short)).round(2)
    reject = np.where(is_bad, (received * rng.uniform(0, .05, n_orders)).round(2), 0.0)

    po = pd.DataFrame({
        "po_id": [f"X{i:05d}" for i in range(n_orders)], "po_date": po_date.date,
        "supplier_id": sup, "material_id": mat, "quantity_ordered": qty, "unit": "MT",
        "unit_price_quoted": price, "delivery_promised_date": promised.date,
        "payment_terms_days": 30})
    gr = pd.DataFrame({
        "gr_id": [f"G{i:05d}" for i in range(n_orders)], "po_id": po["po_id"],
        "receipt_date": (promised + pd.to_timedelta(late, "D")).date,
        "quantity_received": received,
        "quality_grade": np.where(reject > 0, "C", "A"), "rejection_qty": reject,
        "rejection_reason": np.where(reject > 0, "Dimensional deviation", None),
        "invoice_amount_billed": (qty * price).round(2)})
    inv = promised + pd.to_timedelta(late + 2, "D")
    pay = pd.DataFrame({
        "po_id": po["po_id"], "supplier_id": sup, "invoice_date": inv.date,
        "agreed_payment_days": 30,
        "actual_payment_date": (inv + pd.to_timedelta(rng.integers(25, 40, n_orders), "D")).date,
        "days_late": 0})

    weights = np.array([6.0 if s in bad_ids else 1.0 for s in sups])
    traced = rng.choice(sups, n_returns, p=weights / weights.sum())
    rdate = pd.Timestamp("2022-03-01") + pd.to_timedelta(rng.integers(0, 640, n_returns), "D")
    ret = pd.DataFrame({
        "return_id": [f"R{i:04d}" for i in range(n_returns)], "return_date": rdate.date,
        "client_id": "C1", "material_id": rng.choice(mats, n_returns),
        "quantity_returned": rng.uniform(.5, 4, n_returns).round(2),
        "reason": rng.choice(["Bend/warp", "Weight short", "Surface rust"], n_returns),
        "supplier_id_traced": np.where(rng.random(n_returns) < label_share, traced, None)})

    months = pd.period_range("2022-01", "2023-12", freq="M").astype(str)
    mpi = pd.DataFrame([{"month": m, "material_category": "Copper Rod",
                         "market_price_per_mt": 60_000, "source": "test"} for m in months])
    sm = pd.DataFrame({"supplier_id": sups, "supplier_name": [f"Firm {s}" for s in sups],
                       "material_categories": "Copper Rod,Alu Tube", "city": "Pune",
                       "years_of_relationship": rng.integers(1, 20, n_suppliers),
                       "contact_name": "A", "credit_days_agreed": 30,
                       "is_underperformer": [s in bad_ids for s in sups]})

    root.mkdir(parents=True, exist_ok=True)
    # Deliberately unhelpful file names: detection is by column signature.
    for name, df in {"Book1": po, "export (2)": gr, "rets": ret, "prices": mpi,
                     "payments_final": pay, "vendors": sm}.items():
        df.to_csv(root / f"{name}.csv", index=False)
    return root


@pytest.fixture
def synthetic_raw(tmp_path: Path) -> Path:
    return make_synthetic(tmp_path / "raw")
