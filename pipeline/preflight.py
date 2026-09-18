"""Pre-flight checks. Run this first, before any real logic exists.

Answers the ten questions that decide whether our design assumptions
hold, and prints the findings that become the data-quality section of
the write-up. It is read-only and never modifies anything.

    python -m pipeline.preflight
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from pipeline import config

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 40)


# Column fingerprints, used to identify a file by its contents rather
# than its name -- so the pipeline works on files named Book1.csv.
SIGNATURES = {
    "purchase_orders": {"po_id", "supplier_id", "quantity_ordered", "unit_price_quoted"},
    "goods_receipts": {"gr_id", "po_id", "quantity_received", "invoice_amount_billed"},
    "customer_returns": {"return_id", "return_date", "quantity_returned"},
    "market_price_index": {"month", "material_category", "market_price_per_mt"},
    "payment_records": {"po_id", "actual_payment_date", "agreed_payment_days"},
    "supplier_master": {"supplier_id", "supplier_name", "material_categories"},
}

RULE = "-" * 74


def head(text: str) -> None:
    print(f"\n{RULE}\n  {text}\n{RULE}")


def identify(path: Path) -> tuple[str | None, pd.DataFrame]:
    """Read a CSV and work out which of the six datasets it is."""
    df = pd.read_csv(path)
    cols = set(df.columns)
    for name, required in SIGNATURES.items():
        if required <= cols:
            return name, df
    return None, df


def discover() -> dict[str, pd.DataFrame]:
    if not config.RAW.exists():
        sys.exit(f"Missing directory: {config.RAW}")

    paths = sorted(config.RAW.glob("*.csv"))
    if not paths:
        sys.exit(
            f"No CSV files found in {config.RAW}\n"
            "Download the six files from the assignment's Drive folder first."
        )

    found: dict[str, pd.DataFrame] = {}
    head(f"FILES IN {config.RAW}")
    for p in paths:
        name, df = identify(p)
        size_kb = p.stat().st_size / 1024
        if name:
            found[name] = df
            print(f"  ok   {p.name:<32} -> {name:<20} "
                  f"{len(df):>6,} rows  {len(df.columns):>2} cols  {size_kb:>7.0f} KB")
        else:
            print(f"  ??   {p.name:<32} -> UNRECOGNISED         "
                  f"{len(df):>6,} rows  {len(df.columns):>2} cols  {size_kb:>7.0f} KB")
            print(f"       columns: {list(df.columns)}")

    missing = set(SIGNATURES) - set(found)
    if missing:
        print(f"\n  MISSING: {', '.join(sorted(missing))}")
    return found


def check_units(po: pd.DataFrame) -> None:
    """Blocks every rupee-per-tonne calculation if units are mixed."""
    head("1. UNITS  -- blocks all money math if not uniform")
    if "unit" not in po.columns:
        print("  No `unit` column. Assuming a single implicit unit throughout.")
        return
    counts = po["unit"].value_counts(dropna=False)
    print(counts.to_string())
    if len(counts) == 1:
        print(f"\n  PASS  uniform: {counts.index[0]!r}")
    else:
        print("\n  FAIL  mixed units -- unit_price_quoted is on different scales.")
        print("        config.py needs a conversion table before any money math.")


def check_grades(gr: pd.DataFrame) -> None:
    head("2. QUALITY GRADE  -- real vocabulary before we encode it")
    if "quality_grade" not in gr.columns:
        print("  No `quality_grade` column.")
        return
    print(gr["quality_grade"].value_counts(dropna=False).to_string())


def check_materials(po: pd.DataFrame, mpi: pd.DataFrame, sm: pd.DataFrame) -> None:
    """The mapping nobody gave us. Price benchmarking depends on it."""
    head("3. MATERIAL -> CATEGORY  -- the mapping no file provides")

    mats = sorted(po["material_id"].dropna().unique())
    print(f"  distinct material_id in purchase_orders : {len(mats)}")
    print(f"  sample: {mats[:6]}")

    idx_cats = sorted(mpi["material_category"].dropna().unique())
    print(f"\n  categories in market_price_index        : {len(idx_cats)}")
    for c in idx_cats:
        print(f"    - {c}")

    if "material_categories" in sm.columns:
        raw = sm["material_categories"].dropna().astype(str)
        for delim in (";", ",", "|"):
            if raw.str.contains(delim, regex=False).any():
                print(f"\n  supplier_master.material_categories delimiter: {delim!r}")
                vocab = sorted({
                    part.strip()
                    for cell in raw for part in cell.split(delim) if part.strip()
                })
                break
        else:
            print("\n  supplier_master.material_categories appears single-valued")
            vocab = sorted(raw.str.strip().unique())
        print(f"  distinct categories across suppliers    : {len(vocab)}")
        for c in vocab:
            mark = "  " if c in idx_cats else " *"
            print(f"   {mark} {c}")
        print("\n  (* = no market index -> falls back to peer-median benchmarking)")


def check_identity(po: pd.DataFrame, gr: pd.DataFrame) -> None:
    """The rubric's formula rests on how invoice_amount_billed is computed."""
    head("4. BILLING IDENTITY  -- underpins the 40% criterion")
    m = gr.merge(po[["po_id", "quantity_ordered", "quantity_received"]
                    if "quantity_received" in po.columns
                    else ["po_id", "quantity_ordered"]]
                 .assign(**{}), on="po_id", how="left", suffixes=("", "_po"))
    m = gr.merge(po[["po_id", "quantity_ordered", "unit_price_quoted"]],
                 on="po_id", how="left")

    expected_ordered = m["quantity_ordered"] * m["unit_price_quoted"]
    expected_received = m["quantity_received"] * m["unit_price_quoted"]
    billed = m["invoice_amount_billed"]

    hits_ordered = (billed - expected_ordered).abs().lt(1).mean()
    hits_received = (billed - expected_received).abs().lt(1).mean()

    print(f"  invoice == quantity_ORDERED  x unit_price : {hits_ordered:6.1%} of rows")
    print(f"  invoice == quantity_RECEIVED x unit_price : {hits_received:6.1%} of rows")
    if hits_ordered > 0.95:
        print("\n  CONFIRMED  billing is on ordered quantity, so")
        print("             invoice - (received x price) == (ordered - received) x price")
        print("             i.e. the rubric's formula and short-delivery loss agree.")


def check_dates(frames: dict[str, pd.DataFrame]) -> None:
    head("5. DATE RANGES  -- confirm the 3-year window")
    for name, col in [("purchase_orders", "po_date"),
                      ("goods_receipts", "receipt_date"),
                      ("customer_returns", "return_date"),
                      ("payment_records", "actual_payment_date")]:
        df = frames.get(name)
        if df is None or col not in df.columns:
            continue
        s = pd.to_datetime(df[col], errors="coerce")
        bad = s.isna().sum()
        print(f"  {name:<20} {col:<22} {s.min():%Y-%m-%d} -> {s.max():%Y-%m-%d}"
              f"   unparseable: {bad}")

    po = frames.get("purchase_orders")
    if po is not None and "po_date" in po:
        yr = pd.to_datetime(po["po_date"], errors="coerce").dt.year
        prefix = po["po_id"].astype(str).str.extract(r"(\d{4})")[0].astype("Int64")
        mismatch = (yr != prefix).mean()
        print(f"\n  po_id year prefix disagrees with po_date on {mismatch:.1%} of rows")
        print("  -> always group by po_date; treat po_id as an opaque label.")


def check_returns(cr: pd.DataFrame, po: pd.DataFrame) -> None:
    head("6. RETURNS  -- the 35% criterion")
    n = len(cr)
    if "supplier_id_traced" not in cr.columns:
        print("  No supplier_id_traced column.")
        return
    labelled = cr["supplier_id_traced"].notna().sum()
    blank = n - labelled
    print(f"  total returns          : {n:>5,}")
    print(f"  supplier recorded      : {labelled:>5,}  ({labelled / n:.1%})  <- train + test on these")
    print(f"  supplier blank         : {blank:>5,}  ({blank / n:.1%})  <- must be inferred")

    if blank < config.MIN_LABELLED_FOR_TRAINING:
        print("\n  Note: very few blanks -- inference is nearly trivial here.")
    if labelled < config.MIN_LABELLED_FOR_TRAINING:
        print("\n  WARNING: too few labels to train. Pipeline will use the "
              "most-recent-batch rule.")
    elif labelled < config.LOW_CONFIDENCE_LABELLED:
        print("\n  WARNING: small training set -- results will be flagged low-confidence.")

    print(f"\n  returns carry po_id?   : {'po_id' in cr.columns}")
    unknown = ~cr["material_id"].isin(po["material_id"].unique())
    print(f"  material never purchased: {unknown.sum()} returns -> unattributable floor")

    if "reason" in cr.columns:
        print("\n  reason vocabulary:")
        print(cr["reason"].value_counts().head(12).to_string())


def check_days_late(pay: pd.DataFrame) -> None:
    head("7. days_late  -- does the supplied column reconcile?")
    need = {"invoice_date", "agreed_payment_days", "actual_payment_date", "days_late"}
    if not need <= set(pay.columns):
        print(f"  Missing columns: {sorted(need - set(pay.columns))}")
        return
    inv = pd.to_datetime(pay["invoice_date"], errors="coerce")
    act = pd.to_datetime(pay["actual_payment_date"], errors="coerce")
    due = inv + pd.to_timedelta(pay["agreed_payment_days"], unit="D")
    computed = (act - due).dt.days
    diff = (computed - pay["days_late"]).abs()
    print(f"  rows where supplied == recomputed : {(diff == 0).mean():.1%}")
    print(f"  mean absolute difference          : {diff.mean():.2f} days")
    if (diff > 0).any():
        print("\n  -> recompute from dates; report both, note the discrepancy.")


def check_keys(frames: dict[str, pd.DataFrame]) -> None:
    head("8. KEYS AND JOINS")
    po, gr = frames.get("purchase_orders"), frames.get("goods_receipts")
    if po is not None:
        print(f"  po_id unique in purchase_orders : {po['po_id'].is_unique}")
    if gr is not None:
        print(f"  po_id unique in goods_receipts  : {gr['po_id'].is_unique}")
        per = gr.groupby("po_id").size()
        print(f"  receipts per PO                 : min {per.min()} max {per.max()}")
    if po is not None and gr is not None:
        print(f"  POs with no receipt             : {(~po['po_id'].isin(gr['po_id'])).sum()}")

    sm = frames.get("supplier_master")
    if po is not None and sm is not None:
        in_po = set(po["supplier_id"].unique())
        in_sm = set(sm["supplier_id"].unique())
        print(f"\n  suppliers in master             : {len(in_sm)}")
        print(f"  suppliers transacting           : {len(in_po)}")
        print(f"  in POs but not in master        : {sorted(in_po - in_sm) or 'none'}")
        print(f"  in master but never transacted  : {sorted(in_sm - in_po) or 'none'}")


def check_nulls(frames: dict[str, pd.DataFrame]) -> None:
    head("9. NULLS")
    for name, df in frames.items():
        nulls = df.isna().sum()
        nulls = nulls[nulls > 0]
        if nulls.empty:
            print(f"  {name:<22} clean")
        else:
            print(f"  {name:<22} " + ", ".join(
                f"{c}={v} ({v / len(df):.0%})" for c, v in nulls.items()))


def check_label(sm: pd.DataFrame) -> None:
    head("10. THE ANSWER KEY")
    if config.LABEL_COLUMN not in sm.columns:
        print(f"  No `{config.LABEL_COLUMN}` column present.")
        return
    flagged = sm.loc[sm[config.LABEL_COLUMN].astype(str).str.lower().isin(
        ["true", "1", "yes"]), "supplier_id"].tolist()
    print(f"  `{config.LABEL_COLUMN}` found, flagging {len(flagged)} suppliers: {flagged}")
    print("\n  This column is dropped at load time and never enters scoring.")
    print("  It is re-read only at the end, to check whether our independent")
    print("  ranking put the same suppliers at the bottom.")


def main() -> None:
    frames = discover()
    get = frames.get

    if get("purchase_orders") is not None:
        check_units(frames["purchase_orders"])
    if get("goods_receipts") is not None:
        check_grades(frames["goods_receipts"])
    if all(get(k) is not None for k in
           ("purchase_orders", "market_price_index", "supplier_master")):
        check_materials(frames["purchase_orders"], frames["market_price_index"],
                        frames["supplier_master"])
    if all(get(k) is not None for k in ("purchase_orders", "goods_receipts")):
        check_identity(frames["purchase_orders"], frames["goods_receipts"])
    check_dates(frames)
    if all(get(k) is not None for k in ("customer_returns", "purchase_orders")):
        check_returns(frames["customer_returns"], frames["purchase_orders"])
    if get("payment_records") is not None:
        check_days_late(frames["payment_records"])
    check_keys(frames)
    check_nulls(frames)
    if get("supplier_master") is not None:
        check_label(frames["supplier_master"])

    print(f"\n{RULE}\n  Pre-flight complete.\n{RULE}")


if __name__ == "__main__":
    main()
