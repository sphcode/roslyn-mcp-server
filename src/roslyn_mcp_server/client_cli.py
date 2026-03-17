import argparse
import json
import sys

from roslyn_mcp_server.backend.client import BackendClient, BackendClientError
from roslyn_mcp_server.infrastructure.config import load_server_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Client for the local Roslyn backend daemon")
    parser.add_argument("--config", default="config.json", help="Server config file")
    parser.add_argument("--host", help="Bridge host override")
    parser.add_argument("--port", type=int, help="Bridge port override")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("shutdown")

    definition_parser = subparsers.add_parser("definition")
    definition_parser.add_argument("--file", required=True)
    definition_parser.add_argument("--line", required=True, type=int)
    definition_parser.add_argument("--character", required=True, type=int)

    references_parser = subparsers.add_parser("references")
    references_parser.add_argument("--file", required=True)
    references_parser.add_argument("--line", required=True, type=int)
    references_parser.add_argument("--character", required=True, type=int)
    references_parser.add_argument(
        "--include-declaration",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    implementations_parser = subparsers.add_parser("implementations")
    implementations_parser.add_argument("--file", required=True)
    implementations_parser.add_argument("--line", required=True, type=int)
    implementations_parser.add_argument("--character", required=True, type=int)

    document_symbols_parser = subparsers.add_parser("document-symbols")
    document_symbols_parser.add_argument("--file", required=True)

    search_symbols_parser = subparsers.add_parser("search-symbols")
    search_symbols_parser.add_argument("--query", required=True)

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = load_server_config(args.config)
    host = args.host or config["listen_host"]
    port = args.port or config["listen_port"]
    client = BackendClient(host=host, port=port)

    try:
        if args.command == "health":
            response = client.health()
        elif args.command == "shutdown":
            response = client.shutdown()
        elif args.command == "definition":
            response = client.find_definition(
                file_path=args.file,
                line=args.line,
                character=args.character,
            )
        elif args.command == "references":
            response = client.find_references(
                file_path=args.file,
                line=args.line,
                character=args.character,
                include_declaration=args.include_declaration,
            )
        elif args.command == "implementations":
            response = client.find_implementations(
                file_path=args.file,
                line=args.line,
                character=args.character,
            )
        elif args.command == "document-symbols":
            response = client.document_symbols(file_path=args.file)
        elif args.command == "search-symbols":
            response = client.search_symbols(query=args.query)
        else:
            raise ValueError(f"Unsupported command {args.command}")
    except BackendClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
