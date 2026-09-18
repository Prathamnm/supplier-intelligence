"""The pipeline <-> web app contract.

The React app declares the JSON it expects in web/src/lib/types.ts. These
tests read those interfaces and check every required field is present in
what the pipeline writes -- both a fresh run and the committed copy the
site is actually built from. A renamed column fails here, not as a blank
cell on the deployed site.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline import config
from pipeline.run import run

TYPES = config.WEB / "src" / "lib" / "types.ts"


def interface_fields(name: str) -> set[str]:
    """Required top-level fields of a TypeScript interface."""
    src = TYPES.read_text(encoding="utf-8")
    m = re.search(rf"export interface {name} \{{\n(.*?)\n\}}", src, re.S)
    assert m, f"interface {name} not found in {TYPES}"
    return set(re.findall(r"^  (\w+):", m.group(1), re.M))  # `field?:` is optional


# (interface, how to reach the matching JSON objects in a data directory)
CONTRACT = {
    "Summary": lambda d: [_load(d, "summary.json")],
    "Supplier": lambda d: _load(d, "suppliers.json"),
    "CategoryRow": lambda d: [c for v in _load(d, "supplier_details.json").values() for c in v["categories"]],
    "YearRow": lambda d: [y for v in _load(d, "supplier_details.json").values() for y in v["years"]],
    "ReturnRow": lambda d: _load(d, "returns.json"),
    "Brief": lambda d: _load(d, "briefs.json"),
    "QualityReport": lambda d: [_load(d, "quality.json")],
    "Finding": lambda d: _load(d, "quality.json")["findings"],
}


def _load(d: Path, name: str):
    return json.loads((d / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh(tmp_path_factory) -> Path:
    if not any(config.RAW.glob("*.csv")):
        pytest.skip("source CSVs not present")
    out = tmp_path_factory.mktemp("out")
    run(pdf=False, web=False, out=out)
    return out / "data"


def _same(a, b, path: str = "") -> str | None:
    """First difference between two JSON values, with float tolerance.

    Tolerant because the last rounded digit can differ across platforms'
    floating-point libraries; any real change in the analysis is far larger.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return f"{path}: keys differ {sorted(a.keys() ^ b.keys())}"
        return next((d for k in a if (d := _same(a[k], b[k], f"{path}.{k}"))), None)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} vs {len(b)}"
        return next((d for i, (x, y) in enumerate(zip(a, b, strict=True))
                     if (d := _same(x, y, f"{path}[{i}]"))), None)
    if isinstance(a, float | int) and isinstance(b, float | int) and not isinstance(a, bool):
        return None if abs(a - b) <= 1e-3 + 1e-6 * abs(b) else f"{path}: {a} vs {b}"
    return None if a == b else f"{path}: {a!r} vs {b!r}"


def _check(data_dir: Path) -> None:
    for iface, get in CONTRACT.items():
        required = interface_fields(iface)
        rows = get(data_dir)
        assert rows, f"{iface}: no records"
        for i, row in enumerate(rows):
            missing = required - set(row)
            assert not missing, f"{iface}[{i}] missing {sorted(missing)}"


def test_fresh_pipeline_output_satisfies_web_contract(fresh):
    _check(fresh)


def test_committed_web_data_satisfies_contract():
    if not (config.WEB_DATA / "summary.json").exists():
        pytest.skip("web data not generated yet")
    _check(config.WEB_DATA)


def test_committed_web_data_is_current(fresh):
    """The site must be built from the latest analysis, not a stale copy."""
    if not (config.WEB_DATA / "summary.json").exists():
        pytest.skip("web data not generated yet")
    for name in ("suppliers.json", "returns.json", "supplier_details.json"):
        diff = _same(_load(fresh, name), _load(config.WEB_DATA, name))
        assert diff is None, f"web/src/data/{name} is stale ({diff}) -- rerun `python -m pipeline.run`"


def test_every_brief_links_to_a_file_that_exists():
    if not (config.WEB_DATA / "briefs.json").exists():
        pytest.skip("web data not generated yet")
    for b in _load(config.WEB_DATA, "briefs.json"):
        for kind in ("html", "pdf"):
            if kind in b["files"]:
                assert (config.WEB_BRIEFS / b["files"][kind]).exists(), b["files"][kind]
