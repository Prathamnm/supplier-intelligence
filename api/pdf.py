"""Print an A4 HTML page to PDF, on demand, for uploaded analyses.

The pipeline writes every brief and the approach document as print-ready
HTML. Making the PDFs during the analysis would add a browser start per
file to every upload, so the API prints each one only when it is first
asked for, then keeps it.

Printing uses Playwright's Chromium when it is installed (the hosted API
downloads it at build time, see render.yaml), otherwise a local Edge or
Chrome. Only one print runs at a time: a browser is the largest thing in
memory on a small instance.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("supplier-intelligence.api")
_one_at_a_time = threading.Lock()
# Why the last print failed, reported by /api/health so a hosting problem is visible.
last_error: str | None = None


def html_to_pdf(html: Path, pdf: Path) -> bool:
    """Write `pdf` from `html`; True on success. Never raises."""
    with _one_at_a_time:
        if pdf.exists():  # printed by an earlier request while this one waited
            return True
        tmp = pdf.with_suffix(".tmp.pdf")
        try:
            if _playwright(html, tmp) or _local_browser(html, tmp):
                os.replace(tmp, pdf)
                _set_error(None)
                return True
            return False
        finally:
            tmp.unlink(missing_ok=True)


def _playwright(html: Path, out: Path) -> bool:
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        _set_error("playwright is not installed")
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page()
                page.goto(html.resolve().as_uri(), wait_until="load")
                # The templates set their own A4 size and margins with @page.
                page.pdf(path=str(out), prefer_css_page_size=True, print_background=True)
            finally:
                browser.close()
        return out.exists() and out.stat().st_size > 0
    except Error as e:
        _set_error(" ".join(str(e).split())[:400])
        log.warning("Playwright could not print %s: %s", html.name, last_error)
        return False


def _set_error(message: str | None) -> None:
    global last_error
    last_error = message


def _local_browser(html: Path, out: Path) -> bool:
    from pipeline import brief

    browser = brief._browser()
    return bool(browser) and brief._to_pdf(html, out, browser)
