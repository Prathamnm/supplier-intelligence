"""Stage 01 -- load and validate.

Reads the six source files, identifies each by its column signature
rather than its filename, coerces types, and refuses to continue if the
data cannot support the arithmetic downstream.

Also removes the answer key. `is_underperformer` is stashed away here
and never returned with the working data, so no scoring or modelling
code can reach it. It is re-read at the very end, by score.py, purely
to check whether our independent ranking found the same suppliers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pipeline import config
from pipeline.quality import PipelineError, Quality

STAGE = "01-load"

# A file is identified by the columns it contains. This means the
# pipeline works on files named Book1.csv, and fails clearly rather than
# mysteriously when a file is missing.
SIGNATURES: dict[str, set[str]] = {
    "purchase_orders": {"po_id", "supplier_id", "quantity_ordered", "unit_price_quoted"},
    "goods_receipts": {"gr_id", "po_id", "quantity_received", "invoice_amount_billed"},
    "customer_returns": {"return_id", "return_date", "quantity_returned"},
    "market_price_index": {"month", "material_category", "market_price_per_mt"},
    "payment_records": {"po_id", "actual_payment_date", "agreed_payment_days"},
    "supplier_master": {"supplier_id", "supplier_name", "material_categories"},
}

DATE_COLS: dict[str, list[str]] = {
    "purchase_orders": ["po_date", "delivery_promised_date"],
    "goods_receipts": ["receipt_date"],
    "customer_returns": ["return_date"],
    "payment_records": ["invoice_date", "actual_payment_date"],
    "market_price_index": ["month"],
}

NUM_COLS: dict[str, list[str]] = {
    "purchase_orders": ["quantity_ordered", "unit_price_quoted", "payment_terms_days"],
    "goods_receipts": ["quantity_received", "rejection_qty", "invoice_amount_billed"],
    "customer_returns": ["quantity_returned"],
    "market_price_index": ["market_price_per_mt"],
    "payment_records": ["agreed_payment_days", "days_late"],
    "supplier_master": ["years_of_relationship", "credit_days_agreed"],
}

KEY_COLS: dict[str, str] = {
    "purchase_orders": "po_id",
    "goods_receipts": "gr_id",
    "customer_returns": "return_id",
    "supplier_master": "supplier_id",
}


@dataclass
class Dataset:
    """The six validated frames, plus the sealed answer key."""

    purchase_orders: pd.DataFrame
    goods_receipts: pd.DataFrame
    customer_returns: pd.DataFrame
    market_price_index: pd.DataFrame
    payment_records: pd.DataFrame
    supplier_master: pd.DataFrame
    quality: Quality
    # Never passed to scoring or modelling. Opened only by the blind
    # validation step at the very end.
    _sealed_labels: dict[str, bool] = field(default_factory=dict, repr=False)

    def frames(self) -> dict[str, pd.DataFrame]:
        return {
            "purchase_orders": self.purchase_orders,
            "goods_receipts": self.goods_receipts,
            "customer_returns": self.customer_returns,
            "market_price_index": self.market_price_index,
            "payment_records": self.payment_records,
            "supplier_master": self.supplier_master,
        }


def _identify(df: pd.DataFrame) -> str | None:
    cols = set(df.columns)
    for name, required in SIGNATURES.items():
        if required <= cols:
            return name
    return None


def _discover(raw_dir: Path, q: Quality) -> dict[str, pd.DataFrame]:
    if not raw_dir.exists():
        raise PipelineError(f"Missing directory: {raw_dir}")

    paths = sorted(raw_dir.glob("*.csv"))
    if not paths:
        raise PipelineError(
            f"No CSV files in {raw_dir}. Download the six source files first."
        )

    found: dict[str, pd.DataFrame] = {}
    for path in paths:
        df = pd.read_csv(path)
        name = _identify(df)
        if name is None:
            q.warn(STAGE, "Unrecognised file",
                   f"{path.name} matched no known signature; ignored.",
                   rows_affected=len(df))
            continue
        if name in found:
            q.warn(STAGE, "Duplicate file",
                   f"{path.name} also matches {name}; keeping the first.")
            continue
        found[name] = df
        q.count(f"rows.{name}", len(df))

    missing = set(SIGNATURES) - set(found)
    if missing:
        raise PipelineError(
            f"Missing required file(s): {', '.join(sorted(missing))}. "
            f"Found: {', '.join(sorted(found))}."
        )
    return found


def _coerce(name: str, df: pd.DataFrame, q: Quality) -> pd.DataFrame:
    """Dates become datetimes, numbers become numbers, loudly."""
    df = df.copy()

    for col in DATE_COLS.get(name, []):
        if col not in df.columns:
            continue
        before = df[col].notna().sum()
        df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
        lost = before - df[col].notna().sum()
        if lost:
            q.warn(STAGE, "Unparseable dates",
                   f"{name}.{col}: {lost} values could not be parsed.",
                   rows_affected=int(lost), action="set to NaT")

    for col in NUM_COLS.get(name, []):
        if col not in df.columns:
            continue
        before = df[col].notna().sum()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        lost = before - df[col].notna().sum()
        if lost:
            q.warn(STAGE, "Non-numeric values",
                   f"{name}.{col}: {lost} values could not be parsed.",
                   rows_affected=int(lost), action="set to NaN")

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    return df


def _dedupe(name: str, df: pd.DataFrame, q: Quality) -> pd.DataFrame:
    key = KEY_COLS.get(name)
    if key is None or key not in df.columns:
        return df
    dupes = int(df[key].duplicated().sum())
    if dupes:
        q.warn(STAGE, "Duplicate keys",
               f"{name}.{key}: {dupes} duplicate rows removed.",
               rows_affected=dupes, action="kept first occurrence")
        df = df.drop_duplicates(subset=key, keep="first")
    return df


def _check_units(po: pd.DataFrame, q: Quality) -> None:
    """Mixed units would put unit_price_quoted on different scales and
    silently corrupt every rupee figure in the project."""
    if "unit" not in po.columns:
        q.info(STAGE, "No unit column",
               "Assuming a single implicit unit for all quantities.")
        return

    units = po["unit"].dropna().unique()
    if len(units) == 1:
        q.info(STAGE, "Units uniform", f"All quantities are in {units[0]!r}.")
    else:
        raise PipelineError(
            f"Mixed units in purchase_orders.unit: {sorted(units)}. "
            "unit_price_quoted is on different scales across rows, so every "
            "rupee figure would be wrong. Add a conversion table to config.py."
        )


def _check_billing_identity(po: pd.DataFrame, gr: pd.DataFrame, q: Quality) -> None:
    """The judging criteria states the loss formula as
        invoice_amount_billed - (quantity_received * unit_price_quoted)

    That is only equivalent to short-delivery loss if billing is on the
    ordered quantity. Verify it rather than assume it.
    """
    m = gr[["po_id", "quantity_received", "invoice_amount_billed"]].merge(
        po[["po_id", "quantity_ordered", "unit_price_quoted"]],
        on="po_id", how="inner")
    if m.empty:
        q.warn(STAGE, "Billing identity unchecked", "No overlapping po_id values.")
        return

    on_ordered = m["quantity_ordered"] * m["unit_price_quoted"]
    share = float((m["invoice_amount_billed"] - on_ordered).abs().lt(1).mean())

    if share > 0.95:
        q.info(STAGE, "Billing is on ordered quantity",
               f"invoice_amount_billed == quantity_ordered x unit_price_quoted "
               f"on {share:.1%} of matched rows, so the rubric's formula and "
               f"(ordered - received) x price are the same number.")
    else:
        q.warn(STAGE, "Billing identity does not hold",
               f"Only {share:.1%} of rows match quantity_ordered x price. "
               f"Short-delivery loss will be computed from the rubric's "
               f"formula directly rather than the quantity gap.",
               action="use invoice - (received x price)")


def _seal_labels(sm: pd.DataFrame, q: Quality) -> tuple[pd.DataFrame, dict[str, bool]]:
    """Remove the answer key before anything else can see it."""
    col = config.LABEL_COLUMN
    if col not in sm.columns:
        q.info(STAGE, "No label column",
               f"`{col}` not present; blind validation will be skipped.")
        return sm, {}

    truthy = sm[col].astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})
    sealed = dict(zip(sm["supplier_id"], truthy, strict=True))
    flagged = sorted(sm.loc[truthy, "supplier_id"])

    q.info(STAGE, "Answer key sealed",
           f"`{col}` flags {len(flagged)} supplier(s). Dropped before any "
           f"scoring or modelling code runs; re-opened only for blind "
           f"validation after the ranking is final.",
           rows_affected=len(flagged), action="excluded from all features")

    return sm.drop(columns=[col]), sealed


def load_all(raw_dir: Path | None = None, q: Quality | None = None) -> Dataset:
    q = q or Quality()
    raw_dir = raw_dir or config.RAW

    frames = _discover(raw_dir, q)
    frames = {n: _coerce(n, df, q) for n, df in frames.items()}
    frames = {n: _dedupe(n, df, q) for n, df in frames.items()}

    _check_units(frames["purchase_orders"], q)
    _check_billing_identity(frames["purchase_orders"], frames["goods_receipts"], q)

    frames["supplier_master"], sealed = _seal_labels(frames["supplier_master"], q)

    for name, df in frames.items():
        nulls = df.isna().sum()
        for col, n in nulls[nulls > 0].items():
            q.info(STAGE, "Nulls present", f"{name}.{col}: {n} ({n / len(df):.1%})",
                   rows_affected=int(n))

    return Dataset(quality=q, _sealed_labels=sealed, **frames)
