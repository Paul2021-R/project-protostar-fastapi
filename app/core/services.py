import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from .models import Message, MessageRole, ProcessingStatus

async def save_user_message(
  db: AsyncSession,
  user_uuid: uuid.UUID,
  session_id: str,
  content: str,
) -> Message:
  """
  User Message 저장
  """
  new_message = Message(
    user_uuid=user_uuid,
    session_id=session_id,
    role=MessageRole.USER,
    content_full=content,
    content_summary=None,
    token_usage={},
    status=ProcessingStatus.COMPLETED,
  )

  db.add(new_message)
  await db.commit()
  await db.refresh(new_message)

  return new_message

async def save_initial_response(
  db: AsyncSession, 
  user_uuid: uuid.UUID,
  session_id: str, 
  content_full: str,
  main_token_usage: dict
) -> Message:
  """
  Main Worker 답변 직후 동작 
  요약 로직 전이므로 Status 는 'PENDING'으로 저장됨
  """
  initial_usage = {
    "main": main_token_usage,
    "summary": {},
    "total": main_token_usage,
  }

  new_message = Message(
    user_uuid=user_uuid,
    session_id=session_id,
    role=MessageRole.ASSISTANT,
    content_full=content_full,
    content_summary=None,
    token_usage=initial_usage,
    status=ProcessingStatus.PENDING,
  )

  db.add(new_message)
  await db.commit()
  await db.refresh(new_message)

  return new_message

async def update_message_with_summary(
  db: AsyncSession,
  message_id: uuid.UUID,
  summary_text: str,
  summary_token_usage: dict
) -> Message:
  """
  Summary Worker 가 작업을 마친 후 호출됨. 
  기존 메시지를 찾아 요약 내용과 토큰 사용량을 업데이트 하고, 상태를 COMPLETED 로 변경함. 
  """
  query = select(Message).where(Message.id == message_id)
  result = await db.execute(query)
  message = result.scalar_one_or_none()

  if not message:
    raise ValueError(f"Message {message_id} not found")

  current_usage = dict(message.token_usage) if message.token_usage else {}
  current_usage["summary"] = summary_token_usage

  main_usage = current_usage.get("main", {"input": 0, "output": 0})
  total_input = main_usage.get("input", 0) + summary_token_usage.get("input", 0)
  total_output = main_usage.get("output", 0) + summary_token_usage.get("output", 0)

  current_usage["total"] = {
    "input": total_input,
    "output": total_output,
  }

  message.content_summary = summary_text
  message.token_usage = current_usage
  message.status = ProcessingStatus.COMPLETED

  await db.commit()
  await db.refresh(message)

  return message

async def get_message_by_id(
  db: AsyncSession,
  message_id: uuid.UUID,
) -> Message | None:
  """
  ID로 메시지 조회 (Summary Worker 가 원본 내용 가져갈 때 필요함)
  """

  query = select(Message).where(Message.id == message_id)
  result = await db.execute(query)
  return result.scalar_one_or_none()

async def get_session_history(
  db: AsyncSession,
  session_id: str,
  exclude_ids: list[uuid.UUID] = None
) -> list[Message]:
  """
  Memory 세션의 '모든' 대화 기록을 조회한다. 
  - 최신순으로 가져와서 역순으로 정렬
  - 실패한 메시지는 제외 
  """

  query =  (
    select(Message)
    .where(Message.session_id == session_id)
    .where(Message.status != ProcessingStatus.FAILED)
    .order_by(desc(Message.created_at))
  )

  if exclude_ids:
    query = query.where(Message.id.notin_(exclude_ids))

  result = await db.execute(query)
  messages = result.scalars().all()

  return list(reversed(messages))