# Roslyn MCP Server

The Roslyn MCP Server is an MCP server for C# code navigation, backed by the Roslyn Language Server.

It gives MCP hosts a focused set of navigation tools for working inside a C# solution or project:

- jump to definitions
- find references
- find implementations
- inspect document symbols
- search workspace symbols
- read source spans

The goal is not to reimplement Roslyn. The server reuses Roslyn as the underlying navigation engine and exposes that capability through MCP.

## Quick Start

### Prerequisites

- Python 3.10+
- .NET SDK
- a working Roslyn Language Server binary or DLL
- a C# `.sln`, `.slnx`, or `.csproj` that Roslyn can load

### Install

```bash
python3 -m pip install -e .
```

If you want to run the LangGraph demo:

```bash
python3 -m pip install -e '.[demo]'
```

### Configure

Copy `config.example.json` to `config.json` and edit the paths:

```json
{
  "server_path": "/absolute/path/to/Microsoft.CodeAnalysis.LanguageServer",
  "solution_or_project_path": "/absolute/or/relative/path/to/your.sln",
  "listen_host": "127.0.0.1",
  "listen_port": 8765
}
```

### Run the MCP Server

```bash
roslyn-mcp-server config.json
```

Or without installation:

```bash
PYTHONPATH=src python3 -m roslyn_mcp_server.main config.json
```

This is the normal product entrypoint.

In the current implementation, the MCP server automatically starts and manages the internal Roslyn runtime it needs.

## Tools

### First Batch

The first batch of tools should be:

- `health`
  - return workspace and server readiness
- `search_symbols`
  - search the workspace for candidate symbols
  - return `symbol_handle` values that can be passed to follow-up tools
- `document_symbols`
  - list symbols declared in a file
  - return `symbol_handle` values for each symbol
- `find_definition_by_symbol`
  - jump to definitions from a `symbol_handle`
- `find_references_by_symbol`
  - find references from a `symbol_handle`
- `find_implementations_by_symbol`
  - find implementations from a `symbol_handle`
- `read_symbol`
  - read the source for a symbol directly
- `read_file`
  - read a file, optionally by line range

These tools are being implemented incrementally. The current server is in a transitional state where both:

- newer symbol-oriented tools
- older position-based tools

may coexist for a period of time.

### Transitional State

The current implementation still contains lower-level position-based tools inherited from the underlying LSP model. Those are implementation-oriented and will be phased down in favor of the symbol-oriented MCP surface above.

Examples of lower-level tools that should not remain the primary MCP interface:

- `find_definition(file_path, line, character)`
- `find_references(file_path, line, character)`
- `find_implementations(file_path, line, character)`
- `read_span(file_path, start_line, start_character, end_line, end_character)`

### Coordinate System

Where coordinates do appear in tool results, they follow LSP semantics:

- `line` is `0-based`
- `character` is `0-based`

## Repository Layout

- `src/roslyn_mcp_server/main.py`
  - MCP server entrypoint
- `src/roslyn_mcp_server/mcp/`
  - MCP transport and tool handlers
- `src/roslyn_mcp_server/backend/`
  - Internal Roslyn runtime and local HTTP transport
- `src/roslyn_mcp_server/application/`
  - Services and request/result models
- `src/roslyn_mcp_server/roslyn/`
  - Roslyn session and LSP transport
- `src/roslyn_mcp_server/infrastructure/`
  - Config and logging
- `misc/langgraph_demo.py`
  - Host-side demo
- `misc/mcp_process_client.py`
  - Minimal MCP client used by demos

## LangGraph Demo

The LangGraph demo is a host-side example. It is not part of the product surface.

Run it with:

```bash
python3 misc/langgraph_demo.py --config config.json
```

It embeds a minimal MCP client, starts the MCP server, and lets you chat continuously in the terminal.

Commands:

- `/reset`
  - clear conversation state
- `/exit`
  - quit the demo
