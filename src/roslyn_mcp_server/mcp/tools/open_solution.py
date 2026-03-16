from pathlib import Path

from roslyn_mcp_server.application.models.requests import OpenSolutionRequest


def handle(workspace_service, payload):
    request = OpenSolutionRequest(
        solution_or_project_path=Path(payload["solution_or_project_path"])
    )
    result = workspace_service.open_solution(request)
    return {
        "workspace": str(result.workspace),
        "status": result.status,
        "last_error": result.last_error,
    }
