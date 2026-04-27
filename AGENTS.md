# Repository Guidelines

## Project Structure & Module Organization

This Python 3.10+ package uses a `src/` layout. Product code lives in `src/roslyn_mcp_server/`:

- `main.py` exposes the MCP server entrypoint.
- `mcp/` contains the MCP server and tool handlers.
- `backend/` manages the internal Roslyn runtime and HTTP transport.
- `application/` contains service logic plus request/result models.
- `roslyn/` contains Roslyn session, LSP adapter, and translators.
- `infrastructure/` contains config, logging, and bridge utilities.

Tests belong in `tests/`. Demo and experimental host-side scripts belong in `misc/`; keep them out of the product API surface.

## Architecture Boundaries

- `mcp/` should contain MCP protocol-facing handlers only.
- `application/` should contain service orchestration, request/result models, and business logic.
- `roslyn/` should contain Roslyn session, LSP adapter, and translation logic.
- `backend/` should manage Roslyn runtime process lifecycle and HTTP transport.
- `infrastructure/` should contain configuration, logging, and shared utilities.
- Keep tool handlers thin: parse/validate input, call application services, return structured results.
- Prefer adding tests around translators, config parsing, and service behavior before changing Roslyn-backed flows.

## Build, Test, and Development Commands

- `python3 -m pip install -e .` installs the package and console scripts in editable mode.
- `python3 -m pip install -e '.[dev]'` installs development dependencies, currently `pytest`.
- `python3 -m pip install -e '.[demo]'` installs LangGraph demo dependencies.
- `roslyn-mcp-server config.json` runs the MCP server.
- `PYTHONPATH=src python3 -m roslyn_mcp_server.main config.json` runs without installing.
- `python3 -m pytest` runs the test suite configured by `pyproject.toml`.
- `python3 misc/langgraph_demo.py --config config.json` runs the interactive demo.

## Coding Style & Naming Conventions

Follow idiomatic Python with 4-space indentation, type hints for public/service boundaries, and small modules organized by responsibility. Use `snake_case` for modules, functions, variables, and tool names; use `PascalCase` for classes and data models. Keep MCP tool handlers thin: validate inputs, call application services, and return structured results. Avoid adding dependencies unless they clearly simplify production code.

## Testing Guidelines

Use `pytest` and place tests under `tests/` with names like `test_translators.py` or `test_workspace_service.py`. Prefer focused unit tests for translators, request/result models, config parsing, and service behavior. For Roslyn-backed flows, isolate external process requirements behind fixtures or mark them clearly so the default `python3 -m pytest` remains practical.

## Commit & Pull Request Guidelines

Git history uses Conventional Commit-style subjects such as `fix: harden read_symbol resolution`, `feat: Add symbol-oriented MCP tools`, and `refactor: Align project surfaces with MCP architecture`. Keep commits scoped.

Pull requests should include a concise description, the commands run for verification, any config or Roslyn/.NET prerequisites, and linked issues when applicable. Include screenshots or terminal excerpts only when behavior is difficult to understand from text.

## Security & Configuration Tips

Do not commit local `config.json`, logs, virtual environments, or absolute machine-specific paths. Use `config.example.json` to document expected keys, and keep secrets or private workspace paths outside tracked files.

## Agent Operating Rules

- Before changing code, inspect the relevant files and explain the intended approach unless the task is trivial.
- Keep changes minimal and scoped to the requested task.
- Do not rewrite unrelated modules.
- Do not add dependencies without explicit approval.
- Do not modify generated files, local config files, logs, virtual environments, or machine-specific paths.
- Prefer application/service-layer changes over adding logic directly to MCP tool handlers.
- After code changes, run `python3 -m pytest` when practical.
- If tests cannot be run, explain why and list the unverified risk.
- At the end of each task, summarize:
  - files changed
  - behavior changed
  - tests run
  - remaining risks