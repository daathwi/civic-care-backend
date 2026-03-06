"""
Middleware to log request payloads and execution results using the formal logger.
Captures request bodies for debugging without cluttering logs with large response bodies.
"""
import json
import logging
from typing import Callable

from starlette.types import ASGIApp

logger = logging.getLogger("app.middleware.request_logger")

def _safe_preview(text: str, max_len: int = 1500) -> str:
    if not text:
        return "(empty)"
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated, total {len(text)} chars]"


async def _log_request_receive(receive, method: str, path: str, query: str):
    """Capture request body, log it, and pass it back to the app."""
    body_chunks = []
    more_body = True
    while more_body:
        message = await receive()
        if message["type"] == "http.request":
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        else:
            yield message
            return

    body = b"".join(body_chunks)
    full_path = f"{path}{f'?{query}' if query else ''}"
    
    if method in ("POST", "PUT", "PATCH") and body:
        try:
            payload = json.loads(body.decode("utf-8"))
            # Mask sensitive fields if necessary (best practice)
            if "password" in payload:
                payload["password"] = "*****"
            payload_str = json.dumps(payload)
        except Exception:
            payload_str = body.decode("utf-8", errors="replace")
        
        logger.info(f"REQUEST: {method} {full_path} | Payload: {_safe_preview(payload_str)}")
    else:
        logger.info(f"REQUEST: {method} {full_path}")

    yield {"type": "http.request", "body": body, "more_body": False}

    while True:
        message = await receive()
        yield message
        if message.get("type") == "http.disconnect":
            break


class RequestResponseLoggerMiddleware:
    """
    ASGI middleware that logs request payloads and response status.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        query = scope.get("query_string", b"").decode("utf-8")
        full_path = f"{path}{f'?{query}' if query else ''}"

        # Setup request body capture
        gen = _log_request_receive(receive, method, path, query)
        first = [True]

        async def receive_wrapper():
            if first[0]:
                first[0] = False
                try:
                    return await gen.__anext__()
                except StopAsyncIteration:
                    return {"type": "http.disconnect"}
            try:
                return await gen.__anext__()
            except StopAsyncIteration:
                return {"type": "http.disconnect"}

        response_status = [500]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_status[0] = message.get("status", 0)
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)

        # Log completion summary
        status = response_status[0]
        status_msg = "SUCCESS" if 200 <= status < 300 else "ERROR" if status >= 400 else "INFO"
        logger.info(f"FINISHED: {method} {full_path} -> [{status} {status_msg}]")
