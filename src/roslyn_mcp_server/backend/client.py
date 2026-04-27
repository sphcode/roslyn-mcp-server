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

    def find_definition_by_symbol(self, symbol_handle):
        return self._request_json(
            "POST",
            "/definition-by-symbol",
            {
                "symbol_handle": symbol_handle,
            },
        )

    def find_references_by_symbol(self, symbol_handle, include_declaration=True):
        return self._request_json(
            "POST",
            "/references-by-symbol",
            {
                "symbol_handle": symbol_handle,
                "include_declaration": include_declaration,
            },
        )

    def find_implementations_by_symbol(self, symbol_handle):
        return self._request_json(
            "POST",
            "/implementations-by-symbol",
            {
                "symbol_handle": symbol_handle,
            },
        )

    def document_symbols(self, file_path):
        return self._request_json(
            "POST",
            "/document-symbols",
            {
                "file_path": file_path,
            },
        )

    def search_symbols(self, query):
        return self._request_json(
            "POST",
            "/search-symbols",
            {
                "query": query,
            },
        )

    def read_symbol(self, symbol_handle, include_body=True, context_lines=0):
        return self._request_json(
            "POST",
            "/read-symbol",
            {
                "symbol_handle": symbol_handle,
                "include_body": include_body,
                "context_lines": context_lines,
            },
        )

    def read_file(self, file_path, start_line=0, end_line=None):
        payload = {
            "file_path": file_path,
            "start_line": start_line,
        }
        if end_line is not None:
            payload["end_line"] = end_line
        return self._request_json(
            "POST",
            "/read-file",
            payload,
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
