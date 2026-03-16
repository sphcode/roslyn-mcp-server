import argparse
import sys

from roslyn_mcp_server.infrastructure.config import load_server_config
from roslyn_mcp_server.infrastructure.logging import configure_logging, get_logger
from roslyn_mcp_server.mcp.server import RoslynMcpServer

logger = get_logger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the Roslyn MCP stdio adapter")
    parser.add_argument(
        "config",
        nargs="?",
        default="config.json",
        help="Server config file",
    )
    return parser.parse_args(argv)


def main(argv=None):
    configure_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        server = RoslynMcpServer(load_server_config(args.config))
        server.serve_forever()
    except Exception as exc:
        logger.exception("Failed to run MCP adapter: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
