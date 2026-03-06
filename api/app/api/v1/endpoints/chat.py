"""
WebSocket endpoint for real-time grievance comments.

Clients connect to /ws/grievances/{grievance_id}/comments and receive
JSON messages whenever a new comment is posted (via REST or WS).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db, AsyncSessionLocal as async_session_factory
from app.models.models import Grievance, GrievanceComment, User
from app.core.config import settings
from app.core.security import verify_password
from jose import jwt, JWTError

router = APIRouter()

_connections: dict[str, set[WebSocket]] = defaultdict(set)


def _decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # Backward compatibility: allow tokens where "type" is missing
        token_type = payload.get("type")
        if token_type is not None and token_type != "access":
            return None
        return payload
    except JWTError:
        return None


async def broadcast_comment(grievance_id: str, comment_data: dict):
    """Called from REST endpoint to push new comments to all WS listeners."""
    dead = []
    for ws in _connections.get(grievance_id, set()):
        try:
            await ws.send_json({"type": "new_comment", "comment": comment_data})
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections[grievance_id].discard(ws)


@router.websocket("/ws/grievances/{grievance_id}/comments")
async def grievance_chat(websocket: WebSocket, grievance_id: str):
    await websocket.accept()

    user_id: str | None = None
    user_name: str = "Anonymous"

    _connections[grievance_id].add(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "auth":
                token = data.get("token", "")
                payload = _decode_token(token)
                if payload:
                    user_id = payload.get("sub")
                    async with async_session_factory() as db:
                        result = await db.execute(select(User).where(User.id == user_id))
                        user_obj = result.scalar_one_or_none()
                        if user_obj:
                            user_name = user_obj.name
                    await websocket.send_json({"type": "auth_ok", "user_name": user_name})
                else:
                    await websocket.send_json({"type": "auth_error", "message": "Invalid token"})

            elif msg_type == "comment":
                if not user_id:
                    await websocket.send_json({"type": "error", "message": "Not authenticated"})
                    continue
                text = (data.get("text") or "").strip()
                if not text:
                    continue

                async with async_session_factory() as db:
                    comment = GrievanceComment(
                        grievance_id=uuid.UUID(grievance_id),
                        user_id=uuid.UUID(user_id),
                        text=text,
                    )
                    db.add(comment)
                    await db.commit()
                    await db.refresh(comment)

                    comment_out = {
                        "id": str(comment.id),
                        "user_id": str(comment.user_id),
                        "user_name": user_name,
                        "text": comment.text,
                        "created_at": comment.created_at.isoformat(),
                    }

                await broadcast_comment(grievance_id, comment_out)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        _connections[grievance_id].discard(websocket)
        if not _connections[grievance_id]:
            del _connections[grievance_id]
