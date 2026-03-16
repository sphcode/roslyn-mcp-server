import argparse
import sys
import traceback

from roslyn_mcp_server.infrastructure.config import load_server_config
from roslyn_mcp_server.infrastructure.logging import log
from roslyn_mcp_server.mcp.server import RoslynMcpServer


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the local Roslyn MCP server")
    parser.add_argument(
        "config",
        nargs="?",
        default="config.json",
        help="Server config file",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        server = RoslynMcpServer(load_server_config(args.config), log)
        server.serve_forever()
    except Exception as exc:
        log("fatal", str(exc))
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
