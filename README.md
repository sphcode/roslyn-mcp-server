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
- `roslyn-mcp-langgraph-demo --config config.json`
  - Runs a minimal LangGraph-based agent demo against the backend daemon.

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
  - `roslyn-mcp-langgraph-demo --config config.json`
  - Then type your prompt in the terminal when you see `Prompt>`.

LangGraph demo notes:
- The demo uses `langchain.agents.create_agent`, which runs on LangGraph.
- It connects to the existing backend daemon over local HTTP. Start `roslyn-mcp-backend` first.
- It uses `langchain_openai.ChatOpenAI`.
- LangGraph model config comes from `config.json` under `langgraph_demo`.
- Prompt is entered interactively in the terminal, not passed as a CLI argument.
- System prompt is hardcoded in [langgraph_demo.py](/Users/sunpuhua/now/work/statestreet/roslyn/src/roslyn_mcp_server/langgraph_demo.py).
- `langgraph_demo.model` defaults to `gpt-4.1-mini` if omitted.
- `langgraph_demo.api_key` must be set in `config.json`.
- `langgraph_demo.base_url` is optional and is where you put an OpenAI-compatible proxy endpoint.
