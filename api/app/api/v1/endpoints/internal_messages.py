import logging
import traceback
from datetime import datetime, timezone
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.models import User, InternalMessage, WorkerProfile, Conversation, ConversationParticipant, Grievance
from app.schemas.internal_messages import InternalMessage as MessageSchema, InternalMessageCreate, ConversationMember, ConversationSchema
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

def _get_role_name(user: User) -> str:
    r = getattr(user, "role", "citizen")
    return getattr(r, "value", r) if hasattr(r, "value") else str(r)

@router.post(
    "/send",
    response_model=MessageSchema,
    summary="Send a private message",
    description="Send a direct message to another user in the system.",
    operation_id="sendDirectMessage",
)
async def send_message(
    message_in: InternalMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find or create DM conversation
    u1_id = current_user.id
    u2_id = message_in.receiver_id
    
    # Verify receiver exists
    result = await db.execute(select(User).where(User.id == u2_id))
    receiver = result.scalar_one_or_none()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")

    # Find a conversation where both u1 and u2 are participants
    conv_query = select(Conversation).join(ConversationParticipant).where(
        ConversationParticipant.user_id.in_([u1_id, u2_id])
    ).group_by(Conversation.id).having(func.count(ConversationParticipant.user_id) == 2)
    
    conv_res = await db.execute(conv_query)
    conv = conv_res.scalar_one_or_none()
    
    if not conv:
        conv = Conversation(type="dm")
        db.add(conv)
        await db.flush()
        
        db.add(ConversationParticipant(conversation_id=conv.id, user_id=u1_id))
        db.add(ConversationParticipant(conversation_id=conv.id, user_id=u2_id))
    
    new_msg = InternalMessage(
        sender_id=u1_id,
        receiver_id=u2_id, # Keep for compatibility
        conversation_id=conv.id,
        content=message_in.content
    )
    db.add(new_msg)
    
    # Update unread count for receiver
    await db.execute(
        ConversationParticipant.__table__.update()
        .where(and_(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == u2_id
        ))
        .values(unread_count=ConversationParticipant.unread_count + 1)
    )
    
    await db.commit()
    await db.refresh(new_msg)
    return new_msg

@router.get(
    "/thread/{other_user_id}",
    response_model=List[MessageSchema],
    summary="Read message thread",
    description="Get the full history of messages between you and another user.",
    operation_id="fetchMessageThread",
)
async def get_thread(
    other_user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find conversation
    conv_query = select(Conversation.id).join(ConversationParticipant).where(
        ConversationParticipant.user_id.in_([current_user.id, other_user_id])
    ).group_by(Conversation.id).having(func.count(ConversationParticipant.user_id) == 2)
    
    conv_res = await db.execute(conv_query)
    conv_id = conv_res.scalar_one_or_none()
    
    if not conv_id:
        return []

    # Reset unread count for current user
    await db.execute(
        ConversationParticipant.__table__.update()
        .where(and_(
            ConversationParticipant.conversation_id == conv_id,
            ConversationParticipant.user_id == current_user.id
        ))
        .values(unread_count=0)
    )
    
    # Mark messages as read
    await db.execute(
        InternalMessage.__table__.update()
        .where(and_(
            InternalMessage.conversation_id == conv_id,
            InternalMessage.receiver_id == current_user.id,
            InternalMessage.is_read == False
        ))
        .values(is_read=True)
    )
    await db.commit()

    query = select(InternalMessage).where(
        InternalMessage.conversation_id == conv_id
    ).order_by(InternalMessage.created_at.asc())
    
    result = await db.execute(query)
    return result.scalars().all()

@router.get(
    "/conversations",
    response_model=List[ConversationMember],
    summary="List your conversations",
    description="See all the ongoing discussions you are involved in.",
    operation_id="listActiveConversations",
)
async def get_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # Get all conversations where current_user is a participant
        query = select(Conversation).join(ConversationParticipant).where(
            ConversationParticipant.user_id == current_user.id
        ).order_by(Conversation.updated_at.desc())
        
        result = await db.execute(query)
        conversations_list = result.scalars().all()
        
        results = []
        for conv in conversations_list:
            # For DM, find the other participant
            other_participant_query = select(User).join(ConversationParticipant).where(
                and_(
                    ConversationParticipant.conversation_id == conv.id,
                    ConversationParticipant.user_id != current_user.id
                )
            )
            other_user_res = await db.execute(other_participant_query)
            other_user = other_user_res.scalar_one_or_none()
            
            if not other_user:
                continue
                
            # Get last message from conv
            last_msg_query = select(InternalMessage).where(
                InternalMessage.conversation_id == conv.id
            ).order_by(InternalMessage.created_at.desc()).limit(1)
            last_msg_res = await db.execute(last_msg_query)
            last_msg = last_msg_res.scalar_one_or_none()
            
            # Get unread count for current user in this conv
            unread_query = select(ConversationParticipant.unread_count).where(
                and_(
                    ConversationParticipant.conversation_id == conv.id,
                    ConversationParticipant.user_id == current_user.id
                )
            )
            unread_res = await db.execute(unread_query)
            unread_count = unread_res.scalar() or 0
            
            results.append(ConversationMember(
                id=other_user.id,
                name=other_user.name,
                role=_get_role_name(other_user),
                last_message=last_msg.content if last_msg else None,
                last_message_time=last_msg.created_at if last_msg else None,
                unread_count=unread_count
            ))
            
        return results
    except Exception as e:
        logger.error(f"Error in get_conversations: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/grievance/{grievance_id}",
    response_model=UUID,
    summary="Open issue chat",
    description="Find or start a chat specifically about a reported issue.",
    operation_id="openGrievanceChatThread",
)
async def get_grievance_conversation(
    grievance_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify grievance exists
    result = await db.execute(
        select(Grievance)
        .options(selectinload(Grievance.category))
        .where(Grievance.id == grievance_id)
    )
    grievance = result.scalar_one_or_none()
    if not grievance:
        raise HTTPException(status_code=404, detail="Grievance not found")

    # Find or create conversation for this grievance
    # Since it's task-based, typically all staff involved might see it, 
    # but for now let's handle it as a shared thread for the grievance.
    conv_query = select(Conversation).where(
        and_(
            Conversation.type == "task",
            Conversation.grievance_id == grievance_id
        )
    ).limit(1)
    conv_res = await db.execute(conv_query)
    conv = conv_res.scalar_one_or_none()

    if not conv:
        try:
            conv = Conversation(
                type="task",
                grievance_id=grievance_id,
                name=f"Chat for Task: {grievance_id}"
            )
            db.add(conv)
            await db.flush()
            
            # 1. Add current user
            db.add(ConversationParticipant(conversation_id=conv.id, user_id=current_user.id))
            
            # 2. Add ward/department managers automatically
            if grievance.ward_id and grievance.category and grievance.category.dept_id:
                manager_query = select(User.id).join(
                    WorkerProfile, User.id == WorkerProfile.user_id
                ).where(
                    and_(
                        User.role == "fieldManager",
                        WorkerProfile.ward_id == grievance.ward_id,
                        WorkerProfile.department_id == grievance.category.dept_id
                    )
                )
                manager_res = await db.execute(manager_query)
                for (m_id,) in manager_res.all():
                    if m_id != current_user.id:
                        db.add(ConversationParticipant(conversation_id=conv.id, user_id=m_id))
            
            await db.commit()
        except IntegrityError:
            await db.rollback()
            conv_res = await db.execute(conv_query)
            conv = conv_res.scalar_one_or_none()
            if not conv:
                raise HTTPException(status_code=500, detail="Failed to create or retrieve task conversation")
            
            # Fall through to existing participant check
    
    # Check/Add participants (including managers for existing conversations)
    participants_to_add = [current_user.id]
    if grievance.ward_id and grievance.category and grievance.category.dept_id:
        manager_query = select(User.id).join(
            WorkerProfile, User.id == WorkerProfile.user_id
        ).where(
            and_(
                User.role == "fieldManager",
                WorkerProfile.ward_id == grievance.ward_id,
                WorkerProfile.department_id == grievance.category.dept_id
            )
        )
        manager_res = await db.execute(manager_query)
        for (m_id,) in manager_res.all():
            participants_to_add.append(m_id)

    # Filter out duplicates and check existence
    existing_parts_res = await db.execute(select(ConversationParticipant.user_id).where(ConversationParticipant.conversation_id == conv.id))
    existing_ids = {u_id for u_id, in existing_parts_res.all()}
    
    for u_id in set(participants_to_add):
        if u_id not in existing_ids:
            db.add(ConversationParticipant(conversation_id=conv.id, user_id=u_id))
    
    await db.commit()

    return conv.id

@router.get(
    "/colleagues",
    response_model=List[ConversationMember],
    summary="Find your teammates",
    description="List people in your department that you can message.",
    operation_id="listDepartmentColleagues",
)
async def get_colleagues(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # Fetch people in the same department
        if not current_user.worker_profile or not current_user.worker_profile.department_id:
            return []
        
        dept_id = current_user.worker_profile.department_id
        # Join User and WorkerProfile explicitly to avoid AmbiguousForeignKeysError
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
                role=_get_role_name(u)
            ) for u in users
        ]
    except Exception as e:
        logger.error(f"Error in get_colleagues: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error while fetching colleagues")

@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[MessageSchema],
    summary="View chat messages",
    description="See all messages in a specific group or task conversation.",
    operation_id="fetchChatMessages",
)
async def get_conversation_messages(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify participation
    part_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id
        )
    )
    part_res = await db.execute(part_query)
    if not part_res.scalar_one_or_none():
        # For task-based, auto-join if staff
        conv_res = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = conv_res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # If it's a task conversation, staff can join
        if conv.type == "task":
            db.add(ConversationParticipant(conversation_id=conversation_id, user_id=current_user.id))
            await db.commit()
        else:
            raise HTTPException(status_code=403, detail="Not a participant")

    # Reset unread count
    await db.execute(
        ConversationParticipant.__table__.update()
        .where(and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id
        ))
        .values(unread_count=0)
    )
    await db.commit()

    query = (
        select(InternalMessage, User.name.label("sender_name"))
        .join(User, InternalMessage.sender_id == User.id)
        .where(InternalMessage.conversation_id == conversation_id)
        .order_by(InternalMessage.created_at.asc())
    )
    res = await db.execute(query)
    
    results = []
    for msg, sender_name in res.all():
        msg_dict = {
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "receiver_id": msg.receiver_id,
            "content": msg.content,
            "is_read": msg.is_read,
            "created_at": msg.created_at,
            "sender_name": sender_name
        }
        results.append(msg_dict)
        
    return results

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageSchema,
    summary="Post in chat",
    description="Send a message to everyone in this specific conversation or task chat.",
    operation_id="postChatMessage",
)
async def send_conversation_message(
    conversation_id: UUID,
    message_in: InternalMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify participation
    part_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id
        )
    )
    part_res = await db.execute(part_query)
    if not part_res.scalar_one_or_none():
         raise HTTPException(status_code=403, detail="Not a participant")

    try:
        new_msg = InternalMessage(
            sender_id=current_user.id,
            conversation_id=conversation_id,
            content=message_in.content
        )
        db.add(new_msg)
        
        # Increment unread for others
        await db.execute(
            ConversationParticipant.__table__.update()
            .where(and_(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id != current_user.id
            ))
            .values(unread_count=ConversationParticipant.unread_count + 1)
        )
        
        await db.commit()
        await db.refresh(new_msg)
        return new_msg
    except Exception as e:
        logger.error(f"Error in send_conversation_message: {e}")
        logger.error(traceback.format_exc())
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
