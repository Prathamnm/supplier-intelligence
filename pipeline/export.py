"""Stage 07 -- write the results the web app and reviewers read.

Plain JSON, one file per concern. The web app imports these at build
time, so the deployed site does no computation at all. A copy of every
table also goes to output/ as CSV for anyone who wants to check the
numbers in a spreadsheet.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def _clean(obj):
    """Make anything pandas/numpy produces JSON-safe. NaN/inf -> null."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return round(f, 4) if math.isfinite(f) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime("%Y-%m-%d") if not pd.isna(obj) else None
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if obj is pd.NaT:
        return None
    return obj


def records(df: pd.DataFrame, cols: list[str] | None = None) -> list[dict]:
    d = df[cols] if cols else df
    return _clean(d.to_dict(orient="records"))


def write_json(path: Path, payload) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_clean(payload), ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for col in out.columns:
        if out[col].map(lambda v: isinstance(v, (list, dict))).any():
            out[col] = out[col].map(lambda v: json.dumps(_clean(v)))
    out.to_csv(path, index=False)
