from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkspaceStatusResult:
    workspace: Path
    status: str
    last_error: str | None = None


@dataclass(frozen=True)
class NavigationResult:
    locations: Any


@dataclass(frozen=True)
class SourceSpanResult:
    file_path: Path
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    text: str
