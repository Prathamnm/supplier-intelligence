"""HTTP API: upload CSVs, run the pipeline, serve the results.

    uvicorn api.main:app --reload            # http://localhost:8000/docs

The API adds no analysis of its own. It runs the same pipeline.run() the
command line does, in a fresh folder per upload, and serves the JSON and
briefs it writes -- the same files, in the same shapes, the web app
already reads for the built-in dataset.

Start-up is kept deliberately light. pandas, scikit-learn and SciPy take
seconds to import -- a minute or more on a small hosted instance -- so
they are loaded in a background thread after the server is listening,
never at import time. Health checks and the file rules answer at once;
the first analysis waits only if the warm-up hasn't finished.
"""

from __future__ import annotations

import csv
import importlib
import logging
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.settings import Settings
from api.store import AnalysisStore
from evaluation.scenarios import SCENARIOS
from pipeline import schema as file_schema

log = logging.getLogger("supplier-intelligence.api")

DATA_FILES = {"summary.json", "suppliers.json", "supplier_details.json",
              "returns.json", "briefs.json", "quality.json"}
BRIEF_FILE = re.compile(r"^[A-Za-z0-9_-]{1,64}\.(html|pdf)$")
CHUNK = 1 << 20

# The heavy half of the app, imported once, off the request path.
_HEAVY = ("pipeline.run", "pipeline.quality", "evaluation.generate")
_warm = threading.Event()


def _warm_up() -> None:
    """Import the analysis code so the first upload doesn't pay for it."""
    try:
        for module in _HEAVY:
            importlib.import_module(module)
    finally:
        _warm.set()


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = AnalysisStore(settings.data_dir, settings.ttl_minutes, settings.max_analyses)
    runs = threading.BoundedSemaphore(settings.max_concurrent_runs)

    app = FastAPI(title="Supplier Intelligence API", version="1.0.0", lifespan=_lifespan,
                  description="Upload the six CSVs, get the scorecard, rupee impact, "
                              "return attribution and negotiation briefs.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    # -------------------------------------------------------------- helpers

    def _analyse(path: Path, meta: dict) -> dict:
        """Run the pipeline in `path`; record and return the outcome."""
        if not runs.acquire(timeout=120):
            store.discard(path)
            raise HTTPException(503, "The server is busy with other analyses. Try again shortly.")
        # Normally already imported by the warm-up thread; if not, Python's import
        # lock makes this wait for it rather than import twice.
        from pipeline.quality import PipelineError
        from pipeline.run import run as run_pipeline
        try:
            summary = run_pipeline(path / "raw", pdf=settings.pdf, web=False, out=path / "out")
        except PipelineError as e:
            store.discard(path)
            raise HTTPException(422, str(e)) from e
        except Exception as e:  # a bug, not bad input: log it, don't leak internals
            log.exception("Pipeline failed")
            store.discard(path)
            raise HTTPException(500, "The analysis failed unexpectedly. The error has been logged.") from e
        finally:
            runs.release()

        meta.update(status="done", completed=_now(), runtime_s=summary.get("runtime_s"),
                    headline={"suppliers": summary["counts"]["suppliers"],
                              "orders": summary["counts"]["orders"],
                              "bottom": summary["bottom"]["suppliers"],
                              "warnings": summary["quality"]["warnings"]})
        store.write_meta(path, meta)
        return meta

    def _folder(analysis_id: str) -> Path:
        path = store.path(analysis_id)
        if path is None:
            raise HTTPException(404, "No such analysis. It may have expired; upload the files again.")
        return path

    # ---------------------------------------------------------------- routes

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": app.version, "ready": _warm.is_set()}

    @app.get("/api/schema")
    def schema() -> dict:
        """The columns that identify each required file -- the pipeline's own rules,
        so the upload page checks files exactly as the backend will."""
        return {"files": {name: sorted(cols) for name, cols in file_schema.SIGNATURES.items()},
                "max_file_mb": settings.max_file_mb, "max_files": settings.max_files}

    @app.post("/api/analyses", status_code=201)
    def create_analysis(files: list[UploadFile] = File(...)) -> dict:  # noqa: B008 -- FastAPI idiom
        if not files:
            raise HTTPException(400, "No files received.")
        if len(files) > settings.max_files:
            raise HTTPException(400, f"At most {settings.max_files} files per analysis.")

        analysis_id, path = store.create()
        limit = settings.max_file_mb * CHUNK
        received = []
        try:
            for i, f in enumerate(files):
                name = Path(f.filename or f"file{i}").name
                if not name.lower().endswith(".csv"):
                    raise HTTPException(400, f"{name}: only .csv files are accepted.")
                # Saved under our own name; the original is kept only for display.
                target = path / "raw" / f"upload_{i:02d}.csv"
                size = 0
                with target.open("wb") as out:
                    while chunk := f.file.read(CHUNK):
                        size += len(chunk)
                        if size > limit:
                            raise HTTPException(413, f"{name} is larger than {settings.max_file_mb} MB.")
                        out.write(chunk)
                received.append({"name": name, "bytes": size, "detected_as": _identify(target)})
        except HTTPException:
            store.discard(path)
            raise

        meta = {"id": analysis_id, "source": "upload", "created": _now(), "status": "running",
                "files": received}
        store.write_meta(path, meta)
        return _analyse(path, meta)

    @app.get("/api/samples")
    def samples() -> list[dict]:
        return [{"name": s.name, "title": s.title, "purpose": s.purpose,
                 "suppliers": s.n_suppliers, "orders": s.n_orders} for s in SCENARIOS]

    @app.post("/api/samples/{name}", status_code=201)
    def analyse_sample(name: str) -> dict:
        """Generate a synthetic dataset (evaluation/) and analyse it -- for trying
        the app without your own files."""
        scenario = next((s for s in SCENARIOS if s.name == name), None)
        if scenario is None:
            raise HTTPException(404, f"No sample named {name!r}.")
        from evaluation.generate import generate
        analysis_id, path = store.create()
        generate(scenario, path)          # writes path/raw/*.csv and path/truth.json
        (path / "truth.json").unlink(missing_ok=True)
        meta = {"id": analysis_id, "source": "sample", "sample": scenario.title, "created": _now(),
                "status": "running",
                "files": [{"name": p.name, "bytes": p.stat().st_size, "detected_as": _identify(p)}
                          for p in sorted((path / "raw").glob("*.csv"))]}
        store.write_meta(path, meta)
        return _analyse(path, meta)

    @app.get("/api/analyses/{analysis_id}")
    def get_analysis(analysis_id: str) -> dict:
        return store.read_meta(_folder(analysis_id))

    @app.get("/api/analyses/{analysis_id}/data/{name}")
    def get_data(analysis_id: str, name: str) -> FileResponse:
        if name not in DATA_FILES:
            raise HTTPException(404, "Unknown data file.")
        file = _folder(analysis_id) / "out" / "data" / name
        if not file.exists():
            raise HTTPException(404, "Not available for this analysis.")
        return FileResponse(file, media_type="application/json")

    @app.get("/api/analyses/{analysis_id}/briefs/{file}")
    def get_brief(analysis_id: str, file: str) -> FileResponse:
        if not BRIEF_FILE.match(file):
            raise HTTPException(404, "Unknown brief.")
        path = _folder(analysis_id) / "out" / "briefs" / file
        if not path.exists():
            raise HTTPException(404, "Unknown brief.")
        return FileResponse(path, media_type="application/pdf" if file.endswith(".pdf") else "text/html")

    @app.get("/api/analyses/{analysis_id}/approach")
    def get_approach(analysis_id: str) -> FileResponse:
        path = _folder(analysis_id) / "out" / "approach.html"
        if not path.exists():
            raise HTTPException(404, "Not available for this analysis.")
        return FileResponse(path, media_type="text/html")

    return app


def _identify(csv_path: Path) -> str | None:
    """Which required file this is, judged from its header row alone."""
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            return file_schema.identify(next(csv.reader(f), []))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


app = create_app()
