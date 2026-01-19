import asyncio
import logging
import uuid
from core.redis import get_redis_client
from core.database import AsyncSessionLocal
from core.ai import generate_summary
from core.services import get_message_by_id, update_message_with_summary

logger = logging.getLogger("uvicorn")

MAX_CONCURRENT_SUMMARY = 50 # 요약이라 좀더 동시성 추가
semaphore = asyncio.Semaphore(MAX_CONCURRENT_SUMMARY)

async def process_summary_job(msg_id_str: str):
  """
  핵심 로직
  1. DB 에서 원본 메시지 확보
  2. AI 로 요약 생성 (Bypass 로직 포함)
  3. DB 에 저장 -> 상태 변경 => 다음 메시지 작업시 기억 출력 가능!
  """
  async with AsyncSessionLocal() as db:
    try:
      msg_id = uuid.UUID(msg_id_str)

      message = await get_message_by_id(db, msg_id)
      if not message:
        logger.warning(f"⚠️ Summary target not found: {msg_id}")
        return

      logger.info(f"📝 Summarizing Msg: {msg_id} (Length: {len(message.content_full)})")

      result = await generate_summary(message.content_full)

      await update_message_with_summary(
        db,
        msg_id,
        result["summary"],
        result["usage"],
      )
      logger.info(f"✅ Summary Complete: {msg_id}")

    except Exception as e:
      logger.error(f"❌ Summary Failed for {msg_id_str}: {e}")

async def run_summary_worker():
  """
  요약 전용 큐(chat:summary:queue)를 구독하는 루프
  """
  logger.info("📑 Summary Worker started. Listening to 'chat:summary:queue'...")
  redis_client = get_redis_client()

  try:
    while True: 
      
      await semaphore.acquire()

      try: 
        result = await redis_client.brpop(
          "chat:summary:queue",
          timeout=5
        )

        if result:
          _, msg_id_str = result
          task = asyncio.create_task(process_summary_job(msg_id_str))
          task.add_done_callback(lambda t: semaphore.release())
        else:
          semaphore.release()
          await asyncio.sleep(0.5)
        
      except Exception as e:
        semaphore.release()
        raise

  except asyncio.CancelledError:
    logger.info("🛑 Summary Worker cancelled.")
  except Exception as e:
    logger.error(f"❌ Summary Worker crashed: {e}") 
  finally:
    await redis_client.close()