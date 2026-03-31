# roslyn_mcp_server

Roslyn-backed MCP adapter for C# navigation.

Architecture:
- `backend daemon`
  - Owns the Roslyn process and workspace state.
  - Exposes a local HTTP API for `health`, `find_definition`, `find_references`, `find_implementations`, `document_symbols`, `search_symbols`, and `read_span`.
- `MCP stdio adapter`
  - Does not own Roslyn state.
  - Receives MCP tool calls and forwards them to the backend daemon.

Install:
- `python3 -m pip install -e .`
- LangGraph demo:
  - `python3 -m pip install -e '.[demo]'`

Entrypoints:
- `roslyn-mcp-backend config.json`
  - Runs the Roslyn backend daemon.
- `roslyn-mcp-server config.json`
  - Runs the MCP stdio adapter.
- `roslyn-mcp-client --config config.json health`
  - Calls the backend daemon directly over HTTP.

MCP tools:
- `health`
- `find_definition`
- `find_references`
- `find_implementations`
- `document_symbols`
- `search_symbols`
- `read_span`

Coordinate system:
- All `line` and `character` fields are `0-based`, matching LSP.

Timeouts:
- `search_symbols` uses a longer Roslyn timeout by default because `workspace/symbol` can be much slower on real solutions.
- Optional config:
  - `roslyn_timeouts.request_seconds`
  - `roslyn_timeouts.search_symbols_seconds`
  - `roslyn_timeouts.initialize_seconds`
  - `roslyn_timeouts.workspace_ready_seconds`

Testing:
- `pytest` now runs real integration tests against:
  - a real backend daemon process
  - a real MCP adapter process
  - the real Roslyn Language Server from `config.json`
- To enable real `find_definition` and `find_references` tests, set:
  - `ROSLYN_MCP_TEST_FILE_PATH`
  - `ROSLYN_MCP_TEST_LINE`
  - `ROSLYN_MCP_TEST_CHARACTER`

Structure:
- `src/roslyn_mcp_server/backend/`: backend daemon and HTTP client
- `src/roslyn_mcp_server/main.py`: MCP stdio adapter entrypoint
- `src/roslyn_mcp_server/mcp/`: MCP transport and tool handlers
- `src/roslyn_mcp_server/application/`: services and request/result models
- `src/roslyn_mcp_server/roslyn/`: Roslyn session and LSP adapter
- `src/roslyn_mcp_server/infrastructure/`: config, logging, and compatibility wrapper for the old HTTP bridge path

Examples:
- Start the backend:
  - `PYTHONPATH=src python3 -m roslyn_mcp_server.backend.server config.json`
- Search workspace symbols:
  - `PYTHONPATH=src python3 -m roslyn_mcp_server.client_cli --config config.json search-symbols --query IDataContractCalculator`
- List document symbols:
  - `PYTHONPATH=src python3 -m roslyn_mcp_server.client_cli --config config.json document-symbols --file /absolute/path/to/file.cs`
- Find implementations from an interface or abstract member position:
  - `PYTHONPATH=src python3 -m roslyn_mcp_server.client_cli --config config.json implementations --file /absolute/path/to/file.cs --line 10 --character 15`
- Run the LangGraph demo:
  - `python3 misc/langgraph_demo.py --config config.json`
  - Then chat continuously in the terminal when you see `Prompt>`.
  - Use `/reset` to clear context and `/exit` to quit.
