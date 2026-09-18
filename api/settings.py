"""Runtime settings for the API, read once from the environment."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _env_list(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    # Where each analysis gets its own working folder.
    data_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("SI_DATA_DIR", Path(tempfile.gettempdir()) / "supplier-intelligence")))
    max_file_mb: int = int(os.environ.get("SI_MAX_FILE_MB", "25"))
    max_files: int = int(os.environ.get("SI_MAX_FILES", "10"))
    # Old analyses are deleted after this long, or once there are more than max_analyses.
    ttl_minutes: int = int(os.environ.get("SI_TTL_MINUTES", "180"))
    max_analyses: int = int(os.environ.get("SI_MAX_ANALYSES", "25"))
    # Concurrent pipeline runs; each is CPU-bound for a few seconds.
    max_concurrent_runs: int = int(os.environ.get("SI_MAX_CONCURRENT_RUNS", "2"))
    # PDF printing needs a local Chromium and adds ~2 s per brief. Off by
    # default: every brief also ships as an A4 HTML page the browser can print.
    pdf: bool = os.environ.get("SI_PDF", "0") == "1"
    cors_origins: list[str] = field(default_factory=lambda: _env_list(
        "SI_CORS_ORIGINS", "http://localhost:5173,http://localhost:4173"))
