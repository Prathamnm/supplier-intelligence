"""Accumulates every data-quality finding the pipeline makes.

Nothing is ever silently dropped or silently fixed. Each stage records
what it found, what it did about it, and how many rows were affected.
The result is written to site/data/quality.json and becomes the
data-quality section of the write-up.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Finding:
    stage: str
    severity: str          # info | warning | error
    title: str
    detail: str
    rows_affected: int | None = None
    action: str | None = None


@dataclass
class Quality:
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def info(self, stage: str, title: str, detail: str, **kw) -> None:
        self.findings.append(Finding(stage, "info", title, detail, **kw))

    def warn(self, stage: str, title: str, detail: str, **kw) -> None:
        self.findings.append(Finding(stage, "warning", title, detail, **kw))
        print(f"  [warn] {stage}: {title} -- {detail}")

    def error(self, stage: str, title: str, detail: str, **kw) -> None:
        self.findings.append(Finding(stage, "error", title, detail, **kw))
        print(f"  [ERROR] {stage}: {title} -- {detail}")

    def count(self, key: str, value: int) -> None:
        self.counts[key] = int(value)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    def to_dict(self) -> dict:
        return {
            "findings": [asdict(f) for f in self.findings],
            "counts": self.counts,
            "n_warnings": self.warnings,
            "n_errors": self.errors,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


class PipelineError(RuntimeError):
    """Raised when the data cannot be trusted enough to continue.

    Failing loudly in stage 01 beats producing confident nonsense in
    stage 08.
    """
