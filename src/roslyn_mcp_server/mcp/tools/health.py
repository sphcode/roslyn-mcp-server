def handle(workspace_service, _payload):
    result = workspace_service.health()
    return {
        "workspace": str(result.workspace),
        "status": result.status,
        "last_error": result.last_error,
    }
