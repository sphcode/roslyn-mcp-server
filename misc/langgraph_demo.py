import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_process_client import McpProcessClient, McpProcessClientError
SYSTEM_PROMPT = """You are a C# code navigation assistant backed by Roslyn.

Use the available tools instead of guessing. Prefer this workflow:
1. Use search_symbols to find likely entry points across the workspace.
2. Use document_symbols to inspect a candidate file's structure.
3. Use find_definition_by_symbol, find_implementations_by_symbol, and find_references_by_symbol for precise navigation.
4. Use read_symbol to read symbol source directly before answering.
5. Use read_file when the user already gave you a file path or when you need broader file context.

Important constraints:
- Prefer symbol-oriented tools over raw position-oriented reasoning.
- Treat symbol_handle as an opaque handle returned by tools. Copy it exactly. Do not invent, rewrite, or partially reconstruct it.
- All line and character coordinates in tool results are 0-based.
- Do not invent file paths, symbol positions, or code snippets.
- If a tool returns no results, say that clearly and explain what you tried.
- When a tool returns a symbol or location range, use `location.range.start.line` as the exact line number for that symbol.
- `read_symbol` is the preferred way to read code for a known symbol.
- `read_file` is the preferred way to read a file directly.
- The line for an interface/type declaration is not the line for one of its members. If the user asks for a method, cite the method symbol's own range.
- If you need the exact definition or implementation line for a member, prefer the member entry from `document_symbols`, `find_definition_by_symbol`, or `find_implementations_by_symbol` over any surrounding container span.
"""

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run an interactive LangGraph demo against the Roslyn MCP server"
    )
    parser.add_argument("--config", default="config.json", help="Config file")
    return parser.parse_args(argv)


def _load_config(config_path: Path):
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    demo_config = dict(config.get("langgraph_demo") or {})
    demo_config.setdefault("model", "gpt-4.1-mini")
    return demo_config


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


def _tool_error_payload(tool_name, error_type, message):
    payload = {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    print(
        f"[tool] {tool_name} error={json.dumps(payload, ensure_ascii=False)}",
        file=sys.stderr,
    )
    return payload


def _call_mcp_tool(client, tool_name, arguments=None, *, retry_on_empty=False):
    last_payload = None
    for attempt in range(1, 4):
        try:
            payload = client.call_tool(tool_name, arguments or {})
        except McpProcessClientError as exc:
            return _tool_error_payload(tool_name, "mcp_error", str(exc))
        except Exception as exc:
            return _tool_error_payload(tool_name, "tool_execution_error", str(exc))

        last_payload = payload
        count = payload.get("count") if isinstance(payload, dict) else None
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
        """Return workspace health and Roslyn initialization status."""
        return json.dumps(
            _call_mcp_tool(client, "health"),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def search_symbols(query: str) -> str:
        """Search workspace symbols by name. Use broad symbol text if an exact interface name returns nothing."""
        return json.dumps(
            _call_mcp_tool(
                client,
                "search_symbols",
                {"query": query},
                retry_on_empty=True,
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def document_symbols(file_path: str) -> str:
        """List symbols declared in a single C# file. Each symbol includes a symbol_handle that should be reused for follow-up navigation."""
        return json.dumps(
            _call_mcp_tool(client, "document_symbols", {"file_path": file_path}),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def find_definition_by_symbol(symbol_handle: str) -> str:
        """Find definition locations for a previously discovered symbol_handle."""
        return json.dumps(
            _call_mcp_tool(
                client,
                "find_definition_by_symbol",
                {"symbol_handle": symbol_handle},
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def find_references_by_symbol(
        symbol_handle: str,
        include_declaration: bool = True,
    ) -> str:
        """Find references for a previously discovered symbol_handle."""
        return json.dumps(
            _call_mcp_tool(
                client,
                "find_references_by_symbol",
                {
                    "symbol_handle": symbol_handle,
                    "include_declaration": include_declaration,
                },
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def find_implementations_by_symbol(symbol_handle: str) -> str:
        """Find implementation locations for a previously discovered symbol_handle."""
        return json.dumps(
            _call_mcp_tool(
                client,
                "find_implementations_by_symbol",
                {"symbol_handle": symbol_handle},
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def read_symbol(
        symbol_handle: str,
        include_body: bool = True,
        context_lines: int = 0,
    ) -> str:
        """Read the source for a previously discovered symbol_handle."""
        return json.dumps(
            _call_mcp_tool(
                client,
                "read_symbol",
                {
                    "symbol_handle": symbol_handle,
                    "include_body": include_body,
                    "context_lines": context_lines,
                },
            ),
            ensure_ascii=False,
            indent=2,
        )

    @tool
    def read_file(
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read a file directly, optionally restricted to a line range."""
        arguments = {"file_path": file_path}
        if start_line is not None:
            arguments["start_line"] = start_line
        if end_line is not None:
            arguments["end_line"] = end_line

        return json.dumps(
            _call_mcp_tool(
                client,
                "read_file",
                arguments,
            ),
            ensure_ascii=False,
            indent=2,
        )

    return [
        health,
        search_symbols,
        document_symbols,
        find_definition_by_symbol,
        find_references_by_symbol,
        find_implementations_by_symbol,
        read_symbol,
        read_file,
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
    config_path = Path(args.config).resolve()
    demo_config = _load_config(config_path)

    try:
        create_agent, _tool, ChatOpenAI = _require_langgraph_stack()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not demo_config.get("api_key"):
        print("langgraph_demo.api_key is not set in config.json.", file=sys.stderr)
        return 1

    client = McpProcessClient(config_path)
    try:
        client.start()
        available_tools = {tool["name"] for tool in client.list_tools()}
        missing_tools = {
            "health",
            "search_symbols",
            "document_symbols",
            "find_definition_by_symbol",
            "find_references_by_symbol",
            "find_implementations_by_symbol",
            "read_symbol",
            "read_file",
        } - available_tools
        if missing_tools:
            print(
                f"MCP server is missing required tools: {sorted(missing_tools)}",
                file=sys.stderr,
            )
            return 1

        health_result = _call_mcp_tool(client, "health")
        if not health_result.get("ok", True):
            print(
                f"MCP health check failed: {json.dumps(health_result, ensure_ascii=False)}",
                file=sys.stderr,
            )
            return 1
        if health_result["status"] not in {"ready", "degraded"}:
            print(
                "MCP server is not ready for navigation. "
                f"Current status: {health_result['status']}",
                file=sys.stderr,
            )
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
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
