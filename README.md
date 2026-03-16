# roslyn_mcp_server

Roslyn-backed MCP adapter for C# navigation.

Architecture:
- `backend daemon`
  - Owns the Roslyn process and workspace state.
  - Exposes a local HTTP API for `health`, `find_definition`, `find_references`, and `read_span`.
- `MCP stdio adapter`
  - Does not own Roslyn state.
  - Receives MCP tool calls and forwards them to the backend daemon.

Install:
- `python3 -m pip install -e .`

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
- `read_span`

Coordinate system:
- All `line` and `character` fields are `0-based`, matching LSP.

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
- `scripts/client.py`: local CLI wrapper for the backend daemon
