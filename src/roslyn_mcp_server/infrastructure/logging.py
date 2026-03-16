import json
import sys
import time


def log(prefix, payload):
    timestamp = time.strftime("%H:%M:%S")
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, ensure_ascii=False, indent=2)
    print(f"[{timestamp}] {prefix}: {payload}", file=sys.stderr, flush=True)
