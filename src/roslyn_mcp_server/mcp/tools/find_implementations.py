from pathlib import Path

from roslyn_mcp_server.application.models.requests import TextDocumentPositionRequest
from roslyn_mcp_server.roslyn.translators import normalize_lsp_locations


def handle(workspace_service, navigation_service, payload):
    workspace_service.ensure_navigation_ready()
    request = TextDocumentPositionRequest(
        file_path=Path(payload["file_path"]),
        line=int(payload["line"]),
        character=int(payload["character"]),
    )
    result = navigation_service.find_implementations(request)
    locations = normalize_lsp_locations(result.locations)
    return {
        "query": {
            "file_path": str(request.file_path),
            "line": request.line,
            "character": request.character,
        },
        "count": len(locations),
        "locations": locations,
    }
