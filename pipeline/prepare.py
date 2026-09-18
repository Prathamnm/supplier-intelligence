"""Stage 02 -- map and join.

Two jobs.

First, build the mapping no source file provides. Purchase orders carry
a `material_id` like MAT-GI-PIPE-04; the market price index is keyed on
a `material_category` like "GI Pipes". Nothing connects them, and
without that link the price-premium dimension -- a quarter of the
scorecard -- cannot be computed at all.

Second, flatten purchase orders, goods receipts, payments and supplier
details into one fact table, asserting after every join that no row was
duplicated or lost. A merge that silently fans out is the most common
way a pipeline like this produces confident nonsense.
"""

from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process

from pipeline.load import Dataset
from pipeline.quality import Quality

STAGE = "02-prepare"

FUZZY_THRESHOLD = 85
UNMAPPED = "UNMAPPED"

# Tokens that appear in identifiers but carry no category meaning.
_NOISE = re.compile(r"^(mat|material|itm|item|sku)$", re.I)


def _normalise(text: str) -> str:
    """Collapse a label to a comparable key.

    "GI Pipes", "GI-PIPE", "gi pipe" all become "gipipe", so the common
    singular/plural and separator differences stop mattering.
    """
    key = re.sub(r"[^a-z0-9]+", "", str(text).lower())
    return re.sub(r"s$", "", key)


def _category_vocabulary(ds: Dataset, q: Quality) -> list[str]:
    """Every category name known to the dataset, from both sources."""
    vocab: set[str] = set(
        ds.market_price_index["material_category"].dropna().astype(str).str.strip()
    )

    raw = ds.supplier_master["material_categories"].dropna().astype(str)
    delim = next((d for d in (";", "|", ",") if raw.str.contains(d, regex=False).any()),
                 None)
    if delim:
        for cell in raw:
            vocab.update(part.strip() for part in cell.split(delim) if part.strip())
    else:
        vocab.update(raw.str.strip())

    vocab.discard("")
    q.info(STAGE, "Category vocabulary",
           f"{len(vocab)} distinct categories discovered across "
           f"market_price_index and supplier_master.")
    return sorted(vocab)


def _material_to_category(material_id: str, lookup: dict[str, str],
                          vocab: list[str]) -> tuple[str, str]:
    """Resolve one material_id to a category. Returns (category, method)."""
    parts = [p for p in re.split(r"[-_\s]+", str(material_id)) if p]
    parts = [p for p in parts if not _NOISE.match(p) and not p.isdigit()]
    if not parts:
        return UNMAPPED, "none"

    candidate = " ".join(parts)

    hit = lookup.get(_normalise(candidate))
    if hit:
        return hit, "exact"

    # Drop a trailing variant token (MAT-GI-PIPE-04-HEAVY -> GI PIPE)
    for cut in range(len(parts) - 1, 0, -1):
        hit = lookup.get(_normalise(" ".join(parts[:cut])))
        if hit:
            return hit, "prefix"

    match = process.extractOne(candidate, vocab, scorer=fuzz.token_set_ratio)
    if match and match[1] >= FUZZY_THRESHOLD:
        return match[0], "fuzzy"

    # A readable name that simply isn't listed anywhere else is its own
    # category; only an opaque code with nothing to match stays unmapped.
    if any(c.isalpha() for c in candidate) and not any(c.isdigit() for c in str(material_id)):
        return str(material_id).strip(), "self"
    return UNMAPPED, "none"


def build_category_map(ds: Dataset, q: Quality) -> pd.DataFrame:
    vocab = _category_vocabulary(ds, q)
    lookup = {_normalise(v): v for v in vocab}

    materials = sorted(ds.purchase_orders["material_id"].dropna().astype(str).unique())
    rows = [
        {"material_id": m, "material_category": cat, "mapping_method": how}
        for m in materials
        for cat, how in [_material_to_category(m, lookup, vocab)]
    ]
    mapping = pd.DataFrame(rows)

    by_method = mapping["mapping_method"].value_counts().to_dict()
    unmapped = mapping.loc[mapping["material_category"] == UNMAPPED, "material_id"]

    q.info(STAGE, "Material to category mapping",
           f"{len(materials)} materials resolved to "
           f"{mapping['material_category'].nunique()} categories "
           f"({by_method}).")
    if len(unmapped):
        q.warn(STAGE, "Unmapped materials",
               f"{len(unmapped)} material_id values matched no category: "
               f"{list(unmapped[:8])}. Excluded from price benchmarking, "
               f"retained everywhere else.",
               rows_affected=len(unmapped), action="category=UNMAPPED")
    return mapping


def _collapse_receipts(gr: pd.DataFrame, q: Quality) -> pd.DataFrame:
    """A PO may legitimately be received in more than one delivery."""
    per_po = gr.groupby("po_id").size()
    if per_po.max() <= 1:
        return gr

    q.info(STAGE, "Split deliveries",
           f"{int((per_po > 1).sum())} purchase orders were received across "
           f"multiple goods receipts; quantities summed, latest receipt date "
           f"used for lateness.",
           rows_affected=int(per_po[per_po > 1].sum()))

    agg = {
        "receipt_date": "max",
        "quantity_received": "sum",
        "rejection_qty": "sum",
        "invoice_amount_billed": "sum",
        "gr_id": "first",
    }
    for col in ("quality_grade", "rejection_reason"):
        if col in gr.columns:
            agg[col] = "first"

    return gr.groupby("po_id", as_index=False).agg(
        {k: v for k, v in agg.items() if k in gr.columns}
    )


def _merge(left: pd.DataFrame, right: pd.DataFrame, on: str,
           label: str, q: Quality) -> pd.DataFrame:
    """Left join with a row-count assertion. Non-negotiable."""
    before = len(left)
    out = left.merge(right, on=on, how="left")
    if len(out) != before:
        raise AssertionError(
            f"{label}: join on {on!r} changed the row count "
            f"{before} -> {len(out)}. The right side has duplicate keys."
        )
    key = right.columns.difference([on])[0]
    matched = out[key].notna().mean()
    q.info(STAGE, f"Joined {label}", f"{matched:.1%} of rows matched on {on}.")
    return out


def _recompute_days_late(fact: pd.DataFrame, q: Quality) -> pd.DataFrame:
    """The supplied days_late does not always reconcile with the dates."""
    need = {"invoice_date", "agreed_payment_days", "actual_payment_date"}
    if not need <= set(fact.columns):
        return fact

    due = fact["invoice_date"] + pd.to_timedelta(
        fact["agreed_payment_days"], unit="D")
    fact["payment_days_late_computed"] = (
        fact["actual_payment_date"] - due).dt.days.clip(lower=0)

    if "days_late" in fact.columns:
        diff = (fact["payment_days_late_computed"] - fact["days_late"]).abs()
        disagree = float((diff > 0).mean())
        if disagree > 0.01:
            q.warn(STAGE, "days_late does not reconcile",
                   f"The supplied days_late disagrees with a date-based "
                   f"recomputation on {disagree:.1%} of rows "
                   f"(mean difference {diff.mean():.1f} days). Both columns "
                   f"are retained; the recomputed value is used.",
                   rows_affected=int((diff > 0).sum()),
                   action="use payment_days_late_computed")
    return fact


def build_fact_table(ds: Dataset, q: Quality) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per purchase order, carrying its whole story."""
    mapping = build_category_map(ds, q)

    po = ds.purchase_orders.copy()
    po["material_id"] = po["material_id"].astype(str)
    fact = po.merge(mapping, on="material_id", how="left")
    fact["material_category"] = fact["material_category"].fillna(UNMAPPED)

    gr = _collapse_receipts(ds.goods_receipts, q)
    gr_cols = [c for c in gr.columns if c != "supplier_id"]
    fact = _merge(fact, gr[gr_cols], "po_id", "goods_receipts", q)

    pay_cols = [c for c in ds.payment_records.columns if c != "supplier_id"]
    fact = _merge(fact, ds.payment_records[pay_cols], "po_id", "payment_records", q)

    sm_cols = [c for c in ds.supplier_master.columns
               if c not in {"material_categories"}]
    fact = _merge(fact, ds.supplier_master[sm_cols], "supplier_id",
                  "supplier_master", q)

    fact = _recompute_days_late(fact, q)

    # po_id carries a year prefix that does not always match po_date.
    # Every time grouping in this project uses po_date.
    fact["year"] = fact["po_date"].dt.year
    fact["month"] = fact["po_date"].dt.to_period("M").dt.to_timestamp()

    fact["days_late_delivery"] = (
        fact["receipt_date"] - fact["delivery_promised_date"]).dt.days
    fact["is_late"] = fact["days_late_delivery"] > 0

    prefix = fact["po_id"].astype(str).str.extract(r"(\d{4})")[0].astype("Float64")
    mismatch = float((prefix != fact["year"]).mean())
    if mismatch > 0.01:
        q.warn(STAGE, "po_id year prefix is not the order year",
               f"The four-digit prefix in po_id disagrees with po_date on "
               f"{mismatch:.1%} of rows. All time grouping uses po_date; "
               f"po_id is treated as an opaque label.",
               rows_affected=int((prefix != fact["year"]).sum()))

    q.count("fact_rows", len(fact))
    q.count("suppliers", fact["supplier_id"].nunique())
    q.count("categories", fact["material_category"].nunique())
    q.info(STAGE, "Fact table built",
           f"{len(fact):,} purchase orders, {fact['supplier_id'].nunique()} "
           f"suppliers, {fact['material_category'].nunique()} categories, "
           f"{fact['year'].min():.0f}-{fact['year'].max():.0f}.")

    return fact, mapping
