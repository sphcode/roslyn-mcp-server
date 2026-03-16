from pathlib import Path
from urllib.parse import unquote, urlparse


def path_to_uri(path):
    return Path(path).resolve().as_uri()


def uri_to_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return unquote(parsed.path)


def normalize_lsp_locations(raw_result):
    if raw_result is None:
        return []
    if isinstance(raw_result, dict):
        raw_result = [raw_result]

    normalized = []
    for item in raw_result:
        if "targetUri" in item:
            uri = item["targetUri"]
            normalized_item = {
                "uri": uri,
                "path": uri_to_path(uri),
                "range": item.get("targetRange"),
            }
            if "targetSelectionRange" in item:
                normalized_item["selection_range"] = item["targetSelectionRange"]
            if "originSelectionRange" in item:
                normalized_item["origin_selection_range"] = item["originSelectionRange"]
        else:
            uri = item["uri"]
            normalized_item = {
                "uri": uri,
                "path": uri_to_path(uri),
                "range": item.get("range"),
            }
        normalized.append(normalized_item)

    return normalized
