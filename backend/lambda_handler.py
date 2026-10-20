"""AWS Lambda entry point (Function URL, payload v2). Also runs async story jobs when AgentCore is not configured."""

from __future__ import annotations

import base64
import logging

from crayon import generator
from crayon.api import Request, handle

logging.getLogger().setLevel(logging.INFO)


def handler(event, context):
    if "crayon_job" in event:  # async self-invocation: generate a story in the background
        generator.generate_story(event["crayon_job"])
        return {"ok": True}

    http = event.get("requestContext", {}).get("http", {})
    body = event.get("body") or ""
    raw = base64.b64decode(body) if event.get("isBase64Encoded") else body.encode()
    req = Request(
        method=http.get("method", "GET"),
        path=event.get("rawPath", "/"),
        query=event.get("queryStringParameters") or {},
        headers={k.lower(): v for k, v in (event.get("headers") or {}).items()},
        body=raw,
    )
    resp = handle(req)
    text_like = resp.headers.get("content-type", "").startswith(("application/json", "text/", "image/svg"))
    return {
        "statusCode": resp.status,
        "headers": resp.headers,
        "body": resp.body.decode() if text_like else base64.b64encode(resp.body).decode(),
        "isBase64Encoded": not text_like,
    }
