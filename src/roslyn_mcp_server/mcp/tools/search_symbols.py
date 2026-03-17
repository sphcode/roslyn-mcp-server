from roslyn_mcp_server.application.models.requests import SearchSymbolsRequest
from roslyn_mcp_server.roslyn.translators import normalize_workspace_symbols


def handle(workspace_service, navigation_service, payload):
    workspace_service.ensure_navigation_ready()
    request = SearchSymbolsRequest(query=str(payload["query"]))
    result = navigation_service.search_symbols(request)
    symbols = normalize_workspace_symbols(result.locations)
    return {
        "query": request.query,
        "count": len(symbols),
        "symbols": symbols,
    }
