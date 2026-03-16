from pathlib import Path

from roslyn_mcp_server.application.models.requests import FindReferencesRequest


def handle(navigation_service, payload):
    request = FindReferencesRequest(
        file_path=Path(payload["file_path"]),
        line=int(payload["line"]),
        character=int(payload["character"]),
        include_declaration=bool(payload.get("include_declaration", True)),
    )
    result = navigation_service.find_references(request)
    return {
        "result": result.locations,
    }
