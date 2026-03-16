import json
import urllib.error
import urllib.request


class BackendClientError(RuntimeError):
    pass


class BackendClient:
    def __init__(self, host, port):
        self.base_url = f"http://{host}:{port}"

    def health(self):
        return self._request_json("GET", "/health")

    def find_definition(self, file_path, line, character):
        return self._request_json(
            "POST",
            "/definition",
            {
                "file_path": file_path,
                "line": line,
                "character": character,
            },
        )

    def find_references(self, file_path, line, character, include_declaration=True):
        return self._request_json(
            "POST",
            "/references",
            {
                "file_path": file_path,
                "line": line,
                "character": character,
                "include_declaration": include_declaration,
            },
        )

    def read_span(
        self,
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
    ):
        return self._request_json(
            "POST",
            "/read-span",
            {
                "file_path": file_path,
                "start_line": start_line,
                "start_character": start_character,
                "end_line": end_line,
                "end_character": end_character,
            },
        )

    def shutdown(self):
        return self._request_json("POST", "/shutdown", {})

    def _request_json(self, method, path, payload=None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BackendClientError(
                f"Backend request failed with status {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise BackendClientError(
                f"Failed to connect to backend at {self.base_url}: {exc}"
            ) from exc
