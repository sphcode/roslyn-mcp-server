import json
import sys
import threading
import traceback

from roslyn_mcp_server.backend.client import BackendClient, BackendClientError
from roslyn_mcp_server.infrastructure.logging import get_logger
from roslyn_mcp_server.roslyn.translators import parse_symbol_handle

JSONRPC_VERSION = "2.0"
logger = get_logger(__name__)
MAX_READ_LINE = 1_000_000_000
MAX_READ_CHARACTER = 1_000_000_000


class RoslynMcpServer:
    def __init__(self, config):
        self.config = config
        self.backend_client = BackendClient(
            host=config["listen_host"],
            port=config["listen_port"],
        )
        self._write_lock = threading.Lock()
        self._running = True
        self._protocol_version = None
        self._tool_handlers = {
            "health": self._call_health,
            "find_definition": self._call_find_definition,
            "find_references": self._call_find_references,
            "find_implementations": self._call_find_implementations,
            "find_definition_by_symbol": self._call_find_definition_by_symbol,
            "find_references_by_symbol": self._call_find_references_by_symbol,
            "find_implementations_by_symbol": self._call_find_implementations_by_symbol,
            "document_symbols": self._call_document_symbols,
            "search_symbols": self._call_search_symbols,
            "read_symbol": self._call_read_symbol,
            "read_file": self._call_read_file,
            "read_span": self._call_read_span,
        }

    def serve_forever(self):
        try:
            while self._running:
                message = self._read_message()
                if message is None:
                    break
                self._handle_message(message)
        finally:
            self.close()

    def close(self):
        self._running = False

    def _handle_message(self, message):
        logger.debug("mcp <- %s", json.dumps(message, ensure_ascii=False))

        if "id" in message and "method" in message:
            self._handle_request(message)
            return

        if "method" in message:
            self._handle_notification(message)
            return

        logger.warning("Ignoring unsupported MCP message shape: %s", message)

    def _handle_request(self, message):
        request_id = message["id"]
        method = message["method"]
        params = message.get("params") or {}

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tool_definitions()}
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            else:
                self._send_error(request_id, -32601, f"Method not found: {method}")
                return
        except Exception as exc:
            self._send_error(
                request_id,
                -32000,
                str(exc),
                {"traceback": traceback.format_exc()},
            )
            return

        self._send_result(request_id, result)

    def _handle_notification(self, message):
        method = message["method"]
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return
        logger.warning("Unhandled MCP notification: %s", method)

    def _handle_initialize(self, params):
        self._protocol_version = params.get("protocolVersion") or "2024-11-05"
        return {
            "protocolVersion": self._protocol_version,
            "capabilities": {
                "tools": {
                    "listChanged": False,
                }
            },
            "serverInfo": {
                "name": "roslyn-mcp-server",
                "version": "0.1.0",
            },
        }

    def _handle_tools_call(self, params):
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return self._tool_failure_result(
                error_type="unknown_tool",
                message=f"Unknown tool '{tool_name}'",
                details={"tool": tool_name},
            )

        try:
            payload = handler(arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, ensure_ascii=False, indent=2),
                    }
                ],
                "structuredContent": payload,
                "isError": False,
            }
        except BackendClientError as exc:
            logger.warning("Tool '%s' failed with backend error: %s", tool_name, exc)
            return self._tool_failure_result(
                error_type="backend_error",
                message=str(exc),
            )
        except Exception as exc:
            logger.exception("Tool '%s' failed with unexpected error: %s", tool_name, exc)
            return self._tool_failure_result(
                error_type="tool_execution_error",
                message=str(exc),
            )

    def _call_health(self, _arguments):
        response = self.backend_client.health()
        return self._unwrap_backend_response(response)

    def _call_find_definition(self, arguments):
        response = self.backend_client.find_definition(
            file_path=arguments["file_path"],
            line=int(arguments["line"]),
            character=int(arguments["character"]),
        )
        return self._unwrap_backend_response(response)

    def _call_find_references(self, arguments):
        response = self.backend_client.find_references(
            file_path=arguments["file_path"],
            line=int(arguments["line"]),
            character=int(arguments["character"]),
            include_declaration=bool(arguments.get("include_declaration", True)),
        )
        return self._unwrap_backend_response(response)

    def _call_find_implementations(self, arguments):
        response = self.backend_client.find_implementations(
            file_path=arguments["file_path"],
            line=int(arguments["line"]),
            character=int(arguments["character"]),
        )
        return self._unwrap_backend_response(response)

    def _call_find_definition_by_symbol(self, arguments):
        symbol = self._parse_symbol(arguments["symbol_handle"])
        response = self.backend_client.find_definition(
            file_path=symbol["file_path"],
            line=int(symbol["line"]),
            character=int(symbol["character"]),
        )
        payload = self._unwrap_backend_response(response)
        payload["query"] = {"symbol_handle": arguments["symbol_handle"]}
        return payload

    def _call_find_references_by_symbol(self, arguments):
        symbol = self._parse_symbol(arguments["symbol_handle"])
        response = self.backend_client.find_references(
            file_path=symbol["file_path"],
            line=int(symbol["line"]),
            character=int(symbol["character"]),
            include_declaration=bool(arguments.get("include_declaration", True)),
        )
        payload = self._unwrap_backend_response(response)
        payload["query"] = {
            "symbol_handle": arguments["symbol_handle"],
            "include_declaration": bool(arguments.get("include_declaration", True)),
        }
        return payload

    def _call_find_implementations_by_symbol(self, arguments):
        symbol = self._parse_symbol(arguments["symbol_handle"])
        response = self.backend_client.find_implementations(
            file_path=symbol["file_path"],
            line=int(symbol["line"]),
            character=int(symbol["character"]),
        )
        payload = self._unwrap_backend_response(response)
        payload["query"] = {"symbol_handle": arguments["symbol_handle"]}
        return payload

    def _call_document_symbols(self, arguments):
        response = self.backend_client.document_symbols(
            file_path=arguments["file_path"],
        )
        return self._unwrap_backend_response(response)

    def _call_search_symbols(self, arguments):
        response = self.backend_client.search_symbols(
            query=arguments["query"],
        )
        return self._unwrap_backend_response(response)

    def _call_read_symbol(self, arguments):
        symbol = self._parse_symbol(arguments["symbol_handle"])
        include_body = bool(arguments.get("include_body", True))
        context_lines = max(0, int(arguments.get("context_lines", 0)))

        document_symbols_response = self.backend_client.document_symbols(
            file_path=symbol["file_path"],
        )
        document_symbols_payload = self._unwrap_backend_response(document_symbols_response)
        matched_symbol = self._find_document_symbol(document_symbols_payload["symbols"], symbol)

        if matched_symbol is None:
            read_range = symbol.get("range") or symbol.get("selection_range")
            if read_range is None:
                read_range = {
                    "start": {
                        "line": int(symbol["line"]),
                        "character": int(symbol["character"]),
                    },
                    "end": {
                        "line": int(symbol["line"]),
                        "character": int(symbol["character"]),
                    },
                }
            resolved_symbol = None
        else:
            resolved_symbol = {
                "symbol_handle": matched_symbol.get("symbol_handle"),
                "name": matched_symbol.get("name"),
                "kind": matched_symbol.get("kind"),
                "container_name": matched_symbol.get("container_name"),
                "file_path": matched_symbol.get("file_path"),
            }
            if include_body and matched_symbol.get("range") is not None:
                read_range = matched_symbol["range"]
            else:
                read_range = (
                    matched_symbol.get("selection_range")
                    or matched_symbol.get("range")
                )

        span_response = self.backend_client.read_span(
            file_path=symbol["file_path"],
            start_line=max(0, int(read_range["start"]["line"]) - context_lines),
            start_character=0 if context_lines > 0 else int(read_range["start"]["character"]),
            end_line=int(read_range["end"]["line"]) + context_lines,
            end_character=MAX_READ_CHARACTER if context_lines > 0 else int(read_range["end"]["character"]),
        )
        span_payload = self._unwrap_backend_response(span_response)
        return {
            "query": {
                "symbol_handle": arguments["symbol_handle"],
                "include_body": include_body,
                "context_lines": context_lines,
            },
            "resolved_symbol": resolved_symbol,
            "file_path": span_payload["file_path"],
            "range": span_payload["range"],
            "text": span_payload["text"],
        }

    def _call_read_file(self, arguments):
        start_line = max(0, int(arguments.get("start_line", 0)))
        end_line = int(arguments.get("end_line", MAX_READ_LINE))
        if end_line < start_line:
            end_line = start_line

        response = self.backend_client.read_span(
            file_path=arguments["file_path"],
            start_line=start_line,
            start_character=0,
            end_line=end_line,
            end_character=MAX_READ_CHARACTER,
        )
        payload = self._unwrap_backend_response(response)
        payload["query"] = {
            "file_path": arguments["file_path"],
            "start_line": start_line,
            "end_line": end_line if "end_line" in arguments else None,
        }
        return payload

    def _call_read_span(self, arguments):
        response = self.backend_client.read_span(
            file_path=arguments["file_path"],
            start_line=int(arguments["start_line"]),
            start_character=int(arguments["start_character"]),
            end_line=int(arguments["end_line"]),
            end_character=int(arguments["end_character"]),
        )
        return self._unwrap_backend_response(response)

    def _tool_failure_result(self, error_type, message, details=None):
        payload = {
            "ok": False,
            "error": {
                "type": error_type,
                "message": message,
            },
        }
        if details:
            payload["error"]["details"] = details
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False, indent=2),
                }
            ],
            "structuredContent": payload,
            "isError": False,
        }

    def _unwrap_backend_response(self, response):
        if response.get("ok", False):
            payload = dict(response)
            payload.pop("ok", None)
            return payload
        raise BackendClientError(json.dumps(response, ensure_ascii=False))

    def _parse_symbol(self, symbol_handle):
        return parse_symbol_handle(symbol_handle)

    def _find_document_symbol(self, symbols, symbol):
        for item in self._iter_document_symbols(symbols):
            if self._document_symbol_matches(item, symbol):
                return item
        return None

    def _iter_document_symbols(self, symbols):
        for item in symbols:
            yield item
            yield from self._iter_document_symbols(item.get("children", []))

    def _document_symbol_matches(self, item, symbol):
        if item.get("name") != symbol.get("name"):
            return False
        if item.get("kind") != symbol.get("kind"):
            return False

        effective_range = item.get("selection_range") or item.get("range")
        if effective_range is None:
            return False
        start = effective_range["start"]
        return (
            item.get("file_path") == symbol.get("file_path")
            and start["line"] == int(symbol["line"])
            and start["character"] == int(symbol["character"])
        )

    def _tool_definitions(self):
        return [
            {
                "name": "health",
                "description": "Return workspace health and Roslyn initialization status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "find_definition",
                "description": "Find the definition location for a C# symbol at a 0-based LSP position.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "line": {"type": "integer", "minimum": 0},
                        "character": {"type": "integer", "minimum": 0},
                    },
                    "required": ["file_path", "line", "character"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "find_references",
                "description": "Find references for a C# symbol at a 0-based LSP position.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "line": {"type": "integer", "minimum": 0},
                        "character": {"type": "integer", "minimum": 0},
                        "include_declaration": {"type": "boolean"},
                    },
                    "required": ["file_path", "line", "character"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "find_implementations",
                "description": "Find implementation locations for a C# symbol at a 0-based LSP position.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "line": {"type": "integer", "minimum": 0},
                        "character": {"type": "integer", "minimum": 0},
                    },
                    "required": ["file_path", "line", "character"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "find_definition_by_symbol",
                "description": "Find definition locations for a previously discovered symbol_handle.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol_handle": {"type": "string"},
                    },
                    "required": ["symbol_handle"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "find_references_by_symbol",
                "description": "Find references for a previously discovered symbol_handle.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol_handle": {"type": "string"},
                        "include_declaration": {"type": "boolean"},
                    },
                    "required": ["symbol_handle"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "find_implementations_by_symbol",
                "description": "Find implementation locations for a previously discovered symbol_handle.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol_handle": {"type": "string"},
                    },
                    "required": ["symbol_handle"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "document_symbols",
                "description": "List symbols declared in a C# document.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                    },
                    "required": ["file_path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "search_symbols",
                "description": "Search workspace symbols by name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_symbol",
                "description": "Read the source for a symbol_handle directly, optionally including its body and surrounding context.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol_handle": {"type": "string"},
                        "include_body": {"type": "boolean"},
                        "context_lines": {"type": "integer", "minimum": 0},
                    },
                    "required": ["symbol_handle"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_file",
                "description": "Read a file directly, optionally restricted to a line range.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 0},
                        "end_line": {"type": "integer", "minimum": 0},
                    },
                    "required": ["file_path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_span",
                "description": "Read a source span from disk using 0-based start and end positions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 0},
                        "start_character": {"type": "integer", "minimum": 0},
                        "end_line": {"type": "integer", "minimum": 0},
                        "end_character": {"type": "integer", "minimum": 0},
                    },
                    "required": [
                        "file_path",
                        "start_line",
                        "start_character",
                        "end_line",
                        "end_character",
                    ],
                    "additionalProperties": False,
                },
            },
        ]

    def _read_message(self):
        input_stream = sys.stdin.buffer
        headers = {}
        while True:
            line = input_stream.readline()
            if not line:
                return None
            if line == b"\r\n":
                break
            decoded = line.decode("ascii", errors="replace").strip()
            if ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length = int(headers["content-length"])
        body = input_stream.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _send_result(self, request_id, result):
        self._send_message(
            {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": result,
            }
        )

    def _send_error(self, request_id, code, message, data=None):
        error = {
            "code": code,
            "message": message,
        }
        if data is not None:
            error["data"] = data
        self._send_message(
            {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "error": error,
            }
        )

    def _send_message(self, message):
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        logger.debug("mcp -> %s", json.dumps(message, ensure_ascii=False))
        with self._write_lock:
            output_stream = sys.stdout.buffer
            output_stream.write(header)
            output_stream.write(body)
            output_stream.flush()
