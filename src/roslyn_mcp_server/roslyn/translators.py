from pathlib import Path


def path_to_uri(path):
    return Path(path).resolve().as_uri()
