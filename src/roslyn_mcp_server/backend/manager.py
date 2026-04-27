import os
import subprocess
import sys
import tempfile
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
        self._port_file = None

    def ensure_running(self):
        if not self._uses_dynamic_port():
            existing_status = self._health_status()
            if existing_status is not None:
                self._validate_workspace(existing_status)
                status_name = existing_status.get("status")
                if status_name in {"starting", "ready", "degraded"}:
                    logger.info(
                        "Reusing existing internal Roslyn runtime at %s",
                        self.client.base_url,
                    )
                    return
                logger.warning(
                    "Existing internal Roslyn runtime is in '%s' state; restarting it",
                    status_name,
                )
                self._shutdown_existing_runtime()

        self._start_subprocess()
        if self._uses_dynamic_port():
            self._wait_for_dynamic_port()
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
            self._remove_port_file()

    def _start_subprocess(self):
        command = [
            sys.executable,
            "-m",
            "roslyn_mcp_server.backend.server",
            str(self.config["config_path"]),
        ]
        env = os.environ.copy()
        if self._uses_dynamic_port():
            self._port_file = self._create_port_file()
            env["ROSLYN_MCP_BACKEND_PORT_FILE"] = self._port_file
        logger.info("Starting internal Roslyn runtime with command: %s", command)
        self.process = subprocess.Popen(command, env=env)
        self._spawned = True

    def _uses_dynamic_port(self):
        return int(self.config["listen_port"]) == 0

    def _create_port_file(self):
        file_descriptor, path = tempfile.mkstemp(
            prefix="roslyn-mcp-backend-",
            suffix=".port",
        )
        os.close(file_descriptor)
        return path

    def _remove_port_file(self):
        if self._port_file is None:
            return
        try:
            os.unlink(self._port_file)
        except FileNotFoundError:
            pass
        finally:
            self._port_file = None

    def _wait_for_dynamic_port(self):
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(
                    f"Internal Roslyn runtime exited early with code {self.process.returncode}"
                )

            port = self._read_dynamic_port()
            if port is not None:
                self.config["listen_port"] = port
                self.client = BackendClient(
                    host=self.config["listen_host"],
                    port=port,
                )
                logger.info("Internal Roslyn runtime selected port %s", port)
                return
            time.sleep(0.1)

        raise RuntimeError("Timed out waiting for the internal Roslyn runtime port")

    def _read_dynamic_port(self):
        if self._port_file is None:
            return None
        try:
            with open(self._port_file, "r", encoding="utf-8") as handle:
                raw_value = handle.read().strip()
        except FileNotFoundError:
            return None
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except ValueError:
            return None

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
                if status.get("status") == "failed":
                    raise RuntimeError(
                        "Internal Roslyn runtime failed to initialize: "
                        f"{status.get('last_error')}"
                    )
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

    def _shutdown_existing_runtime(self):
        try:
            self.client.shutdown()
        except Exception as exc:
            raise RuntimeError(
                "Failed to shut down existing internal Roslyn runtime"
            ) from exc

        deadline = time.time() + 10
        while time.time() < deadline:
            if self._health_status() is None:
                return
            time.sleep(0.5)

        raise RuntimeError("Existing internal Roslyn runtime did not stop in time")

    def _validate_workspace(self, status):
        expected_workspace = str(self.config["solution_or_project_path"])
        actual_workspace = status.get("workspace")
        if actual_workspace != expected_workspace:
            raise RuntimeError(
                "Internal Roslyn runtime workspace mismatch: "
                f"expected {expected_workspace}, got {actual_workspace}"
            )
