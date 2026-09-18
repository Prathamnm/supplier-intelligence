"""Tests for the properties the analysis depends on.

Each one guards a claim made in the write-up: if it fails, a sentence in
the approach document (pipeline/templates/approach.html.j2) has stopped
being true.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import attribute, brief, load, money, score
from pipeline.quality import PipelineError, Quality
from pipeline.run import run
from tests.conftest import make_synthetic, run_stages

# ------------------------------------------------------------- the 40%

def test_short_loss_is_the_rubric_formula_verbatim(real):
    o = real.orders
    expected = (o["invoice_amount_billed"] - o["quantity_received"] * o["unit_price_quoted"]).clip(lower=0)
    assert np.allclose(o["short_loss"], expected)


def test_supplier_totals_reconcile_to_orders_and_returns(real):
    t = real.totals
    assert np.isclose(t["short_loss"].sum(), real.orders["short_loss"].sum())
    assert np.isclose(t["return_loss"].sum(), real.alloc["return_loss"].sum())
    assert np.allclose(t["rubric_core_total"], t["short_loss"] + t["return_loss"])
    assert np.allclose(t["total_impact"],
                       t["rubric_core_total"] + t["reject_loss"] + t["handling_loss"] + t["premium_loss"])


def test_every_returned_tonne_is_allocated_exactly_once(real):
    returned = real.ds.customer_returns["quantity_returned"].sum()
    assert np.isclose(real.alloc["return_qty"].sum(), returned)


def test_premium_only_charged_when_significant(real):
    t = real.totals
    assert (t.loc[~t["premium_significant"].astype(bool), "premium_loss"] == 0).all()


# ------------------------------------------------------------- the 35%

def test_recorded_returns_go_wholly_to_their_supplier(real):
    rec = real.att.pairs[real.att.pairs["source"] == "recorded"]
    truth = real.ds.customer_returns.set_index("return_id")["supplier_id_traced"]
    assert (rec["probability"] == 1.0).all()
    assert (rec["supplier_id"].to_numpy() == truth.loc[rec["return_id"]].to_numpy()).all()


def test_inferred_probabilities_sum_to_one(real):
    inf = real.att.pairs[real.att.pairs["source"] == "inferred"]
    sums = inf.groupby("return_id")["probability"].sum()
    assert np.allclose(sums, 1.0)
    blank = real.ds.customer_returns["supplier_id_traced"].isna().sum()
    assert len(sums) == blank


def test_model_beats_every_baseline(real):
    m, b = real.att.metrics, real.att.baselines
    for name, base in b.items():
        assert m["misallocation"] < base["misallocation"], name
        assert m["top3"] > base["top3"], name


def test_features_are_causal(real):
    """Deliveries after a return's date must not change its features."""
    returns = real.ds.customer_returns
    before = attribute.build_candidates(returns, real.fact, Quality())
    future = real.fact.copy()
    future["receipt_date"] = returns["return_date"].max() + pd.Timedelta(days=30)
    future["rejection_qty"] = future["quantity_received"]   # catastrophic, but later
    after = attribute.build_candidates(returns, pd.concat([real.fact, future]), Quality())
    cols = ["recency", "material_share", "rejection_rate", "short_rate", "late_days"]
    a = before.set_index(["return_id", "supplier_id"])[cols].sort_index()
    b = after.set_index(["return_id", "supplier_id"])[cols].sort_index()
    pd.testing.assert_frame_equal(a, b)


def test_falls_back_loudly_without_labels(tmp_path):
    raw = make_synthetic(tmp_path / "raw", label_share=0.0)
    r = run_stages(raw)
    assert r.att.method == "fallback"
    assert any(f.title == "Model not trained" for f in r.q.findings)


# ----------------------------------------------------------- scorecard

def test_answer_key_never_reaches_the_analysis(real):
    assert "is_underperformer" not in real.ds.supplier_master.columns
    assert "is_underperformer" not in real.fact.columns
    assert real.ds._sealed_labels  # kept aside for the blind check only


def test_relationship_length_does_not_affect_scores(real):
    orders = real.orders.copy()
    orders["years_of_relationship"] = orders["years_of_relationship"].sample(
        frac=1, random_state=0).to_numpy()
    cats = money.category_totals(orders, real.alloc)
    shuffled = score.build(real.totals, orders, cats, Quality())
    a = real.sc.set_index("supplier_id")["score"].sort_index()
    b = shuffled.set_index("supplier_id")["score"].sort_index()
    pd.testing.assert_series_equal(a, b)


def test_blind_validation_on_supplied_data(real):
    v = score.blind_validation(real.sc, real.ds._sealed_labels, Quality())
    assert v["precision"] == 1.0


def test_bottom_three_stable_across_weightings(real):
    assert score.stability(real.sc)["stable"]


# --------------------------------------------------------- robustness

def test_generalises_to_a_different_dataset(tmp_path):
    """Other IDs, materials, file names and size; no code changes."""
    raw = make_synthetic(tmp_path / "raw")
    summary = run(raw, pdf=False, web=False, out=tmp_path / "out")
    assert summary["counts"]["suppliers"] == 9
    assert set(summary["validation"]["hits"]) == {"SUP-001", "SUP-004"}
    assert (tmp_path / "out" / "data" / "suppliers.json").exists()
    assert len(list((tmp_path / "out" / "briefs").glob("*.html"))) == 5


def test_missing_file_fails_clearly(tmp_path):
    raw = make_synthetic(tmp_path / "raw")
    (raw / "rets.csv").unlink()
    with pytest.raises(PipelineError, match="customer_returns"):
        load.load_all(raw, Quality())


def test_mixed_units_fail_clearly(tmp_path):
    raw = make_synthetic(tmp_path / "raw")
    po = pd.read_csv(raw / "Book1.csv")
    po.loc[0, "unit"] = "KG"
    po.to_csv(raw / "Book1.csv", index=False)
    with pytest.raises(PipelineError, match="Mixed units"):
        load.load_all(raw, Quality())


@pytest.mark.parametrize("value,expected", [
    (0, "₹0"), (999, "₹999"), (1000, "₹1,000"), (123456, "₹1,23,456"),
    (12345678.4, "₹1,23,45,678"), (-4200, "-₹4,200"),
])
def test_indian_number_format(value, expected):
    assert brief.inr(value) == expected


def test_no_false_alarms_when_nobody_is_bad(tmp_path):
    """On a panel where every supplier behaves the same, nobody is 'act now'.

    Guards against scoring relative to the panel's worst, which condemns
    someone even when the differences are pure noise. Also runs the whole
    pipeline with an answer key that flags nobody.
    """
    raw = make_synthetic(tmp_path / "raw", bad=())
    summary = run(raw, pdf=False, web=False, out=tmp_path / "out")
    r = run_stages(raw)
    assert (r.sc["band"] != "act").all(), r.sc.loc[r.sc["band"] == "act", ["supplier_id", "score"]]
    assert summary["validation"]["flagged"] == []
    assert summary["premium"]["significant"] == []


def test_indian_spreadsheet_exports_give_the_same_answer(tmp_path):
    """DD/MM/YYYY dates, 12,34,567.89 amounts, a BOM, extra and reordered columns,
    stray spaces: the rupee figures must match the clean files exactly."""
    from evaluation.generate import Profile, Scenario, generate
    base = dict(n_suppliers=12, n_orders=900, seed=5, bad={"S003": Profile(short=0.04)},
                name="t", title="t", purpose="t")
    generate(Scenario(**base), tmp_path / "clean")
    generate(Scenario(**base, export="indian"), tmp_path / "excel")
    clean = run_stages(tmp_path / "clean" / "raw")
    excel = run_stages(tmp_path / "excel" / "raw")
    a = clean.totals.set_index("supplier_id")["short_loss"].sort_index()
    b = excel.totals.set_index("supplier_id")["short_loss"].sort_index()
    pd.testing.assert_series_equal(a, b)
    assert excel.fact["po_date"].equals(clean.fact["po_date"])          # day-first read correctly


def test_unparseable_numbers_stop_the_run(tmp_path):
    raw = make_synthetic(tmp_path / "raw")
    po = pd.read_csv(raw / "Book1.csv")
    po["unit_price_quoted"] = "call supplier"
    po.to_csv(raw / "Book1.csv", index=False)
    with pytest.raises(PipelineError, match="unit_price_quoted"):
        load.load_all(raw, Quality())
