from pathlib import Path

from roslyn_mcp_server.application.models.requests import ReadSpanRequest


def handle(source_service, payload):
    request = ReadSpanRequest(
        file_path=Path(payload["file_path"]),
        start_line=int(payload["start_line"]),
        start_character=int(payload["start_character"]),
        end_line=int(payload["end_line"]),
        end_character=int(payload["end_character"]),
    )
    result = source_service.read_span(request)
    return {
        "file_path": str(result.file_path),
        "range": {
            "start": {
                "line": request.start_line,
                "character": request.start_character,
            },
            "end": {
                "line": request.end_line,
                "character": request.end_character,
            },
        },
        "text": result.text,
    }
