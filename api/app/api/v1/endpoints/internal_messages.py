from datetime import datetime, timezone
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, InternalMessage, WorkerProfile
from app.schemas.internal_messages import InternalMessage as MessageSchema, InternalMessageCreate, ConversationMember
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

@router.post("/send", response_model=MessageSchema)
async def send_message(
    message_in: InternalMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify receiver exists
    result = await db.execute(select(User).where(User.id == message_in.receiver_id))
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    
    # Optional: Verify they are in the same department (optional but good for 'personalised department chat')
    # For now, let's just allow sending to anyone if they are staff
    
    new_msg = InternalMessage(
        sender_id=current_user.id,
        receiver_id=message_in.receiver_id,
        content=message_in.content
    )
    db.add(new_msg)
    await db.commit()
    await db.refresh(new_msg)
    return new_msg

@router.get("/thread/{other_user_id}", response_model=List[MessageSchema])
async def get_thread(
    other_user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Mark messages as read
    await db.execute(
        InternalMessage.__table__.update()
        .where(and_(
            InternalMessage.sender_id == other_user_id,
            InternalMessage.receiver_id == current_user.id,
            InternalMessage.is_read == False
        ))
        .values(is_read=True)
    )
    await db.commit()

    query = select(InternalMessage).where(
        or_(
            and_(InternalMessage.sender_id == current_user.id, InternalMessage.receiver_id == other_user_id),
            and_(InternalMessage.sender_id == other_user_id, InternalMessage.receiver_id == current_user.id)
        )
    ).order_by(InternalMessage.created_at.asc())
    
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/conversations", response_model=List[ConversationMember])
async def get_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # This is a bit complex for a simple query, let's find all users current_user has messaged with
    # First, find IDs of people we've chatted with
    sent_to = select(InternalMessage.receiver_id).where(InternalMessage.sender_id == current_user.id)
    received_from = select(InternalMessage.sender_id).where(InternalMessage.receiver_id == current_user.id)
    
    chatted_ids_query = sent_to.union(received_from)
    res = await db.execute(chatted_ids_query)
    chatted_ids = [r[0] for r in res.fetchall()]
    
    if not chatted_ids:
        return []
    
    # Fetch user details for these IDs
    users_query = select(User).where(User.id.in_(chatted_ids))
    users_res = await db.execute(users_query)
    users = users_res.scalars().all()
    
    conversations = []
    for user in users:
        # Get last message
        last_msg_query = select(InternalMessage).where(
            or_(
                and_(InternalMessage.sender_id == current_user.id, InternalMessage.receiver_id == user.id),
                and_(InternalMessage.sender_id == user.id, InternalMessage.receiver_id == current_user.id)
            )
        ).order_by(InternalMessage.created_at.desc()).limit(1)
        last_msg_res = await db.execute(last_msg_query)
        last_msg = last_msg_res.scalar_one_or_none()
        
        # Get unread count
        unread_query = select(func.count(InternalMessage.id)).where(
            and_(
                InternalMessage.sender_id == user.id,
                InternalMessage.receiver_id == current_user.id,
                InternalMessage.is_read == False
            )
        )
        unread_res = await db.execute(unread_query)
        unread_count = unread_res.scalar() or 0
        
        conversations.append(ConversationMember(
            id=user.id,
            name=user.name,
            role=str(user.role),
            last_message=last_msg.content if last_msg else None,
            last_message_time=last_msg.created_at if last_msg else None,
            unread_count=unread_count
        ))
    
    # Sort by last message time
    conversations.sort(key=lambda x: x.last_message_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return conversations

@router.get("/colleagues", response_model=List[ConversationMember])
async def get_colleagues(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Fetch people in the same department
    if not current_user.worker_profile or not current_user.worker_profile.department_id:
        return []
    
    dept_id = current_user.worker_profile.department_id
    query = select(User).join(WorkerProfile, User.id == WorkerProfile.user_id).where(
        and_(
            WorkerProfile.department_id == dept_id,
            User.id != current_user.id
        )
    )
    result = await db.execute(query)
    users = result.scalars().all()
    
    return [
        ConversationMember(
            id=u.id,
            name=u.name,
            role=str(u.role)
        ) for u in users
    ]
