import threading
import traceback
from pathlib import Path

from roslyn_mcp_server.application.models.requests import OpenSolutionRequest
from roslyn_mcp_server.application.models.results import WorkspaceStatusResult


class WorkspaceService:
    def __init__(self, session, log):
        self.session = session
        self.log = log
        self._lock = threading.Lock()
        self._status = "stopped"
        self._last_error = None
        self._startup_thread = None

    def start(self):
        with self._lock:
            if self._status in {"starting", "ready", "degraded"}:
                return
            self._status = "starting"
            self._last_error = None
            self._startup_thread = threading.Thread(
                target=self._start_session,
                name="workspace-startup",
                daemon=True,
            )
            self._startup_thread.start()

    def close(self):
        with self._lock:
            self._status = "stopped"
        self.session.close()

    def health(self):
        with self._lock:
            return WorkspaceStatusResult(
                workspace=self.session.solution_or_project_path,
                status=self._status,
                last_error=self._last_error,
            )

    def open_solution(self, request: OpenSolutionRequest):
        requested_path = Path(request.solution_or_project_path).resolve()
        current_path = self.session.solution_or_project_path.resolve()
        if requested_path != current_path:
            raise NotImplementedError(
                "Dynamic workspace switching is not implemented yet. Restart the server with a new config."
            )
        return self.health()

    def can_serve_navigation(self):
        with self._lock:
            return self._status in {"ready", "degraded"}

    def _start_session(self):
        try:
            workspace_ready = self.session.start()
            with self._lock:
                self._status = "ready" if workspace_ready else "degraded"
                if not workspace_ready and self._last_error is None:
                    self._last_error = (
                        "Timed out waiting for workspace/projectInitializationComplete"
                    )
        except Exception as exc:
            self.log("fatal", f"Workspace startup failed: {exc}")
            self.log("fatal", traceback.format_exc())
            with self._lock:
                self._status = "failed"
                self._last_error = str(exc)
