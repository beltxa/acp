from __future__ import annotations

import json
import sys
from typing import Any

from .common import CliUserError


def emit_result(result: dict[str, Any], *, json_output: bool) -> None:
    payload = _strip_meta(result)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    human = result.get("_human")
    if isinstance(human, str):
        print(human)
        return
    if isinstance(human, list):
        print("\n".join(str(line) for line in human))
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def emit_error(exc: Exception, *, json_output: bool) -> None:
    if isinstance(exc, CliUserError):
        message = exc.message
        code = exc.code
        details = exc.details
    else:
        message = str(exc)
        code = "internal_error"
        details = None

    if json_output:
        body: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if details:
            body["error"]["details"] = details
        print(json.dumps(body, indent=2, sort_keys=True), file=sys.stderr)
        return

    print(f"Error [{code}]: {message}", file=sys.stderr)
    if details:
        for key in sorted(details):
            print(f"  {key}: {details[key]}", file=sys.stderr)


def _strip_meta(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if not key.startswith("_")}
