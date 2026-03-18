import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import argparse
import json

from roslyn_mcp_server.backend.client import BackendClient, BackendClientError
from roslyn_mcp_server.infrastructure.config import load_server_config

SYSTEM_PROMPT = """You are a C# code navigation assistant backed by Roslyn.

Use the available tools instead of guessing. Prefer this workflow:
1. Use search_symbols to find likely entry points across the workspace.
2. Use document_symbols to inspect a candidate file's structure.
3. Use find_definition, find_implementations, and find_references for precise navigation.
4. Use read_span to read source code around the relevant locations before answering.

Important constraints:
- All line and character coordinates are 0-based.
- Do not invent file paths, symbol positions, or code snippets.
- If a tool returns no results, say that clearly and explain what you tried.
- When a tool returns a symbol or location range, use `location.range.start.line` as the exact line number for that symbol.
- `read_span` is only for reading code context. Do not use the start of a read span as the symbol's definition or implementation line.
- The line for an interface/type declaration is not the line for one of its members. If the user asks for a method, cite the method symbol's own range.
- If you need the exact definition or implementation line for a member, prefer the member entry from `document_symbols`, `find_definition`, or `find_implementations` over any surrounding container span.
"""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a minimal LangGraph-based agent demo against the Roslyn backend"
    )
    parser.add_argument("--config", default="config.json", help="Server config file")
    parser.add_argument("--host", help="Backend host override")
    parser.add_argument("--port", type=int, help="Backend port override")
    return parser.parse_args(argv)


def _require_langgraph_stack():
    try:
        from langchain.agents import create_agent
        from langchain.tools import tool
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph demo dependencies are not installed. "
            "Run: python3 -m pip install -e '.[demo]'"
        ) from exc

    return create_agent, tool, ChatOpenAI


def _unwrap_backend_response(response):
    if response.get("ok", False):
        payload = dict(response)
        payload.pop("ok", None)
        return payload
    raise BackendClientError(json.dumps(response, ensure_ascii=False))


def _call_backend_tool(tool_name, operation, *, retry_on_empty=False):
    import time

    last_payload = None
    for attempt in range(1, 4):
        payload = _unwrap_backend_response(operation())
        last_payload = payload
        count = payload.get("count")
        print(
            f"[tool] {tool_name} attempt={attempt} payload={json.dumps(payload, ensure_ascii=False)}",
            file=sys.stderr,
        )
        if not retry_on_empty or count is None or count > 0 or attempt == 3:
            return payload
        time.sleep(0.3)

    return last_payload


def build_tools(client):
    _create_agent, tool, _chat_open_ai = _require_langgraph_stack()

    @tool
    def health() -> str:
        """Return backend workspace health and Roslyn initialization status."""
        return json.dumps(
            _call_backend_tool("health", client.health),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def search_symbols(query: str) -> str:
        """Search workspace symbols by name. Use broad symbol text if an exact interface name returns nothing."""
        return json.dumps(
            _call_backend_tool(
                "search_symbols",
                lambda: client.search_symbols(query=query),
                retry_on_empty=True,
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def document_symbols(file_path: str) -> str:
        """List symbols declared in a single C# file. Use each symbol's location.range.start.line as the exact line for that symbol."""
        return json.dumps(
            _call_backend_tool(
                "document_symbols",
                lambda: client.document_symbols(file_path=file_path),
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def find_definition(file_path: str, line: int, character: int) -> str:
        """Find the exact definition location for the symbol at a 0-based LSP position. Use the returned location.range.start.line directly in your answer."""
        return json.dumps(
            _call_backend_tool(
                "find_definition",
                lambda: client.find_definition(
                    file_path=file_path,
                    line=line,
                    character=character,
                ),
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def find_references(
        file_path: str,
        line: int,
        character: int,
        include_declaration: bool = True,
    ) -> str:
        """Find references for the symbol at a 0-based LSP position."""
        return json.dumps(
            _call_backend_tool(
                "find_references",
                lambda: client.find_references(
                    file_path=file_path,
                    line=line,
                    character=character,
                    include_declaration=include_declaration,
                ),
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def find_implementations(file_path: str, line: int, character: int) -> str:
        """Find the exact implementation locations for the symbol at a 0-based LSP position. Use the returned location.range.start.line directly in your answer."""
        return json.dumps(
            _call_backend_tool(
                "find_implementations",
                lambda: client.find_implementations(
                    file_path=file_path,
                    line=line,
                    character=character,
                ),
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def read_span(
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
    ) -> str:
        """Read a source code span from disk using 0-based start/end positions. This is for code context only, not for determining the exact symbol line when another tool already returned a symbol range."""
        return json.dumps(
            _call_backend_tool(
                "read_span",
                lambda: client.read_span(
                    file_path=file_path,
                    start_line=start_line,
                    start_character=start_character,
                    end_line=end_line,
                    end_character=end_character,
                ),
            ),
            ensure_ascii=False,
            indent=2,
        )

    return [
        health,
        search_symbols,
        document_symbols,
        find_definition,
        find_references,
        find_implementations,
        read_span,
    ]


def _read_prompt():
    if sys.stdin.isatty():
        prompt = input("Prompt> ").strip()
    else:
        prompt = sys.stdin.read().strip()

    if not prompt:
        raise RuntimeError("Prompt is empty. Enter a question in the terminal.")

    return prompt


def _print_messages(messages):
    for message in messages:
        if hasattr(message, "pretty_print"):
            message.pretty_print()
            continue

        if isinstance(message, dict):
            role = message.get("role", "message")
            content = message.get("content")
        else:
            role = getattr(message, "type", "message")
            content = getattr(message, "content", message)

        print(f"[{role}]")
        if isinstance(content, list):
            print(json.dumps(content, ensure_ascii=False, indent=2))
        else:
            print(content)
        print()


def _run_repl(agent):
    state = {"messages": []}

    while True:
        try:
            prompt = _read_prompt()
        except EOFError:
            print("\nExiting.", file=sys.stderr)
            return 0
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            continue

        if prompt in {"exit", "quit", "/exit", "/quit"}:
            return 0

        if prompt == "/reset":
            state = {"messages": []}
            print("[system]\nConversation state reset.\n")
            continue

        previous_count = len(state["messages"])
        state["messages"].append({"role": "user", "content": prompt})

        try:
            state = agent.invoke(state)
        except Exception as exc:
            print(f"LangGraph demo failed: {exc}", file=sys.stderr)
            continue

        _print_messages(state.get("messages", [])[previous_count:])


def main(argv=None):
    args = parse_args(argv)
    config = load_server_config(args.config)
    host = args.host or config["listen_host"]
    port = args.port or config["listen_port"]
    demo_config = config["langgraph_demo"]

    client = BackendClient(host=host, port=port)
    try:
        health_result = _unwrap_backend_response(client.health())
    except BackendClientError as exc:
        print(f"Backend health check failed: {exc}", file=sys.stderr)
        return 1

    if health_result["status"] not in {"ready", "degraded"}:
        print(
            "Backend is not ready for navigation. "
            f"Current status: {health_result['status']}. "
            "Start the backend daemon first and wait for Roslyn to finish loading.",
            file=sys.stderr,
        )
        return 1

    try:
        create_agent, _tool, ChatOpenAI = _require_langgraph_stack()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not demo_config.get("api_key"):
        print("langgraph_demo.api_key is not set in config.json.", file=sys.stderr)
        return 1

    model = ChatOpenAI(
        model=demo_config["model"],
        temperature=0,
        api_key=demo_config["api_key"],
        base_url=demo_config.get("base_url"),
    )
    agent = create_agent(
        model=model,
        tools=build_tools(client),
        system_prompt=SYSTEM_PROMPT,
    )
    print("Interactive chat started. Use /reset to clear context, /exit to quit.")
    return _run_repl(agent)


if __name__ == "__main__":
    raise SystemExit(main())
