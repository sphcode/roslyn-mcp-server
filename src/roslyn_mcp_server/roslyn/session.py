import os
import subprocess
import threading
from pathlib import Path

from roslyn_mcp_server.roslyn.lsp_adapter import LspClient, LspError
from roslyn_mcp_server.roslyn.translators import path_to_uri


def guess_csharp_design_time_path(server_path):
    candidate_names = [
        server_path.resolve().parents[1]
        / ".razorExtension/Targets/Microsoft.CSharpExtension.DesignTime.targets",
        server_path.resolve().parent.parent
        / ".razorExtension/Targets/Microsoft.CSharpExtension.DesignTime.targets",
    ]

    for candidate in candidate_names:
        if candidate.exists():
            return candidate

    vscode_extension_roots = [
        Path.home() / ".vscode/extensions",
        Path.home() / ".cursor/extensions",
        Path.home() / ".vscode-insiders/extensions",
    ]
    for root in vscode_extension_roots:
        if not root.exists():
            continue
        matches = sorted(
            root.glob(
                "ms-dotnettools.csharp*/.razorExtension/Targets/Microsoft.CSharpExtension.DesignTime.targets"
            )
        )
        if matches:
            return matches[-1]

    return None


class RoslynSession:
    def __init__(self, server_path, solution_or_project_path, log):
        self.server_path = Path(server_path).resolve()
        self.solution_or_project_path = Path(solution_or_project_path).resolve()
        self.workspace_root = self.solution_or_project_path.parent
        self.log = log
        self.process = None
        self.client = None
        self._documents = {}
        self._lock = threading.RLock()

    def start(self):
        log_dir = Path(".logs/roslyn-server").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)

        command = self._build_server_command(log_dir)
        self.log("startup", {"command": command})

        self.process = subprocess.Popen(
            command,
            cwd=str(self.workspace_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.client = LspClient(self.process, self.log)
        initialize_result = self._initialize_client()
        self.log("initialize result", initialize_result)
        self._open_workspace()

        try:
            notification = self.client.wait_for_notification(
                "workspace/projectInitializationComplete",
                timeout=60,
            )
            self.log("workspace/projectInitializationComplete", notification)
            return True
        except LspError as exc:
            self.log("warning", str(exc))
            self.log(
                "warning",
                "Proceeding anyway. If navigation is empty, workspace load likely did not finish.",
            )
            return False

    def definition(self, file_path, line, character):
        with self._lock:
            file_path = Path(file_path).resolve()
            self._sync_document(file_path)
            return self.client.send_request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": path_to_uri(file_path)},
                    "position": {"line": line, "character": character},
                },
                timeout=30,
            )

    def references(self, file_path, line, character, include_declaration=True):
        with self._lock:
            file_path = Path(file_path).resolve()
            self._sync_document(file_path)
            return self.client.send_request(
                "textDocument/references",
                {
                    "textDocument": {"uri": path_to_uri(file_path)},
                    "position": {"line": line, "character": character},
                    "context": {"includeDeclaration": include_declaration},
                },
                timeout=30,
            )

    def close(self):
        if self.client is None:
            return

        try:
            for document_uri in list(self._documents.keys()):
                try:
                    self.client.send_notification(
                        "textDocument/didClose",
                        {"textDocument": {"uri": document_uri}},
                    )
                except Exception as exc:
                    self.log("cleanup", f"didClose failed for {document_uri}: {exc}")
            self.client.shutdown()
        finally:
            self.client = None
            self.process = None
            self._documents.clear()

    def _build_server_command(self, log_dir):
        command = []
        if self.server_path.suffix.lower() == ".dll":
            command.extend(["dotnet", str(self.server_path)])
        else:
            command.append(str(self.server_path))

        command.extend(
            [
                "--stdio",
                "--logLevel",
                "Trace",
                "--telemetryLevel",
                "off",
                "--extensionLogDirectory",
                str(log_dir),
            ]
        )

        csharp_design_time_path = guess_csharp_design_time_path(self.server_path)
        if csharp_design_time_path is not None:
            command.extend(["--csharpDesignTimePath", str(csharp_design_time_path)])
            self.log("startup", f"Using --csharpDesignTimePath {csharp_design_time_path}")
        else:
            self.log(
                "startup",
                "Could not infer --csharpDesignTimePath. Project load may fail for some server builds.",
            )

        return command

    def _initialize_client(self):
        params = {
            "processId": os.getpid(),
            "clientInfo": {
                "name": "roslyn-python-bridge",
                "version": "0.2.0",
            },
            "rootUri": path_to_uri(self.workspace_root),
            "rootPath": str(self.workspace_root),
            "workspaceFolders": [
                {
                    "uri": path_to_uri(self.workspace_root),
                    "name": self.workspace_root.name,
                }
            ],
            "trace": "verbose",
            "capabilities": {
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                    "applyEdit": True,
                },
                "window": {
                    "workDoneProgress": True,
                },
                "textDocument": {
                    "definition": {
                        "linkSupport": True,
                    },
                    "references": {},
                    "publishDiagnostics": {
                        "relatedInformation": True,
                    },
                    "synchronization": {
                        "didSave": True,
                    },
                },
            },
        }
        result = self.client.send_request("initialize", params, timeout=30)
        self.client.send_notification("initialized", {})
        return result

    def _open_workspace(self):
        suffix = self.solution_or_project_path.suffix.lower()
        uri = path_to_uri(self.solution_or_project_path)

        if suffix in {".sln", ".slnx"}:
            self.client.send_notification("solution/open", {"solution": uri})
            self.log("workspace", f"Sent solution/open for {self.solution_or_project_path}")
            return

        if suffix == ".csproj":
            self.client.send_notification("project/open", {"projects": [uri]})
            self.log("workspace", f"Sent project/open for {self.solution_or_project_path}")
            return

        raise ValueError(
            f"Unsupported solution_or_project_path suffix '{self.solution_or_project_path.suffix}'. "
            "Expected .sln, .slnx, or .csproj."
        )

    def _sync_document(self, file_path):
        file_path = Path(file_path).resolve()
        text = file_path.read_text(encoding="utf-8")
        document_uri = path_to_uri(file_path)
        document_state = self._documents.get(document_uri)

        if document_state is None:
            self.client.send_notification(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": document_uri,
                        "languageId": "csharp",
                        "version": 1,
                        "text": text,
                    }
                },
            )
            self._documents[document_uri] = {
                "version": 1,
                "text": text,
            }
            return

        if document_state["text"] == text:
            return

        next_version = document_state["version"] + 1
        self.client.send_notification(
            "textDocument/didChange",
            {
                "textDocument": {
                    "uri": document_uri,
                    "version": next_version,
                },
                "contentChanges": [
                    {
                        "text": text,
                    }
                ],
            },
        )
        document_state["version"] = next_version
        document_state["text"] = text
