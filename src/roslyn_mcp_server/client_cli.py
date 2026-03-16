import argparse
import json
import sys
import urllib.error
import urllib.request

from roslyn_mcp_server.infrastructure.config import load_server_config


def request_json(method, url, payload=None):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


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

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = load_server_config(args.config)
    host = args.host or config["listen_host"]
    port = args.port or config["listen_port"]
    base_url = f"http://{host}:{port}"

    try:
        if args.command == "health":
            response = request_json("GET", f"{base_url}/health")
        elif args.command == "shutdown":
            response = request_json("POST", f"{base_url}/shutdown", {})
        elif args.command == "definition":
            response = request_json(
                "POST",
                f"{base_url}/definition",
                {
                    "file_path": args.file,
                    "line": args.line,
                    "character": args.character,
                },
            )
        elif args.command == "references":
            response = request_json(
                "POST",
                f"{base_url}/references",
                {
                    "file_path": args.file,
                    "line": args.line,
                    "character": args.character,
                    "include_declaration": args.include_declaration,
                },
            )
        else:
            raise ValueError(f"Unsupported command {args.command}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(body, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Failed to connect to bridge server: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
