from pathlib import Path

from roslyn_mcp_server.application.models.requests import TextDocumentPositionRequest


def handle(navigation_service, payload):
    request = TextDocumentPositionRequest(
        file_path=Path(payload["file_path"]),
        line=int(payload["line"]),
        character=int(payload["character"]),
    )
    result = navigation_service.find_definition(request)
    return {
        "result": result.locations,
    }
