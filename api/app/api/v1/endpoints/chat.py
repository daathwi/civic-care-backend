"""
WebSocket endpoint for real-time grievance comments AND internal staff conversations.

Clients connect to /ws/grievances/{grievance_id}/comments or /ws/conversations/{conversation_id}/messages
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db, AsyncSessionLocal as async_session_factory
from app.models.models import Grievance, GrievanceComment, User, InternalMessage, ConversationParticipant, Conversation
from app.core.config import settings
from jose import jwt, JWTError

from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.chat_service import ask_database_stream

class ChatRequest(BaseModel):
    message: str

router = APIRouter()

_connections: dict[str, set[WebSocket]] = defaultdict(set)
_conv_connections: dict[str, set[WebSocket]] = defaultdict(set)


def _decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_type = payload.get("type")
        if token_type is not None and token_type != "access":
            return None
        return payload
    except JWTError:
        return None


async def broadcast_comment(grievance_id: str, comment_data: dict):
    """Called from REST endpoint to push new comments to all WS listeners."""
    print(f"DEBUG: Broadcasting comment for grievance {grievance_id}. Data: {comment_data}")
    dead = []
    conns = _connections.get(grievance_id, set())
    print(f"DEBUG: Found {len(conns)} active connections for grievance {grievance_id}")
    for ws in conns:
        try:
            await ws.send_json({"type": "new_comment", "comment": comment_data})
            print(f"DEBUG: Sent JSON to {ws.client}")
        except Exception as e:
            print(f"DEBUG: Failed to send to {ws.client}: {e}")
            dead.append(ws)
    for ws in dead:
        _connections[grievance_id].discard(ws)


async def broadcast_internal_message(conversation_id: str, message_data: dict):
    dead = []
    for ws in _conv_connections.get(conversation_id, set()):
        try:
            await ws.send_json({"type": "new_message", "message": message_data})
        except Exception:
            dead.append(ws)
    for ws in dead:
        _conv_connections[conversation_id].discard(ws)


@router.websocket("/ws/grievances/{grievance_id}/comments")
async def grievance_chat(websocket: WebSocket, grievance_id: str):
    print(f"DEBUG: Local WS connection attempt for grievance {grievance_id}")
    await websocket.accept()
    print(f"DEBUG: WS connection accepted for grievance {grievance_id}")

    user_id: str | None = None
    user_name: str = "Anonymous"

    _connections[grievance_id].add(websocket)
    print(f"DEBUG: Added {websocket.client} to connections for {grievance_id}. Total: {len(_connections[grievance_id])}")
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


@router.websocket("/ws/conversations/{conversation_id}/messages")
async def internal_conversation_chat(websocket: WebSocket, conversation_id: str):
    await websocket.accept()

    user_id: str | None = None
    user_name: str = "Anonymous"
    is_participant = False

    _conv_connections[conversation_id].add(websocket)
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
                        # Verify user exists and is a participant in this conversation
                        result = await db.execute(select(User).where(User.id == user_id))
                        user_obj = result.scalar_one_or_none()
                        if user_obj:
                            user_name = user_obj.name
                        
                        part_res = await db.execute(
                            select(ConversationParticipant).where(
                                and_(
                                    ConversationParticipant.conversation_id == uuid.UUID(conversation_id),
                                    ConversationParticipant.user_id == uuid.UUID(user_id)
                                )
                            )
                        )
                        if part_res.scalar_one_or_none():
                            is_participant = True
                        else:
                            # If it's a task/grievance conversation, allow staff to auto-join like REST endpoint does
                            conv_res = await db.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation_id)))
                            conv = conv_res.scalar_one_or_none()
                            if conv and conv.type == "task":
                                db.add(ConversationParticipant(conversation_id=uuid.UUID(conversation_id), user_id=uuid.UUID(user_id)))
                                await db.commit()
                                is_participant = True

                    if is_participant:
                        await websocket.send_json({"type": "auth_ok", "user_name": user_name})
                    else:
                        await websocket.send_json({"type": "auth_error", "message": "Not a conversation participant"})
                else:
                    await websocket.send_json({"type": "auth_error", "message": "Invalid token"})

            elif msg_type == "message":
                if not user_id or not is_participant:
                    await websocket.send_json({"type": "error", "message": "Not authenticated or lacking participant access"})
                    continue
                content = (data.get("content") or "").strip()
                if not content:
                    continue

                async with async_session_factory() as db:
                    new_msg = InternalMessage(
                        sender_id=uuid.UUID(user_id),
                        conversation_id=uuid.UUID(conversation_id),
                        content=content
                    )
                    db.add(new_msg)
                    
                    # Increment unread for everyone else in the conversation
                    await db.execute(
                        ConversationParticipant.__table__.update()
                        .where(and_(
                            ConversationParticipant.conversation_id == uuid.UUID(conversation_id),
                            ConversationParticipant.user_id != uuid.UUID(user_id)
                        ))
                        .values(unread_count=ConversationParticipant.unread_count + 1)
                    )
                    
                    await db.commit()
                    await db.refresh(new_msg)

                    msg_out = {
                        "id": str(new_msg.id),
                        "sender_id": str(new_msg.sender_id),
                        "receiver_id": str(new_msg.receiver_id) if new_msg.receiver_id else "",
                        "sender_name": user_name,
                        "content": new_msg.content,
                        "is_read": new_msg.is_read,
                        "created_at": new_msg.created_at.isoformat(),
                    }

                await broadcast_internal_message(conversation_id, msg_out)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        _conv_connections[conversation_id].discard(websocket)
        if not _conv_connections[conversation_id]:
            del _conv_connections[conversation_id]

@router.post("/stream")
async def stream_chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream a response from the AI assistant, executing required database queries.
    Expects request body: {"message": "question here"}
    """
    return StreamingResponse(
        ask_database_stream(db, req.message),
        media_type="text/event-stream"
    )
