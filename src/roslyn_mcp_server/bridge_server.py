import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from roslyn_mcp_server.roslyn_session import RoslynSession


class BridgeServer:
    def __init__(self, config, log):
        self.config = config
        self.log = log
        self.session = RoslynSession(
            server_path=config["server_path"],
            solution_or_project_path=config["solution_or_project_path"],
            log=log,
        )
        self.httpd = None

    def serve_forever(self):
        self.session.start()
        self.httpd = ThreadingHTTPServer(
            (self.config["listen_host"], self.config["listen_port"]),
            self._build_handler(),
        )
        self.log(
            "bridge",
            f"Listening on http://{self.config['listen_host']}:{self.config['listen_port']}",
        )
        try:
            self.httpd.serve_forever()
        finally:
            self.close()

    def close(self):
        if self.httpd is not None:
            self.httpd.server_close()
            self.httpd = None
        self.session.close()

    def _build_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format_string, *args):
                bridge.log("http", format_string % args)

            def do_GET(self):
                if self.path != "/health":
                    self._write_json(404, {"ok": False, "error": "Not found"})
                    return

                self._write_json(
                    200,
                    {
                        "ok": True,
                        "workspace": str(bridge.config["solution_or_project_path"]),
                    },
                )

            def do_POST(self):
                try:
                    payload = self._read_json()
                    if self.path == "/definition":
                        result = bridge.session.definition(
                            file_path=payload["file_path"],
                            line=int(payload["line"]),
                            character=int(payload["character"]),
                        )
                        self._write_json(200, {"ok": True, "result": result})
                        return

                    if self.path == "/references":
                        result = bridge.session.references(
                            file_path=payload["file_path"],
                            line=int(payload["line"]),
                            character=int(payload["character"]),
                            include_declaration=bool(
                                payload.get("include_declaration", True)
                            ),
                        )
                        self._write_json(200, {"ok": True, "result": result})
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
                if bridge.httpd is not None:
                    bridge.httpd.shutdown()

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
