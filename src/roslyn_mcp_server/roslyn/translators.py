import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


class InvalidSymbolHandleError(ValueError):
    pass


def path_to_uri(path):
    return Path(path).resolve().as_uri()


def uri_to_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None

    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc != "localhost":
        path = f"//{parsed.netloc}{path}"
    if len(path) >= 3 and path[0] == "/" and path[1].isalpha() and path[2] == ":":
        return path[1:]
    return path


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


def create_symbol_handle(
    *,
    file_path,
    line,
    character,
    name,
    kind,
    container_name=None,
    range_value=None,
    selection_range=None,
):
    payload = {
        "v": 1,
        "file_path": str(Path(file_path)),
        "line": int(line),
        "character": int(character),
        "name": name,
        "kind": kind,
    }
    if container_name is not None:
        payload["container_name"] = container_name
    if range_value is not None:
        payload["range"] = range_value
    if selection_range is not None:
        payload["selection_range"] = selection_range

    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    checksum = hashlib.sha256(encoded_payload.encode("ascii")).hexdigest()[:16]
    return f"sym:{encoded_payload}.{checksum}"


def parse_symbol_handle(symbol_handle):
    if not isinstance(symbol_handle, str) or not symbol_handle.startswith("sym:"):
        raise InvalidSymbolHandleError("Invalid symbol_handle")

    encoded = symbol_handle[4:]
    if "." not in encoded:
        raise InvalidSymbolHandleError("Invalid symbol_handle")

    encoded_payload, checksum = encoded.rsplit(".", 1)
    expected_checksum = hashlib.sha256(encoded_payload.encode("ascii")).hexdigest()[:16]
    if checksum != expected_checksum:
        raise InvalidSymbolHandleError("Invalid symbol_handle")

    padding = "=" * (-len(encoded_payload) % 4)
    try:
        payload = json.loads(
            base64.urlsafe_b64decode((encoded_payload + padding).encode("ascii")).decode("utf-8")
        )
    except Exception as exc:
        raise InvalidSymbolHandleError("Invalid symbol_handle") from exc

    required_fields = {"file_path", "line", "character", "name", "kind"}
    if not required_fields.issubset(payload):
        raise InvalidSymbolHandleError("Invalid symbol_handle")
    return payload


def _normalize_location(uri, range_value):
    if uri is None:
        return None
    return {
        "uri": uri,
        "path": uri_to_path(uri),
        "range": _normalize_range(range_value),
    }


def _symbol_anchor(range_value, selection_range=None):
    effective_range = selection_range or range_value
    if effective_range is None:
        return None
    return effective_range["start"]["line"], effective_range["start"]["character"]


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

        location_range = None
        file_path = None
        if symbol["location"] is not None:
            file_path = symbol["location"].get("path")
            location_range = symbol["location"].get("range")
        anchor = _symbol_anchor(location_range)
        if file_path is not None and anchor is not None:
            symbol["symbol_handle"] = create_symbol_handle(
                file_path=file_path,
                line=anchor[0],
                character=anchor[1],
                name=symbol["name"],
                kind=symbol["kind"],
                container_name=symbol["container_name"],
                range_value=location_range,
            )
        else:
            symbol["symbol_handle"] = None

        normalized.append(symbol)

    return normalized


def normalize_document_symbols(raw_result, file_path):
    if raw_result is None:
        return []

    resolved_file_path = str(Path(file_path).resolve())
    normalized = []
    for item in raw_result:
        if "location" in item:
            location = _normalize_location(
                item["location"]["uri"],
                item["location"].get("range"),
            )
            anchor = _symbol_anchor(location["range"])
            normalized.append(
                {
                    "name": item.get("name"),
                    "kind": item.get("kind"),
                    "tags": item.get("tags", []),
                    "container_name": item.get("containerName"),
                    "file_path": resolved_file_path,
                    "location": location,
                    "symbol_handle": create_symbol_handle(
                        file_path=resolved_file_path,
                        line=anchor[0],
                        character=anchor[1],
                        name=item.get("name"),
                        kind=item.get("kind"),
                        container_name=item.get("containerName"),
                        range_value=location["range"],
                    ),
                }
            )
            continue

        normalized.append(_normalize_document_symbol(item, resolved_file_path))

    return normalized


def _normalize_document_symbol(item, file_path, container_name=None):
    range_value = _normalize_range(item.get("range"))
    selection_range = _normalize_range(item.get("selectionRange"))
    anchor = _symbol_anchor(range_value, selection_range)
    return {
        "name": item.get("name"),
        "detail": item.get("detail"),
        "kind": item.get("kind"),
        "tags": item.get("tags", []),
        "deprecated": bool(item.get("deprecated", False)),
        "container_name": container_name,
        "file_path": file_path,
        "range": range_value,
        "selection_range": selection_range,
        "symbol_handle": create_symbol_handle(
            file_path=file_path,
            line=anchor[0],
            character=anchor[1],
            name=item.get("name"),
            kind=item.get("kind"),
            container_name=container_name,
            range_value=range_value,
            selection_range=selection_range,
        )
        if anchor is not None
        else None,
        "children": [
            _normalize_document_symbol(
                child,
                file_path,
                item.get("name"),
            )
            for child in item.get("children", [])
        ],
    }
