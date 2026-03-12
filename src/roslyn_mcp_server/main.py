import sys
import time
import traceback

from roslyn_mcp_server.bridge_server import BridgeServer
from roslyn_mcp_server.config_utils import load_server_config


def log(prefix, payload):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {prefix}: {payload}", flush=True)


if __name__ == "__main__":
    config_arg = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    try:
        server = BridgeServer(load_server_config(config_arg), log)
        server.serve_forever()
    except Exception as exc:
        log("fatal", str(exc))
        traceback.print_exc()
        sys.exit(1)
