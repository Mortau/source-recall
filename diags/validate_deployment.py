#!/usr/bin/env python3
"""Validate a deployed SourceRecall API and optionally one search path."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "status": response.status, "body": payload}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw[:500]
        return {"ok": False, "status": exc.code, "body": payload}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8070")
    parser.add_argument("--api-token")
    parser.add_argument("--repository")
    parser.add_argument("--query", default="application entry point")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = parse_args(arguments)
    base_url = args.api_url.rstrip("/")
    checks = {
        "live": request_json(f"{base_url}/live"),
        "ready": request_json(f"{base_url}/ready"),
        "status": request_json(f"{base_url}/status", token=args.api_token),
        "repositories": request_json(f"{base_url}/repositories", token=args.api_token),
    }
    if args.repository:
        checks["search"] = request_json(
            f"{base_url}/search",
            method="POST",
            body={
                "repository": args.repository,
                "query": args.query,
                "limit": 3,
            },
            token=args.api_token,
        )
    passed = all(check.get("ok") for check in checks.values())
    report = {
        "schema": "source-recall-deployment-validation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": base_url,
        "passed": passed,
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": passed, "output": str(args.output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
