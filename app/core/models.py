import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, Any

from sqlalchemy import String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.database import Base

class MessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ProcessingStatus(str, PyEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Message(Base):
  __tablename__ = "messages"

  # 1. Identity Keys 
  id: Mapped[uuid.UUID] = mapped_column(
    PG_UUID(as_uuid=True), # DB 에서 꺼낼때 문자열 아닌, 파이썬 객체 UUID 로 자동 변환 
    primary_key=True,
    default=uuid.uuid4,
  )

  user_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
  session_id: Mapped[str] = mapped_column(String(40), nullable=False)

  # 2. Basic Info 
  role: Mapped[MessageRole] = mapped_column(String(20), nullable=False)

  # 3. Content 
  content_full: Mapped[str] = mapped_column(Text, nullable=False)
  content_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

  # 4. Status 
  status: Mapped[ProcessingStatus] = mapped_column(
    String(20), 
    default=ProcessingStatus.PENDING,
    nullable=False
  )

  # 5. Metrics 
  token_usage: Mapped[dict[str, Any]] = mapped_column(
    JSONB,
    default={},
    nullable=True
  )

  # 6. Timestamps 
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), 
    server_default=func.now(), # 시간 찍는 주체, DB 스키마(DDL)에 남는지 차이. DBA 가 DB 직접 적을 시 default=~ 이렇게 하면 시간이 안들어감
  )

  updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    onupdate=func.now(),
    nullable=True # DB 관리 차원에서 만든 직후와 갱신 여부를 판단하는 용
  )

  __table_args__ = (
    Index("idx_messages_session_created", "session_id", "created_at"),
    Index("idx_messages_user_uuid", "user_uuid"),
  )

  def __repr__(self):
    return f"<Message id={self.id} role={self.role} status={self.status}>"