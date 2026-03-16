from pathlib import Path

from roslyn_mcp_server.application.models.requests import FindReferencesRequest
from roslyn_mcp_server.roslyn.translators import normalize_lsp_locations


def handle(workspace_service, navigation_service, payload):
    workspace_service.ensure_navigation_ready()
    request = FindReferencesRequest(
        file_path=Path(payload["file_path"]),
        line=int(payload["line"]),
        character=int(payload["character"]),
        include_declaration=bool(payload.get("include_declaration", True)),
    )
    result = navigation_service.find_references(request)
    locations = normalize_lsp_locations(result.locations)
    return {
        "query": {
            "file_path": str(request.file_path),
            "line": request.line,
            "character": request.character,
            "include_declaration": request.include_declaration,
        },
        "count": len(locations),
        "locations": locations,
    }
