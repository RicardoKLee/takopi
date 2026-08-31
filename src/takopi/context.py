from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunContext:
    project: str | None = None
    branch: str | None = None
    path: Path | None = None
