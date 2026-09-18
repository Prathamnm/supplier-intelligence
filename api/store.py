"""One folder per analysis, with bounded lifetime and count.

    <data_dir>/<id>/raw/        the uploaded CSVs, under our own names
    <data_dir>/<id>/out/        everything pipeline.run() writes
    <data_dir>/<id>/meta.json   what was uploaded, when, and the outcome
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class AnalysisStore:
    def __init__(self, root: Path, ttl_minutes: int, max_analyses: int) -> None:
        self.root = root
        self.ttl_s = ttl_minutes * 60
        self.max_analyses = max_analyses
        self._lock = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)

    def create(self) -> tuple[str, Path]:
        self.prune()
        analysis_id = uuid.uuid4().hex
        path = self.root / analysis_id
        (path / "raw").mkdir(parents=True)
        return analysis_id, path

    def path(self, analysis_id: str) -> Path | None:
        """The folder for an id, or None. Ids are validated, never joined raw."""
        if not ID_PATTERN.match(analysis_id):
            return None
        path = self.root / analysis_id
        return path if (path / "meta.json").exists() else None

    def write_meta(self, path: Path, meta: dict) -> None:
        (path / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

    def read_meta(self, path: Path) -> dict:
        return json.loads((path / "meta.json").read_text(encoding="utf-8"))

    def discard(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    def prune(self) -> None:
        """Drop expired analyses, then the oldest beyond the cap."""
        with self._lock:
            now = time.time()
            folders = sorted((p for p in self.root.iterdir() if p.is_dir()),
                             key=lambda p: p.stat().st_mtime)
            keep = []
            for p in folders:
                if now - p.stat().st_mtime > self.ttl_s:
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    keep.append(p)
            for p in keep[: max(len(keep) - self.max_analyses + 1, 0)]:
                shutil.rmtree(p, ignore_errors=True)
