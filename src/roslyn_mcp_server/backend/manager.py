import os
import subprocess
import sys
import time

from roslyn_mcp_server.backend.client import BackendClient, BackendClientError
from roslyn_mcp_server.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ManagedBackendRuntime:
    def __init__(self, config):
        self.config = config
        self.client = BackendClient(
            host=config["listen_host"],
            port=config["listen_port"],
        )
        self.process = None
        self._spawned = False

    def ensure_running(self):
        existing_status = self._health_status()
        if existing_status is not None:
            self._validate_workspace(existing_status)
            logger.info("Reusing existing internal Roslyn runtime at %s", self.client.base_url)
            return

        self._start_subprocess()
        self._wait_for_health()

    def close(self):
        if not self._spawned:
            return

        try:
            self.client.shutdown()
        except Exception as exc:
            logger.warning("Failed to request backend shutdown: %s", exc)

        if self.process is None:
            return

        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Internal Roslyn runtime did not exit in time; terminating")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Internal Roslyn runtime ignored terminate; killing")
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            self.process = None
            self._spawned = False

    def _start_subprocess(self):
        command = [
            sys.executable,
            "-m",
            "roslyn_mcp_server.backend.server",
            str(self.config["config_path"]),
        ]
        env = os.environ.copy()
        logger.info("Starting internal Roslyn runtime with command: %s", command)
        self.process = subprocess.Popen(command, env=env)
        self._spawned = True

    def _wait_for_health(self):
        deadline = time.time() + max(
            10,
            self.config["roslyn_timeouts"]["workspace_ready_seconds"] + 10,
        )

        while time.time() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(
                    f"Internal Roslyn runtime exited early with code {self.process.returncode}"
                )

            status = self._health_status()
            if status is not None:
                self._validate_workspace(status)
                return
            time.sleep(0.5)

        raise RuntimeError("Timed out waiting for the internal Roslyn runtime to accept connections")

    def _health_status(self):
        try:
            response = self.client.health()
        except BackendClientError:
            return None
        if not response.get("ok", False):
            return None
        return response

    def _validate_workspace(self, status):
        expected_workspace = str(self.config["solution_or_project_path"])
        actual_workspace = status.get("workspace")
        if actual_workspace != expected_workspace:
            raise RuntimeError(
                "Internal Roslyn runtime workspace mismatch: "
                f"expected {expected_workspace}, got {actual_workspace}"
            )
