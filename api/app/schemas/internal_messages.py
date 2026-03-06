from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

class InternalMessageBase(BaseModel):
    receiver_id: UUID
    content: str = Field(..., min_length=1)

class InternalMessageCreate(InternalMessageBase):
    pass

class InternalMessage(BaseModel):
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    content: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationMember(BaseModel):
    id: UUID
    name: str
    role: str
    last_message: str | None = None
    last_message_time: datetime | None = None
    unread_count: int = 0
