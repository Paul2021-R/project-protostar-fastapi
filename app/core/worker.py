import asyncio
import json
import logging
import uuid
from datetime import datetime
from core.config import settings

# 기존 Import
from core.redis import get_redis_client
from core.ai import generate_response_stream

# DB 및 서비스 Import
from core.database import AsyncSessionLocal 
from core.services import save_user_message, save_initial_response, get_session_history
from .models import Message, MessageRole, ProcessingStatus
from core.rag_service import search_similar_docs, format_rag_context


logger = logging.getLogger("uvicorn")

TARGET_TPS = 100
TEST_DELAY = 1 / TARGET_TPS

MAX_CONCURRENT_JOBS = 100
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

async def process_chat_job(job_id: str, redis_client): 
    """
    단일 채팅 작업을 처리하는 함수 
    1. Redis 에서 작업 데이터 조회
    2. 최초 질문 저장
    3. AI 응답 생성 (이때 전체 대화 흐름 함께 들어감)
    4. 답변 저장
    5. Redis Pub/Sub 에 결과 전송
    6. AI 응답의 요약 생성 및 저장 
    """

    # 작업 키 확보
    task_key = f"chat:task:{job_id}"

    # async with AsyncSessionLocal() as db:
    try:
        # 작업 데이터 데이터 조회
        task_data_json = await redis_client.get(task_key)

        if not task_data_json:
            logger.warning(f"Task data missing for job: {job_id}")
            return

        # 작업 데이터 파싱   
        task_data = json.loads(task_data_json)

        mode = task_data.get("mode")
        session_id = task_data.get("sessionId")
        raw_user_uuid = task_data.get("uuid")
        try:
            user_uuid = uuid.UUID(raw_user_uuid)
        except ValueError:
            logger.error(f"❌ Invalid UUID format: {raw_user_uuid}")
            return # 혹은 에러 처리 로직

        prompt = task_data.get("content")
        base_context = task_data.get("context", "")

        timestamp = task_data.get("timestamp")

        logger.info(f"🤖 Processing Job {job_id} | User: {raw_user_uuid} | Session: {session_id}")

        # RAG 검색 로직
        rag_system_message=""

        if mode in ['general']:
            logger.info(f"🔍 [RAG] Searching docs for: '{prompt}'")
            found_docs = await search_similar_docs(prompt)

            if found_docs:
                rag_context_str = format_rag_context(found_docs)
                rag_system_message = f"""
You are an intelligent assistant named Protostar.

[Instructions]
- Use the provided [Retrieved Knowledge] to answer the user's question accurately.
- If the answer is found in the knowledge, cite the source keywords if possible.
- If the answer is NOT in the knowledge, rely on your general knowledge but mention that "This information is not in the provided documents."
- Respond in the same language as the user's question (Korean).

[Retrieved Knowledge]
{rag_context_str}
"""         
                logger.info("✅ [RAG] Context injected into system prompt.")
            else:
                logger.info("⚠️ [RAG] No relevant documents found.")    

        final_system_context = f"{rag_system_message}\n\n{base_context}".strip()                
        
        user_msg = None

        # 사용자 질문 DB 저장 
        async with AsyncSessionLocal() as db:
            try: 
                user_msg = await save_user_message(
                    db,
                    user_uuid,
                    session_id,
                    prompt,
                )
                user_msg_id = user_msg.id
            except Exception as e:
                logger.error(f"❌ Error saving user message: {e}")
                raise e

        channel = f"chat:stream:{raw_user_uuid}-{session_id}"

        # 테스트 모드
        if mode not in ['general', 'page_context']:
            test_message_payload = {
                "type": 'message',
                "content": "T",
                "uuid": raw_user_uuid,
                "sessionId": session_id,
                "timestamp": task_data.get("timestamp")
            }
            await redis_client.publish(channel, json.dumps(test_message_payload))

            await asyncio.sleep(TEST_DELAY) 

            done_payload = {
                "type": 'done',
                "content": 'done',
                "uuid": raw_user_uuid,
                "sessionId": session_id,
                "timestamp": task_data.get("timestamp")
            }
            
            await redis_client.publish(channel, json.dumps(done_payload))
            await redis_client.delete(task_key)
            logger.info(f"🗑️ [Test] Deleted task data for job: {job_id}")
            return


        history_context = []
        if user_msg:
            async with AsyncSessionLocal() as db:
                past_messages = await get_session_history(
                    db,
                    session_id,
                    exclude_ids=[user_msg_id]
                )
                for msg in past_messages:
                    final_content = msg.content_summary if msg.content_summary else msg.content_full

                    role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"

                    history_context.append({
                        "role": role,
                        "content": final_content,
                    })
        # AI가 한 토큰(조각)를 줄 때마다 Redis로 즉시 발송
        # 토큰 수집 준비
        full_response_list = []
        
        async for token in generate_response_stream(
            prompt, 
            mode, 
            final_system_context, 
            history=history_context
            ):
            full_response_list.append(token)
            message_payload = {
                "type": 'message',
                "content": token, # 전체 문장이 아닌 '조각'
                "uuid": raw_user_uuid,
                "sessionId": session_id,
                "timestamp": task_data.get("timestamp")
            }
            # print(token)
            # NestJS로 조각 발송
            await redis_client.publish(channel, json.dumps(message_payload))

        done_payload = {
            "type": 'done',            # 완료 타입 (NestJS나 클라이언트에서 식별 가능)
            "content": 'done',           # 내용은 없음
            "uuid": raw_user_uuid,
            "sessionId": session_id,
            "timestamp": datetime.now().isoformat()
        }
        await redis_client.publish(channel, json.dumps(done_payload))
        logger.info(f"✅ Job {job_id} Finished & DONE signal sent.")

        # 답변 DB 1차 저장 
        full_response_text = "".join(full_response_list)
        usage_data = {
            "input": len(prompt),
            "output": len(full_response_text),
            "model": settings.OPENROUTER_MODEL
        }
        async with AsyncSessionLocal() as db:
            try:
                saved_msg = await save_initial_response(
                    db,
                    user_uuid,
                    session_id,
                    full_response_text,
                    usage_data,
                )
                logger.info(f"💾 Saved AI Response. MsgID: {saved_msg.id}")

                await redis_client.rpush("chat:summary:queue", str(saved_msg.id))
                logger.info(f"🔔 Triggered Summary for MsgID: {saved_msg.id}")

            except Exception as e:
                logger.error(f"⚠️ AI response save failed: {e}")

        await redis_client.delete(task_key)
        logger.info(f"🗑️ Deleted task data for job: {job_id}")
        
    except Exception as e:
        # DLQ 구현 
        # Promtail 로 추적 중이니 식별자를 포함한 JSON 식의 출력 구현 
        error_payload = {
            "type": "DLQ",
            "status": "failed",
            "job_id": job_id,
            "error_msg": str(e),
            "original_task_data": task_data if 'task_data' in locals() else None,
            "timestamp": datetime.now().isoformat()
        }
        logger.error(json.dumps(error_payload, ensure_ascii=False))
        logger.error(f"❌ Error processing job {job_id}: {e}")  # 기존 에러 핸들링, 간단한 판단용

async def run_worker():
    """
    백그라운드에서 실행되며 Redis Queue(chat:job:queue)를 지속적으로 확인하는 루프 
    """
    logger.info("🚀 Protostar Worker started. Listening to 'chat:job:queue'...")
    redis_client = get_redis_client()
    
    try:
        while True:

            await semaphore.acquire()
            
            result = await redis_client.brpop("chat:job:queue", timeout=5)

            if result:
                _, job_id = result 
                task = asyncio.create_task(process_chat_job(job_id, redis_client))
                task.add_done_callback(lambda t: semaphore.release())
            else:
                semaphore.release()
                await asyncio.sleep(0.0001)
    
    except asyncio.CancelledError:
        logger.info("🛑 Worker loop cancelled.")
    except Exception as e:
        logger.error(f"❌ Worker crashed: {e}")
    finally:
        await redis_client.close()
            