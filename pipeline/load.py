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

import re
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

# Every column the pipeline reads. Anything else in an export (remarks,
# serial numbers, blank columns) is set aside at load, so an extra column
# can never collide with another file's in a join.
KNOWN_COLS: dict[str, set[str]] = {
    "purchase_orders": {"po_id", "po_date", "supplier_id", "material_id", "quantity_ordered", "unit",
                        "unit_price_quoted", "delivery_promised_date", "payment_terms_days"},
    "goods_receipts": {"gr_id", "po_id", "receipt_date", "quantity_received", "quality_grade",
                       "rejection_qty", "rejection_reason", "invoice_amount_billed"},
    "customer_returns": {"return_id", "return_date", "client_id", "material_id", "quantity_returned",
                         "reason", "supplier_id_traced"},
    "market_price_index": {"month", "material_category", "market_price_per_mt", "source"},
    "payment_records": {"po_id", "supplier_id", "invoice_date", "agreed_payment_days",
                        "actual_payment_date", "days_late"},
    "supplier_master": {"supplier_id", "supplier_name", "material_categories", "city",
                        "years_of_relationship", "contact_name", "credit_days_agreed",
                        config.LABEL_COLUMN},
}

ISO_DATE = re.compile(r"^\d{4}-\d{1,2}(-\d{1,2})?")
NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})")
# Currency symbols, digit grouping and spaces, as exported by Excel or Tally.
NUMBER_NOISE = re.compile(r"(?i)(₹|rs\.?|inr|,|\s)")

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


def identify(df: pd.DataFrame) -> str | None:
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
        # utf-8-sig drops the byte-order mark Excel writes, which would
        # otherwise corrupt the first column's name. Everything is read as
        # text and typed deliberately in _coerce.
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        name = identify(df)
        if name is None:
            q.warn(STAGE, "Unrecognised file",
                   f"{path.name} matched no known signature; ignored.",
                   rows_affected=len(df))
            continue
        if name in found:
            q.warn(STAGE, "Duplicate file",
                   f"{path.name} also matches {name}; keeping the first.")
            continue
        extra = [c for c in df.columns if c not in KNOWN_COLS[name]]
        if extra:
            q.info(STAGE, "Extra columns ignored",
                   f"{path.name} ({name}): {', '.join(extra[:6])} not used by the analysis.",
                   action="set aside")
            df = df.drop(columns=extra)
        found[name] = df
        q.count(f"rows.{name}", len(df))

    missing = set(SIGNATURES) - set(found)
    if missing:
        raise PipelineError(
            f"Missing required file(s): {', '.join(sorted(missing))}. "
            f"Found: {', '.join(sorted(found))}."
        )
    return found


def _day_first(frames: dict[str, pd.DataFrame], q: Quality) -> bool:
    """Decide once, for the whole dataset, whether 02/04/2023 is 2 April or 4 February.

    A value like 25/03/2023 can only be day-first and 03/25/2023 only
    month-first; one such value settles every file. With no deciding value
    the Indian convention (day first) is assumed, and said so -- a silent
    guess here would shift every date in the analysis.
    """
    firsts, seconds = [], []
    for name, df in frames.items():
        for col in DATE_COLS.get(name, []):
            if col not in df.columns:
                continue
            m = df[col].dropna().astype(str).str.strip().str.extract(NUMERIC_DATE).dropna()
            firsts.append(m[0].astype(int))
            seconds.append(m[1].astype(int))
    first = pd.concat(firsts) if firsts else pd.Series(dtype=int)
    second = pd.concat(seconds) if seconds else pd.Series(dtype=int)
    if first.empty:
        return False                             # ISO dates throughout
    if (first > 12).any() and (second > 12).any():
        raise PipelineError("Dates mix day-first and month-first formats (e.g. 25/03 and 03/25); "
                            "export them in one consistent format.")
    if (first > 12).any():
        q.info(STAGE, "Date format", "Dates are day-first (DD/MM/YYYY).")
        return True
    if (second > 12).any():
        q.info(STAGE, "Date format", "Dates are month-first (MM/DD/YYYY).")
        return False
    q.warn(STAGE, "Ambiguous date format",
           "No date settles whether values like 02/04/2023 are day-first or month-first; "
           "day-first (the Indian convention) was assumed.", action="assumed DD/MM/YYYY")
    return True


def _parse_dates(s: pd.Series, day_first: bool) -> pd.Series:
    text = s.astype("string").str.strip()
    iso = text.str.match(ISO_DATE).fillna(False).astype(bool)
    out = pd.to_datetime(text.where(iso), errors="coerce", format="mixed")
    other = text.where(~iso)
    if other.notna().any():
        out = out.fillna(pd.to_datetime(other, errors="coerce", format="mixed", dayfirst=day_first))
    return out


def _parse_numbers(s: pd.Series) -> pd.Series:
    """'23,26,836.99', '₹ 1,200' and ' 42 ' all become numbers."""
    text = s.astype("string").str.replace(NUMBER_NOISE, "", regex=True)
    return pd.to_numeric(text.replace("", pd.NA), errors="coerce")


def _coerce(name: str, df: pd.DataFrame, day_first: bool, q: Quality) -> pd.DataFrame:
    """Text is trimmed, dates become datetimes, numbers become numbers -- loudly."""
    df = df.apply(lambda c: c.str.strip().replace("", pd.NA) if c.dtype == object else c)

    parsers = (("dates", DATE_COLS.get(name, []), lambda c: _parse_dates(c, day_first)),
               ("numbers", NUM_COLS.get(name, []), _parse_numbers))
    for kind, cols, parse in parsers:
        for col in cols:
            if col not in df.columns:
                continue
            raw = df[col]
            before = int(raw.notna().sum())
            df[col] = parse(raw)
            lost = before - int(df[col].notna().sum())
            if not lost:
                continue
            examples = ", ".join(repr(v) for v in raw[df[col].isna() & raw.notna()].unique()[:3])
            if before and lost / before > config.MAX_UNPARSEABLE_SHARE:
                raise PipelineError(
                    f"{name}.{col}: {lost} of {before} values are not valid {kind} (e.g. {examples}). "
                    f"Fix the export and upload again.")
            q.warn(STAGE, f"Unparseable {kind}",
                   f"{name}.{col}: {lost} values could not be parsed (e.g. {examples}).",
                   rows_affected=lost, action="left blank")
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
    day_first = _day_first(frames, q)
    frames = {n: _coerce(n, df, day_first, q) for n, df in frames.items()}
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
