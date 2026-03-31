import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
JSONRPC_VERSION = "2.0"


class McpProcessClientError(RuntimeError):
    pass


class McpProcessClient:
    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.process = None
        self._next_id = 1

    def start(self):
        if self.process is not None:
            return

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        if existing_pythonpath:
            env["PYTHONPATH"] = f"{SRC_ROOT}:{existing_pythonpath}"
        else:
            env["PYTHONPATH"] = str(SRC_ROOT)

        command = [
            sys.executable,
            "-m",
            "roslyn_mcp_server.main",
            str(self.config_path),
        ]
        self.process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            env=env,
        )
        self.initialize()

    def initialize(self):
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "langgraph-demo",
                    "version": "0.1.0",
                },
            },
        )
        self.notify("notifications/initialized", {})

    def list_tools(self):
        result = self.request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name, arguments=None):
        result = self.request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments or {},
            },
        )
        payload = result.get("structuredContent")
        if payload is not None:
            return payload

        content = result.get("content") or []
        if content and content[0].get("type") == "text":
            try:
                return json.loads(content[0]["text"])
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "error": {
                        "type": "mcp_content_error",
                        "message": content[0]["text"],
                    },
                }

        raise McpProcessClientError(f"MCP tool '{name}' returned no structured content")

    def request(self, method, params=None):
        message = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self._next_id,
            "method": method,
        }
        self._next_id += 1
        if params is not None:
            message["params"] = params

        self._send_message(message)
        while True:
            response = self._read_message()
            if response is None:
                raise McpProcessClientError("MCP server closed stdout")
            if response.get("id") != message["id"]:
                continue
            if "error" in response:
                error = response["error"]
                raise McpProcessClientError(
                    f"MCP request '{method}' failed: {json.dumps(error, ensure_ascii=False)}"
                )
            return response.get("result") or {}

    def notify(self, method, params=None):
        message = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._send_message(message)

    def close(self):
        if self.process is None:
            return
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
        finally:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None

    def _send_message(self, message):
        if self.process is None or self.process.stdin is None:
            raise McpProcessClientError("MCP server is not running")
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header)
        self.process.stdin.write(body)
        self.process.stdin.flush()

    def _read_message(self):
        if self.process is None or self.process.stdout is None:
            return None

        headers = {}
        while True:
            line = self.process.stdout.readline()
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
        body = self.process.stdout.read(content_length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))
