from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpenSolutionRequest:
    solution_or_project_path: Path


@dataclass(frozen=True)
class TextDocumentPositionRequest:
    file_path: Path
    line: int
    character: int


@dataclass(frozen=True)
class FindReferencesRequest:
    file_path: Path
    line: int
    character: int
    include_declaration: bool = True


@dataclass(frozen=True)
class SearchSymbolsRequest:
    query: str


@dataclass(frozen=True)
class ReadSpanRequest:
    file_path: Path
    start_line: int
    start_character: int
    end_line: int
    end_character: int
