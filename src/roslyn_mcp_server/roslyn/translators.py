from pathlib import Path
from urllib.parse import unquote, urlparse


def path_to_uri(path):
    return Path(path).resolve().as_uri()


def uri_to_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return unquote(parsed.path)


def _normalize_range(range_value):
    if range_value is None:
        return None
    return {
        "start": {
            "line": range_value["start"]["line"],
            "character": range_value["start"]["character"],
        },
        "end": {
            "line": range_value["end"]["line"],
            "character": range_value["end"]["character"],
        },
    }


def _normalize_location(uri, range_value):
    if uri is None:
        return None
    return {
        "uri": uri,
        "path": uri_to_path(uri),
        "range": _normalize_range(range_value),
    }


def normalize_lsp_locations(raw_result):
    if raw_result is None:
        return []
    if isinstance(raw_result, dict):
        raw_result = [raw_result]

    normalized = []
    for item in raw_result:
        if "targetUri" in item:
            normalized_item = _normalize_location(
                item["targetUri"],
                item.get("targetRange"),
            )
            normalized_item["selection_range"] = _normalize_range(
                item.get("targetSelectionRange")
            )
            normalized_item["origin_selection_range"] = _normalize_range(
                item.get("originSelectionRange")
            )
        else:
            normalized_item = _normalize_location(item["uri"], item.get("range"))
        normalized.append(normalized_item)

    return normalized


def normalize_workspace_symbols(raw_result):
    if raw_result is None:
        return []

    normalized = []
    for item in raw_result:
        symbol = {
            "name": item.get("name"),
            "kind": item.get("kind"),
            "tags": item.get("tags", []),
            "container_name": item.get("containerName"),
        }

        location = item.get("location")
        if isinstance(location, dict):
            if "uri" in location:
                symbol["location"] = _normalize_location(
                    location["uri"],
                    location.get("range"),
                )
            else:
                uri = location.get("targetUri") or location.get("uri")
                symbol["location"] = _normalize_location(
                    uri,
                    location.get("targetRange") or location.get("range"),
                )
        elif isinstance(location, str):
            symbol["location"] = _normalize_location(location, None)
        else:
            symbol["location"] = None

        normalized.append(symbol)

    return normalized


def normalize_document_symbols(raw_result):
    if raw_result is None:
        return []

    normalized = []
    for item in raw_result:
        if "location" in item:
            normalized.append(
                {
                    "name": item.get("name"),
                    "kind": item.get("kind"),
                    "tags": item.get("tags", []),
                    "container_name": item.get("containerName"),
                    "location": _normalize_location(
                        item["location"]["uri"],
                        item["location"].get("range"),
                    ),
                }
            )
            continue

        normalized.append(_normalize_document_symbol(item))

    return normalized


def _normalize_document_symbol(item):
    return {
        "name": item.get("name"),
        "detail": item.get("detail"),
        "kind": item.get("kind"),
        "tags": item.get("tags", []),
        "deprecated": bool(item.get("deprecated", False)),
        "range": _normalize_range(item.get("range")),
        "selection_range": _normalize_range(item.get("selectionRange")),
        "children": [
            _normalize_document_symbol(child)
            for child in item.get("children", [])
        ],
    }
