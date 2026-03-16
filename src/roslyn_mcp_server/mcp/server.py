import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from roslyn_mcp_server.application.services.navigation_service import NavigationService
from roslyn_mcp_server.application.services.source_service import SourceService
from roslyn_mcp_server.application.services.workspace_service import WorkspaceService
from roslyn_mcp_server.mcp.tools import (
    find_definition,
    find_references,
    open_solution,
    read_span,
    search_symbols,
)
from roslyn_mcp_server.roslyn.session import RoslynSession


class RequestAlreadyHandled(Exception):
    pass


class RoslynMcpServer:
    def __init__(self, config, log):
        self.config = config
        self.log = log
        self.session = RoslynSession(
            server_path=config["server_path"],
            solution_or_project_path=config["solution_or_project_path"],
            log=log,
        )
        self.workspace_service = WorkspaceService(self.session, log)
        self.navigation_service = NavigationService(self.session)
        self.source_service = SourceService()
        self.httpd = None

    def serve_forever(self):
        self.httpd = ThreadingHTTPServer(
            (self.config["listen_host"], self.config["listen_port"]),
            self._build_handler(),
        )
        self.log(
            "bridge",
            f"Listening on http://{self.config['listen_host']}:{self.config['listen_port']}",
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

    def _build_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format_string, *args):
                server.log("http", format_string % args)

            def do_GET(self):
                if self.path != "/health":
                    self._write_json(404, {"ok": False, "error": "Not found"})
                    return

                result = server.workspace_service.health()
                self._write_json(
                    200,
                    {
                        "ok": result.status != "failed",
                        "workspace": str(result.workspace),
                        "status": result.status,
                        "last_error": result.last_error,
                    },
                )

            def do_POST(self):
                try:
                    payload = self._read_json()
                    if self.path == "/definition":
                        self._ensure_navigation_ready()
                        self._write_json(
                            200,
                            {"ok": True, **find_definition.handle(server.navigation_service, payload)},
                        )
                        return

                    if self.path == "/references":
                        self._ensure_navigation_ready()
                        self._write_json(
                            200,
                            {"ok": True, **find_references.handle(server.navigation_service, payload)},
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
                            {"ok": True, **search_symbols.handle(server.navigation_service, payload)},
                        )
                        return

                    if self.path == "/shutdown":
                        self._write_json(200, {"ok": True})
                        threading.Thread(
                            target=self._shutdown_async,
                            name="bridge-shutdown",
                            daemon=True,
                        ).start()
                        return

                    self._write_json(404, {"ok": False, "error": "Not found"})
                except NotImplementedError as exc:
                    self._write_json(501, {"ok": False, "error": str(exc)})
                except RequestAlreadyHandled:
                    return
                except Exception as exc:
                    self._write_json(
                        500,
                        {
                            "ok": False,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                    )

            def _ensure_navigation_ready(self):
                if server.workspace_service.can_serve_navigation():
                    return

                health = server.workspace_service.health()
                self._write_json(
                    503,
                    {
                        "ok": False,
                        "error": "Workspace is not ready for navigation",
                        "workspace": str(health.workspace),
                        "status": health.status,
                        "last_error": health.last_error,
                    },
                )
                raise RequestAlreadyHandled()

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
