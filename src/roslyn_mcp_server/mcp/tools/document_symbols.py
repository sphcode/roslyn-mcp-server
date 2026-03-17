from pathlib import Path

from roslyn_mcp_server.application.models.requests import TextDocumentRequest
from roslyn_mcp_server.roslyn.translators import normalize_document_symbols


def handle(workspace_service, navigation_service, payload):
    workspace_service.ensure_navigation_ready()
    request = TextDocumentRequest(file_path=Path(payload["file_path"]))
    result = navigation_service.document_symbols(request)
    symbols = normalize_document_symbols(result.locations)
    return {
        "query": {
            "file_path": str(request.file_path),
        },
        "count": len(symbols),
        "symbols": symbols,
    }
