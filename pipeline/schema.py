"""Which columns identify each source file.

Kept free of heavy imports: the upload API serves these the moment it
starts, and the web app checks files against them in the browser.
"""

from __future__ import annotations

from collections.abc import Iterable

SIGNATURES: dict[str, set[str]] = {
    "purchase_orders": {"po_id", "supplier_id", "quantity_ordered", "unit_price_quoted"},
    "goods_receipts": {"gr_id", "po_id", "quantity_received", "invoice_amount_billed"},
    "customer_returns": {"return_id", "return_date", "quantity_returned"},
    "market_price_index": {"month", "material_category", "market_price_per_mt"},
    "payment_records": {"po_id", "actual_payment_date", "agreed_payment_days"},
    "supplier_master": {"supplier_id", "supplier_name", "material_categories"},
}


# Used only for context (never for scoring), and few businesses keep one.
OPTIONAL: frozenset[str] = frozenset({"market_price_index"})


def sniff_delimiter(header: str) -> str:
    """Comma, semicolon (European Excel) or tab: whichever splits the header row most."""
    return max((",", ";", "\t"), key=header.count)


def identify(columns: Iterable[str]) -> str | None:
    """The first file type whose identifying columns are all present."""
    cols = {str(c).strip() for c in columns}
    for name, required in SIGNATURES.items():
        if required <= cols:
            return name
    return None
