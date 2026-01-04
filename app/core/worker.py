import asyncio
import json
import logging
from datetime import datetime
from core.redis import get_redis_client
from core.ai import generate_response_stream

logger = logging.getLogger("uvicorn")

TARGET_TPS = 100
TEST_DELAY = 1 / TARGET_TPS

async def process_chat_job(job_id: str, redis_client): 
    """
    단일 채팅 작업을 처리하는 함수 
    1. Redis 에서 작업 데이터 조회
    2. AI 응답 생성 
    3. Redis Pub/Sub 에 결과 전송
    """

    # 작업 키 확보
    task_key = f"chat:task:{job_id}"

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
        user_uuid = task_data.get("uuid")
        prompt = task_data.get("content")
        context = task_data.get("context", "")

        logger.info(f"🤖 Processing Job {job_id} | User: {user_uuid} | Session: {session_id}")

        channel = f"chat:stream:{user_uuid}-{session_id}"

        # 테스트 모드
        if mode not in ['general', 'page_context']:
            test_message_payload = {
                "type": 'message',
                "content": "T",
                "uuid": user_uuid,
                "sessionId": session_id,
                "timestamp": datetime.now().isoformat()
            }
            await redis_client.publish(channel, json.dumps(test_message_payload))

            await asyncio.sleep(TEST_DELAY) 

            done_payload = {
                "type": 'done',
                "content": 'done',
                "uuid": user_uuid,
                "sessionId": session_id,
                "timestamp": datetime.now().isoformat()
            }
            
            await redis_client.publish(channel, json.dumps(done_payload))
            await redis_client.delete(task_key)
            logger.info(f"🗑️ [Test] Deleted task data for job: {job_id}")
            return

        # AI가 한 토큰(조각)를 줄 때마다 Redis로 즉시 발송
        async for token in generate_response_stream(prompt, mode, context):
            message_payload = {
                "type": 'message',
                "content": token, # 전체 문장이 아닌 '조각'
                "uuid": user_uuid,
                "sessionId": session_id,
                "timestamp": task_data.get("timestamp")
            }
            # print(token)
            # NestJS로 조각 발송
            await redis_client.publish(channel, json.dumps(message_payload))

        done_payload = {
            "type": 'done',            # 완료 타입 (NestJS나 클라이언트에서 식별 가능)
            "content": 'done',           # 내용은 없음
            "uuid": user_uuid,
            "sessionId": session_id,
            "timestamp": datetime.now().isoformat()
        }
        await redis_client.publish(channel, json.dumps(done_payload))
        logger.info(f"✅ Job {job_id} Finished & DONE signal sent.")

        await redis_client.delete(task_key)
        logger.info(f"🗑️ Deleted task data for job: {job_id}")
        
    except Exception as e:
        logger.error(f"❌ Error processing job {job_id}: {e}")  

async def run_worker():
    """
    백그라운드에서 실행되며 Redis Queue(chat:job:queue)를 지속적으로 확인하는 루프 
    """
    logger.info("🚀 Worker started. Listening to 'chat:job:queue'...")
    redis_client = get_redis_client()
    
    try:
        while True:
            result = await redis_client.brpop("chat:job:queue", timeout=1)

            if result:
                _, job_id = result 
                asyncio.create_task(process_chat_job(job_id, redis_client))

            await asyncio.sleep(0.001)
    
    except asyncio.CancelledError:
        logger.info("🛑 Worker loop cancelled.")
    except Exception as e:
        logger.error(f"❌ Worker crashed: {e}")
    finally:
        await redis_client.close()
            