from roslyn_mcp_server.application.models.requests import SearchSymbolsRequest


def handle(navigation_service, payload):
    request = SearchSymbolsRequest(query=str(payload["query"]))
    result = navigation_service.search_symbols(request)
    return {
        "result": result.locations,
    }
