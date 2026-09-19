"""The upload API, end to end through HTTP."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings
from pipeline import config
from tests.conftest import make_synthetic
from tests.test_contract import CONTRACT, _check


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path / "store", max_file_mb=5)))


def _upload(client: TestClient, folder: Path):
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(folder.glob("*.csv"))]
    return client.post("/api/analyses", files=files)


def test_health_and_schema(client):
    assert client.get("/api/health").json()["status"] == "ok"
    schema = client.get("/api/schema").json()
    assert set(schema["files"]) == {"purchase_orders", "goods_receipts", "customer_returns",
                                    "market_price_index", "payment_records", "supplier_master"}


def test_upload_runs_pipeline_and_serves_web_ready_results(client, tmp_path):
    raw = make_synthetic(tmp_path / "raw")
    r = _upload(client, raw)
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["status"] == "done"
    assert all(f["detected_as"] for f in meta["files"])      # every file recognised by its columns
    assert set(meta["headline"]["bottom"]) >= {"SUP-001", "SUP-004"}

    # Every data file the web app reads is served, and satisfies its contract.
    download = tmp_path / "downloaded"
    download.mkdir()
    for name in ("summary.json", "suppliers.json", "supplier_details.json", "returns.json",
                 "briefs.json", "quality.json"):
        res = client.get(f"/api/analyses/{meta['id']}/data/{name}")
        assert res.status_code == 200, name
        (download / name).write_bytes(res.content)
    assert CONTRACT
    _check(download)

    brief = client.get(f"/api/analyses/{meta['id']}/data/briefs.json").json()[0]
    page = client.get(f"/api/analyses/{meta['id']}/briefs/{brief['files']['html']}")
    assert page.status_code == 200 and "Negotiation brief" in page.text


def test_real_assignment_files_upload(client):
    if not any(config.RAW.glob("*.csv")):
        pytest.skip("source CSVs not present")
    meta = _upload(client, config.RAW).json()
    assert sorted(meta["headline"]["bottom"]) == ["VS03", "VS12", "VS19"]


def test_missing_file_is_a_clear_422(client, tmp_path):
    raw = make_synthetic(tmp_path / "raw")
    (raw / "rets.csv").unlink()
    r = _upload(client, raw)
    assert r.status_code == 422
    assert "customer_returns" in r.json()["detail"]


@pytest.mark.parametrize("name,body,status", [
    pytest.param("notes.txt", b"hello", 400, id="wrong-type"),
    pytest.param("big.csv", b"a,b\n" + b"1,2\n" * 2_000_000, 413, id="over-size-limit"),
])
def test_rejects_bad_uploads(client, name, body, status):
    assert client.post("/api/analyses", files=[("files", (name, body, "text/csv"))]).status_code == status


@pytest.mark.parametrize("url", [
    "/api/analyses/not-an-id",
    "/api/analyses/" + "0" * 32,
    "/api/analyses/" + "0" * 32 + "/data/summary.json",
])
def test_unknown_or_malformed_ids_are_404(client, url):
    assert client.get(url).status_code == 404


def test_cannot_escape_the_analysis_folder(client, tmp_path):
    meta = _upload(client, make_synthetic(tmp_path / "raw")).json()
    base = f"/api/analyses/{meta['id']}"
    assert client.get(f"{base}/data/..%2Fmeta.json").status_code == 404
    assert client.get(f"{base}/briefs/..%2F..%2Fmeta.json").status_code == 404
    assert client.get(f"{base}/data/truth.json").status_code == 404


def test_expired_analysis_pages_are_readable_not_json(client):
    for url in ("/briefs/VS03.html", "/briefs/VS03.pdf", "/approach", "/approach.pdf"):
        r = client.get("/api/analyses/" + "0" * 32 + url)
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("text/html")
        assert "no longer on the server" in r.text


def test_brief_pdf_is_printed_on_first_request_then_kept(client, tmp_path, monkeypatch):
    meta = _upload(client, make_synthetic(tmp_path / "raw")).json()
    base = f"/api/analyses/{meta['id']}"
    brief = client.get(f"{base}/data/briefs.json").json()[0]
    assert "pdf" not in brief["files"]          # the upload itself makes no PDFs
    calls = []

    def fake_print(html, pdf):
        calls.append(html.name)
        pdf.write_bytes(b"%PDF-1.7 fake")
        return True

    monkeypatch.setattr("api.main.html_to_pdf", fake_print)
    pdf_name = brief["files"]["html"].replace(".html", ".pdf")
    for _ in range(2):
        r = client.get(f"{base}/briefs/{pdf_name}")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert client.get(f"{base}/approach.pdf").headers["content-type"] == "application/pdf"
    assert calls == [brief["files"]["html"], "approach.html"]   # printed once each, then served


def test_pdf_failure_points_to_the_printable_page(client, tmp_path, monkeypatch):
    meta = _upload(client, make_synthetic(tmp_path / "raw")).json()
    monkeypatch.setattr("api.main.html_to_pdf", lambda html, pdf: False)
    brief = client.get(f"/api/analyses/{meta['id']}/data/briefs.json").json()[0]
    r = client.get(f"/api/analyses/{meta['id']}/briefs/{brief['files']['html'].replace('.html', '.pdf')}")
    assert r.status_code == 503 and f'href="{brief["files"]["html"]}"' in r.text


def test_printable_pages_hide_the_print_bar_when_printed(client, tmp_path):
    meta = _upload(client, make_synthetic(tmp_path / "raw")).json()
    brief = client.get(f"/api/analyses/{meta['id']}/data/briefs.json").json()[0]
    page = client.get(f"/api/analyses/{meta['id']}/briefs/{brief['files']['html']}").text
    assert "window.print()" in page and "@media print { .printbar { display: none; } }" in page


def test_real_pdf_print(tmp_path):
    from api.pdf import html_to_pdf
    from pipeline import brief

    if brief._browser() is None:
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest.skip("no browser available to print with")
    html = tmp_path / "page.html"
    html.write_text("<!doctype html><style>@page{size:A4}</style><h1>Brief</h1>", encoding="utf-8")
    ok = html_to_pdf(html, tmp_path / "page.pdf")
    if not ok:
        pytest.skip("browser present but could not print here")
    assert (tmp_path / "page.pdf").read_bytes().startswith(b"%PDF")
