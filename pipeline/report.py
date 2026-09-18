"""The approach document -- generated, so its numbers can never drift.

Renders templates/approach.html.j2 from the same objects the web app
reads, then prints it to PDF with the same headless browser the briefs
use. Every figure in the write-up is therefore the figure the pipeline
just computed.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline import brief, config


def _pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{x * 100:.{digits}f}%"


def render(summary: dict, suppliers: list[dict], briefs: list[dict], quality: dict,
           out_dir: Path, pdf: bool = True) -> dict:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters.update(inr=brief.inr, lakh=brief.lakh, pct=_pct)
    html = env.get_template("approach.html.j2").render(
        s=summary, suppliers=sorted(suppliers, key=lambda r: r["rank"], reverse=True),
        briefs=briefs, quality=quality, cfg=config)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "approach.html"
    html_path.write_text(html, encoding="utf-8")
    files = {"html": html_path.name}
    browser = brief._browser() if pdf else None
    if browser and brief._to_pdf(html_path, out_dir / "approach.pdf", browser):
        files["pdf"] = "approach.pdf"
    return files
