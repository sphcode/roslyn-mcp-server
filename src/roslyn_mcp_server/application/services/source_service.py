from pathlib import Path

from roslyn_mcp_server.application.models.requests import ReadSpanRequest
from roslyn_mcp_server.application.models.results import SourceSpanResult


class SourceService:
    def read_span(self, request: ReadSpanRequest) -> SourceSpanResult:
        file_path = Path(request.file_path).resolve()
        lines = file_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            lines = [""]

        start_line, start_character = self._clamp_position(
            lines,
            request.start_line,
            request.start_character,
        )
        end_line, end_character = self._clamp_position(
            lines,
            request.end_line,
            request.end_character,
        )

        if (end_line, end_character) < (start_line, start_character):
            end_line = start_line
            end_character = start_character

        text = self._slice_text(
            lines,
            start_line,
            start_character,
            end_line,
            end_character,
        )

        return SourceSpanResult(
            file_path=file_path,
            start_line=start_line,
            start_character=start_character,
            end_line=end_line,
            end_character=end_character,
            text=text,
        )

    @staticmethod
    def _clamp_position(lines, line, character):
        last_line_index = len(lines) - 1
        clamped_line = min(max(line, 0), last_line_index)
        line_length = len(lines[clamped_line])
        clamped_character = min(max(character, 0), line_length)
        return clamped_line, clamped_character

    @staticmethod
    def _slice_text(lines, start_line, start_character, end_line, end_character):
        if start_line == end_line:
            return lines[start_line][start_character:end_character]

        parts = [lines[start_line][start_character:]]
        parts.extend(lines[start_line + 1 : end_line])
        parts.append(lines[end_line][:end_character])
        return "\n".join(parts)
