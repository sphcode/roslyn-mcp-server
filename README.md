# roslyn_mcp_server

Minimal Roslyn-based navigation server.

Install:
- `python3 -m pip install -e .`

Entrypoints:
- `roslyn-mcp-server config.json`
- `roslyn-mcp-client --config config.json health`

Structure:
- `src/roslyn_mcp_server/main.py`: server entrypoint
- `src/roslyn_mcp_server/mcp/`: transport and tool-facing handlers
- `src/roslyn_mcp_server/application/`: services and request/result models
- `src/roslyn_mcp_server/roslyn/`: Roslyn session and LSP adapter
- `src/roslyn_mcp_server/infrastructure/`: config and logging
- `scripts/client.py`: local debug CLI for the HTTP bridge
