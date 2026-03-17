from roslyn_mcp_server.application.models.requests import (
    FindReferencesRequest,
    SearchSymbolsRequest,
    TextDocumentRequest,
    TextDocumentPositionRequest,
)
from roslyn_mcp_server.application.models.results import NavigationResult


class NavigationService:
    def __init__(self, session):
        self.session = session

    def find_definition(self, request: TextDocumentPositionRequest):
        locations = self.session.definition(
            file_path=request.file_path,
            line=request.line,
            character=request.character,
        )
        return NavigationResult(locations=locations)

    def find_references(self, request: FindReferencesRequest):
        locations = self.session.references(
            file_path=request.file_path,
            line=request.line,
            character=request.character,
            include_declaration=request.include_declaration,
        )
        return NavigationResult(locations=locations)

    def find_implementations(self, request: TextDocumentPositionRequest):
        locations = self.session.implementations(
            file_path=request.file_path,
            line=request.line,
            character=request.character,
        )
        return NavigationResult(locations=locations)

    def document_symbols(self, request: TextDocumentRequest):
        locations = self.session.document_symbols(file_path=request.file_path)
        return NavigationResult(locations=locations)

    def search_symbols(self, request: SearchSymbolsRequest):
        locations = self.session.search_symbols(query=request.query)
        return NavigationResult(locations=locations)
