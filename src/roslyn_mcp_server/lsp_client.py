import json
import queue
import subprocess
import threading
import time
from collections import defaultdict


class LspError(Exception):
    pass


class LspClient:
    def __init__(self, process, log):
        self.process = process
        self.log = log
        self._next_id = 1
        self._write_lock = threading.Lock()
        self._pending = {}
        self._pending_lock = threading.Lock()
        self._notifications = defaultdict(queue.Queue)
        self._closed = threading.Event()

        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="lsp-reader",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop,
            name="lsp-stderr",
            daemon=True,
        )
        self._reader_thread.start()
        self._stderr_thread.start()

    def send_request(self, method, params=None, timeout=30):
        request_id = self._next_id
        self._next_id += 1
        response_queue = queue.Queue(maxsize=1)

        with self._pending_lock:
            self._pending[request_id] = response_queue

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._send_message(message, "client -> server request")

        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise LspError(
                f"Timed out waiting for response to '{method}' after {timeout}s"
            ) from exc

        if "error" in response:
            raise LspError(
                f"LSP error for '{method}': {json.dumps(response['error'], ensure_ascii=False)}"
            )

        return response.get("result")

    def send_notification(self, method, params=None):
        message = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._send_message(message, "client -> server notification")

    def wait_for_notification(self, method, timeout=30):
        try:
            return self._notifications[method].get(timeout=timeout)
        except queue.Empty as exc:
            raise LspError(
                f"Timed out waiting for notification '{method}' after {timeout}s"
            ) from exc

    def shutdown(self):
        try:
            self.send_request("shutdown", None, timeout=10)
        finally:
            try:
                self.send_notification("exit")
            finally:
                self._wait_for_process_exit()

    def _send_message(self, message, label):
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.log(label, message)
        with self._write_lock:
            if self.process.stdin is None:
                raise LspError("Server stdin is closed")
            self.process.stdin.write(header)
            self.process.stdin.write(body)
            self.process.stdin.flush()

    def _reader_loop(self):
        try:
            while True:
                message = self._read_message()
                if message is None:
                    self.log("lsp", "Server closed stdout")
                    break
                self.log("server -> client", message)
                self._handle_message(message)
        except Exception as exc:
            self.log("lsp", f"Reader loop failed: {exc}")
        finally:
            self._closed.set()
            with self._pending_lock:
                for response_queue in self._pending.values():
                    response_queue.put(
                        {
                            "error": {
                                "code": -1,
                                "message": "Reader loop stopped before a response arrived",
                            }
                        }
                    )
                self._pending.clear()

    def _stderr_loop(self):
        if self.process.stderr is None:
            return

        for raw_line in iter(self.process.stderr.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if line:
                self.log("server stderr", line)

    def _handle_message(self, message):
        if "id" in message and ("result" in message or "error" in message):
            with self._pending_lock:
                response_queue = self._pending.pop(message["id"], None)
            if response_queue is not None:
                response_queue.put(message)
            else:
                self.log("lsp", f"No pending request for response id {message['id']}")
            return

        if "id" in message and "method" in message:
            self._handle_server_request(message)
            return

        if "method" in message:
            self._notifications[message["method"]].put(message.get("params"))

    def _handle_server_request(self, message):
        method = message["method"]
        params = message.get("params")

        if method == "workspace/configuration":
            items = (params or {}).get("items", [])
            result = [None for _ in items]
        elif method in {
            "client/registerCapability",
            "client/unregisterCapability",
            "window/workDoneProgress/create",
        }:
            result = None
        elif method == "workspace/workspaceFolders":
            result = None
        elif method == "workspace/applyEdit":
            result = {"applied": False}
        elif method == "window/showDocument":
            result = {"success": False}
        elif method == "window/showMessageRequest":
            result = None
        else:
            self.log("lsp", f"Unhandled server request '{method}', replying with null")
            result = None

        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": result,
        }
        self._send_message(response, "client -> server response")

    def _read_message(self):
        if self.process.stdout is None:
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

    def _wait_for_process_exit(self):
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.process.poll() is not None:
                return
            time.sleep(0.1)

        self.log("lsp", "Server did not exit after shutdown; terminating process")
        self.process.terminate()
