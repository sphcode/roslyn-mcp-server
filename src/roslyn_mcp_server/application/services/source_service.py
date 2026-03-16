from pathlib import Path

from roslyn_mcp_server.application.models.requests import ReadSpanRequest
from roslyn_mcp_server.application.models.results import SourceSpanResult


class SourceService:
    def read_span(self, request: ReadSpanRequest):
        file_path = Path(request.file_path).resolve()
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        if request.start_line < 0 or request.end_line < request.start_line:
            raise ValueError("Invalid span line range")
        if request.end_line >= len(lines):
            raise ValueError("Span end_line is out of range")

        if request.start_line == request.end_line:
            text = lines[request.start_line][request.start_character:request.end_character]
        else:
            parts = [lines[request.start_line][request.start_character:]]
            parts.extend(lines[request.start_line + 1 : request.end_line])
            parts.append(lines[request.end_line][: request.end_character])
            text = "".join(parts)

        return SourceSpanResult(file_path=file_path, text=text)
