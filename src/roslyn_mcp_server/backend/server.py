import argparse
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    find_definition,
    find_implementations,
    find_references,
    health,
    open_solution,
    read_span,
    search_symbols,
)
from roslyn_mcp_server.roslyn.session import RoslynSession

logger = get_logger(__name__)


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
                    if self.path == "/definition":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **find_definition.handle(
                                    server.workspace_service,
                                    server.navigation_service,
                                    payload,
                                ),
                            },
                        )
                        return

                    if self.path == "/references":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **find_references.handle(
                                    server.workspace_service,
                                    server.navigation_service,
                                    payload,
                                ),
                            },
                        )
                        return

                    if self.path == "/implementations":
                        self._write_json(
                            200,
                            {
                                "ok": True,
                                **find_implementations.handle(
                                    server.workspace_service,
                                    server.navigation_service,
                                    payload,
                                ),
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

                    if self.path == "/read-span":
                        self._write_json(
                            200,
                            {"ok": True, **read_span.handle(server.source_service, payload)},
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
