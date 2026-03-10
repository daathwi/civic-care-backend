from datetime import datetime
from typing import List
from uuid import UUID
from pydantic import BaseModel, Field

class InternalMessageBase(BaseModel):
    receiver_id: UUID | None = None
    content: str = Field(..., min_length=1)

class InternalMessageCreate(InternalMessageBase):
    pass

class InternalMessage(BaseModel):
    id: UUID
    conversation_id: UUID | None = None
    sender_id: UUID
    receiver_id: UUID | None = None
    content: str
    is_read: bool
    created_at: datetime
    sender_name: str | None = None

    class Config:
        from_attributes = True

class ConversationMember(BaseModel):
    id: UUID
    name: str
    role: str
    last_message: str | None = None
    last_message_time: datetime | None = None
    unread_count: int = 0

class ConversationSchema(BaseModel):
    id: UUID
    name: str | None = None
    type: str
    department_id: UUID | None = None
    grievance_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    participants: List[UUID] = []

    class Config:
        from_attributes = True
