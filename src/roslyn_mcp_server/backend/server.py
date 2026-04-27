import argparse
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from roslyn_mcp_server.application.models.requests import (
    FindReferencesRequest,
    ReadSpanRequest,
    TextDocumentRequest,
    TextDocumentPositionRequest,
)
from roslyn_mcp_server.application.services.navigation_service import NavigationService
from roslyn_mcp_server.application.services.source_service import SourceService
from roslyn_mcp_server.application.services.workspace_service import (
    WorkspaceNotReadyError,
    WorkspaceService,
)
from roslyn_mcp_server.infrastructure.config import load_server_config
from roslyn_mcp_server.infrastructure.logging import configure_logging, get_logger
from roslyn_mcp_server.mcp.tools import (
    document_symbols,
    health,
    open_solution,
    search_symbols,
)
from roslyn_mcp_server.roslyn.session import RoslynSession
from roslyn_mcp_server.roslyn.translators import (
    InvalidSymbolHandleError,
    normalize_document_symbols,
    normalize_lsp_locations,
    parse_symbol_handle,
)

logger = get_logger(__name__)
MAX_READ_LINE = 1_000_000_000
MAX_READ_CHARACTER = 1_000_000_000


class BackendServer:
    def __init__(self, config):
        self.config = config
        self.session = RoslynSession(
            server_path=config["server_path"],
            solution_or_project_path=config["solution_or_project_path"],
            timeouts=config["roslyn_timeouts"],
        )
        self.workspace_service = WorkspaceService(self.session)
        self.navigation_service = NavigationService(self.session)
        self.source_service = SourceService()
        self.httpd = None

    def serve_forever(self):
        self.httpd = ThreadingHTTPServer(
            (self.config["listen_host"], self.config["listen_port"]),
            self._build_handler(),
        )
        actual_host, actual_port = self.httpd.server_address[:2]
        self.config["listen_port"] = int(actual_port)
        self._write_port_file(actual_port)
        logger.info(
            "Backend listening on http://%s:%s",
            actual_host,
            actual_port,
        )
        self.workspace_service.start()
        try:
            self.httpd.serve_forever()
        finally:
            self.close()

    def close(self):
        if self.httpd is not None:
            self.httpd.server_close()
            self.httpd = None
        self.workspace_service.close()

    def _write_port_file(self, port):
        port_file = os.environ.get("ROSLYN_MCP_BACKEND_PORT_FILE")
        if not port_file:
            return
        with open(port_file, "w", encoding="utf-8") as handle:
            handle.write(str(port))

    def find_definition_by_symbol(self, payload):
        symbol = self._parse_symbol(payload["symbol_handle"])
        self.workspace_service.ensure_navigation_ready()
        request = TextDocumentPositionRequest(
            file_path=Path(symbol["file_path"]),
            line=int(symbol["line"]),
            character=int(symbol["character"]),
        )
        result = self.navigation_service.find_definition(request)
        locations = normalize_lsp_locations(result.locations)
        return {
            "query": {"symbol_handle": payload["symbol_handle"]},
            "count": len(locations),
            "locations": locations,
        }

    def find_references_by_symbol(self, payload):
        symbol = self._parse_symbol(payload["symbol_handle"])
        include_declaration = bool(payload.get("include_declaration", True))
        self.workspace_service.ensure_navigation_ready()
        request = FindReferencesRequest(
            file_path=Path(symbol["file_path"]),
            line=int(symbol["line"]),
            character=int(symbol["character"]),
            include_declaration=include_declaration,
        )
        result = self.navigation_service.find_references(request)
        locations = normalize_lsp_locations(result.locations)
        return {
            "query": {
                "symbol_handle": payload["symbol_handle"],
                "include_declaration": include_declaration,
            },
            "count": len(locations),
            "locations": locations,
        }

    def find_implementations_by_symbol(self, payload):
        symbol = self._parse_symbol(payload["symbol_handle"])
        self.workspace_service.ensure_navigation_ready()
        request = TextDocumentPositionRequest(
            file_path=Path(symbol["file_path"]),
            line=int(symbol["line"]),
            character=int(symbol["character"]),
        )
        result = self.navigation_service.find_implementations(request)
        locations = normalize_lsp_locations(result.locations)
        return {
            "query": {"symbol_handle": payload["symbol_handle"]},
            "count": len(locations),
            "locations": locations,
        }

    def read_symbol(self, payload):
        symbol_handle = payload["symbol_handle"]
        symbol = self._parse_symbol(symbol_handle)
        include_body = bool(payload.get("include_body", True))
        context_lines = max(0, int(payload.get("context_lines", 0)))

        self.workspace_service.ensure_navigation_ready()
        document_symbols_payload = self._document_symbols_for_file(symbol["file_path"])
        matched_symbol = self._find_document_symbol(document_symbols_payload["symbols"], symbol)
        fallback_range = self._default_read_range(symbol)

        if matched_symbol is None:
            read_range = fallback_range
            resolved_symbol = {
                "symbol_handle": symbol_handle,
                "name": symbol.get("name"),
                "kind": symbol.get("kind"),
                "container_name": symbol.get("container_name"),
                "file_path": symbol.get("file_path"),
                "range": symbol.get("range"),
                "selection_range": symbol.get("selection_range"),
                "matched_from_document_symbols": False,
            }
        else:
            resolved_symbol = {
                "symbol_handle": matched_symbol.get("symbol_handle"),
                "name": matched_symbol.get("name"),
                "kind": matched_symbol.get("kind"),
                "container_name": matched_symbol.get("container_name"),
                "file_path": matched_symbol.get("file_path"),
                "range": matched_symbol.get("range"),
                "selection_range": matched_symbol.get("selection_range"),
                "matched_from_document_symbols": True,
            }
            read_range = (
                matched_symbol.get("range")
                or matched_symbol.get("selection_range")
                or fallback_range
            )

        span_payload = self._read_span_payload(
            file_path=symbol["file_path"],
            start_line=max(0, int(read_range["start"]["line"]) - context_lines),
            start_character=0 if context_lines > 0 else int(read_range["start"]["character"]),
            end_line=int(read_range["end"]["line"]) + context_lines,
            end_character=MAX_READ_CHARACTER if context_lines > 0 else int(read_range["end"]["character"]),
        )
        text = span_payload["text"]
        output_range = span_payload["range"]
        if not include_body and matched_symbol is not None:
            text, output_range = self._extract_declaration_text(
                text=text,
                base_range=span_payload["range"],
            )

        return {
            "query": {
                "symbol_handle": symbol_handle,
                "include_body": include_body,
                "context_lines": context_lines,
            },
            "resolved_symbol": resolved_symbol,
            "file_path": span_payload["file_path"],
            "range": output_range,
            "text": text,
        }

    def read_file(self, payload):
        start_line = max(0, int(payload.get("start_line", 0)))
        end_line = int(payload.get("end_line", MAX_READ_LINE))
        if end_line < start_line:
            end_line = start_line

        span_payload = self._read_span_payload(
            file_path=payload["file_path"],
            start_line=start_line,
            start_character=0,
            end_line=end_line,
            end_character=MAX_READ_CHARACTER,
        )
        span_payload["query"] = {
            "file_path": payload["file_path"],
            "start_line": start_line,
            "end_line": end_line if "end_line" in payload else None,
        }
        return span_payload

    def _parse_symbol(self, symbol_handle):
        return parse_symbol_handle(symbol_handle)

    def _document_symbols_for_file(self, file_path):
        request = TextDocumentRequest(file_path=Path(file_path))
        result = self.navigation_service.document_symbols(request)
        symbols = normalize_document_symbols(result.locations, request.file_path)
        return {
            "query": {
                "file_path": str(request.file_path),
            },
            "count": len(symbols),
            "symbols": symbols,
        }

    def _read_span_payload(
        self,
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
    ):
        request = ReadSpanRequest(
            file_path=Path(file_path),
            start_line=int(start_line),
            start_character=int(start_character),
            end_line=int(end_line),
            end_character=int(end_character),
        )
        result = self.source_service.read_span(request)
        return {
            "file_path": str(result.file_path),
            "range": {
                "start": {
                    "line": result.start_line,
                    "character": result.start_character,
                },
                "end": {
                    "line": result.end_line,
                    "character": result.end_character,
                },
            },
            "text": result.text,
        }

    def _default_read_range(self, symbol):
        read_range = symbol.get("range") or symbol.get("selection_range")
        if read_range is not None:
            return read_range
        return {
            "start": {
                "line": int(symbol["line"]),
                "character": int(symbol["character"]),
            },
            "end": {
                "line": int(symbol["line"]),
                "character": int(symbol["character"]),
            },
        }

    def _find_document_symbol(self, symbols, symbol):
        best_match = None
        best_score = -1
        for item in self._iter_document_symbols(symbols):
            score = self._document_symbol_match_score(item, symbol)
            if score > best_score:
                best_match = item
                best_score = score
        return best_match if best_score >= 0 else None

    def _iter_document_symbols(self, symbols):
        for item in symbols:
            yield item
            yield from self._iter_document_symbols(item.get("children", []))

    def _document_symbol_match_score(self, item, symbol):
        if item.get("file_path") != symbol.get("file_path"):
            return -1
        if item.get("kind") != symbol.get("kind"):
            return -1

        item_name = item.get("name")
        symbol_name = symbol.get("name")
        if item_name is None or symbol_name is None:
            return -1

        item_short_name = self._short_symbol_name(item_name)
        symbol_short_name = self._short_symbol_name(symbol_name)
        if item_short_name != symbol_short_name:
            return -1

        score = 10
        effective_range = item.get("selection_range") or item.get("range")
        if effective_range is None:
            return score
        start = effective_range["start"]
        if start["line"] == int(symbol["line"]) and start["character"] == int(symbol["character"]):
            score += 100

        item_range = item.get("range")
        symbol_range = symbol.get("range")
        if item_range is not None and symbol_range is not None and item_range == symbol_range:
            score += 50

        if item.get("container_name") == symbol.get("container_name"):
            score += 5

        return score

    def _short_symbol_name(self, name):
        short_name = name.rsplit(".", 1)[-1]
        if "(" in short_name:
            short_name = short_name.split("(", 1)[0]
        return short_name

    def _extract_declaration_text(self, text, base_range):
        declaration_text = text
        delimiter_index = None
        for delimiter in ("{", ";"):
            index = declaration_text.find(delimiter)
            if index != -1 and (delimiter_index is None or index < delimiter_index):
                delimiter_index = index

        if delimiter_index is not None:
            include_delimiter = declaration_text[delimiter_index] == ";"
            end_index = delimiter_index + (1 if include_delimiter else 0)
            declaration_text = declaration_text[:end_index].rstrip()
        else:
            declaration_text = declaration_text.rstrip()

        return declaration_text, self._range_for_text(base_range, declaration_text)

    def _range_for_text(self, base_range, text):
        start = base_range["start"]
        lines = text.splitlines()
        if not lines:
            end_line = start["line"]
            end_character = start["character"]
        elif len(lines) == 1:
            end_line = start["line"]
            end_character = start["character"] + len(lines[0])
        else:
            end_line = start["line"] + len(lines) - 1
            end_character = len(lines[-1])

        return {
            "start": {
                "line": start["line"],
                "character": start["character"],
            },
            "end": {
                "line": end_line,
                "character": end_character,
            },
        }

    def _build_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format_string, *args):
                logger.info("http: %s", format_string % args)

            def do_GET(self):
                if self.path != "/health":
                    self._write_json(404, {"ok": False, "error": "Not found"})
                    return

                self._write_json(200, {"ok": True, **health.handle(server.workspace_service, {})})

            def do_POST(self):
                try:
                    payload = self._read_json()
                    if self.path == "/definition-by-symbol":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **server.find_definition_by_symbol(payload),
                            },
                        )
                        return

                    if self.path == "/references-by-symbol":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **server.find_references_by_symbol(payload),
                            },
                        )
                        return

                    if self.path == "/implementations-by-symbol":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **server.find_implementations_by_symbol(payload),
                            },
                        )
                        return

                    if self.path == "/document-symbols":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **document_symbols.handle(
                                    server.workspace_service,
                                    server.navigation_service,
                                    payload,
                                ),
                            },
                        )
                        return

                    if self.path == "/open-solution":
                        self._write_json(
                            200,
                            {"ok": True, **open_solution.handle(server.workspace_service, payload)},
                        )
                        return

                    if self.path == "/read-symbol":
                        self._write_json(
                            200,
                            {"ok": True, **server.read_symbol(payload)},
                        )
                        return

                    if self.path == "/read-file":
                        self._write_json(
                            200,
                            {"ok": True, **server.read_file(payload)},
                        )
                        return

                    if self.path == "/search-symbols":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **search_symbols.handle(
                                    server.workspace_service,
                                    server.navigation_service,
                                    payload,
                                ),
                            },
                        )
                        return

                    if self.path == "/shutdown":
                        self._write_json(200, {"ok": True})
                        threading.Thread(
                            target=self._shutdown_async,
                            name="backend-shutdown",
                            daemon=True,
                        ).start()
                        return

                    self._write_json(404, {"ok": False, "error": "Not found"})
                except WorkspaceNotReadyError as exc:
                    self._write_json(
                        503,
                        {
                            "ok": False,
                            "error": str(exc),
                            "workspace": str(exc.status_result.workspace),
                            "status": exc.status_result.status,
                            "last_error": exc.status_result.last_error,
                        },
                    )
                except NotImplementedError as exc:
                    self._write_json(501, {"ok": False, "error": str(exc)})
                except InvalidSymbolHandleError as exc:
                    self._write_json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    self._write_json(
                        500,
                        {
                            "ok": False,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                    )

            def _shutdown_async(self):
                if server.httpd is not None:
                    server.httpd.shutdown()

            def _read_json(self):
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length) if content_length else b"{}"
                return json.loads(body.decode("utf-8"))

            def _write_json(self, status_code, payload):
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the internal Roslyn runtime used by the MCP server"
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config.json",
        help="Server config file",
    )
    return parser.parse_args(argv)


def main(argv=None):
    configure_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        server = BackendServer(load_server_config(args.config))
        server.serve_forever()
    except Exception as exc:
        logger.exception("Failed to run internal Roslyn runtime: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
