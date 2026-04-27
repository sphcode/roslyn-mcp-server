import json
from pathlib import Path


def resolve_path(raw_value, base_dir):
    path = Path(raw_value)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def load_server_config(config_path):
    config_path = Path(config_path).resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    base_dir = config_path.parent
    config["config_path"] = config_path
    config["server_path"] = resolve_path(config["server_path"], base_dir)
    config["solution_or_project_path"] = resolve_path(
        config["solution_or_project_path"], base_dir
    )
    config["listen_host"] = config.get("listen_host", "127.0.0.1")
    config["listen_port"] = int(config.get("listen_port", 0))
    roslyn_timeouts = dict(config.get("roslyn_timeouts", {}))
    roslyn_timeouts["request_seconds"] = int(
        roslyn_timeouts.get("request_seconds", 30)
    )
    roslyn_timeouts["search_symbols_seconds"] = int(
        roslyn_timeouts.get("search_symbols_seconds", 120)
    )
    roslyn_timeouts["initialize_seconds"] = int(
        roslyn_timeouts.get("initialize_seconds", 30)
    )
    roslyn_timeouts["workspace_ready_seconds"] = int(
        roslyn_timeouts.get("workspace_ready_seconds", 60)
    )
    config["roslyn_timeouts"] = roslyn_timeouts
    langgraph_demo = dict(config.get("langgraph_demo", {}))
    langgraph_demo["model"] = langgraph_demo.get("model", "gpt-4.1-mini")
    langgraph_demo["api_key"] = langgraph_demo.get("api_key")
    langgraph_demo["base_url"] = langgraph_demo.get("base_url")
    config["langgraph_demo"] = langgraph_demo
    return config
