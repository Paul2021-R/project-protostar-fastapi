from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from core.redis import init_test_redis  
from core.database import init_db
from core.ai import generate_response_stream
# from core.ai import init_ai_context
from core.worker import run_worker
from core.worker_summary import run_summary_worker
from core.silence_health_checker import report_health_status_to_redis
from core.redis import get_redis_client
from core.minio_client import minio_client
from core.config import settings
from core.worker_knowledge import run_knowledge_worker 

import asyncio
import uuid
import logging

INSTANCE_ID = f"fastapi:{str(uuid.uuid4())[:8]}"
logger = logging.getLogger('uvicorn')
logger.setLevel(settings.LOG_LEVEL)

logger.info(f'uvicorn log level: {settings.LOG_LEVEL}')

@asynccontextmanager
async def main_lifespan(app: FastAPI): # context manager 패턴
    # 영역 1 - on module init
    # 시작 시 Redis 연결 테스트
    await init_test_redis()
    await init_db()
    
    # await init_ai_context()

    worker_task = asyncio.create_task(run_worker())
    summary_task = asyncio.create_task(run_summary_worker())
    health_task = asyncio.create_task(report_health_status_to_redis(INSTANCE_ID))
    rag_task = asyncio.create_task(run_knowledge_worker())
    await minio_client.check_connection()
    
    logger.info(f"🚀 Protostar FastAPI Instance {INSTANCE_ID} Started & Reporting Health...")
    
    yield # 기준점
    # 영역 2 - on module destroy 
    worker_task.cancel()
    summary_task.cancel()
    health_task.cancel()
    rag_task.cancel()

    # Graceful Shutdown - 종료 시 출석부에서 즉시 제거
    # 스코프 문제를 위하여 redis_client를 None으로 초기화
    redis_client = None

    try:
        redis_client = get_redis_client()
        await redis_client.zrem("cluster:heartbeats", INSTANCE_ID)
    except Exception as e: # error handling 패스 안하기
        logger.error(f"Failed to remove instance from Redis during shutdown: {e}")
    finally:
        if redis_client: # 클라이언트 존재 할 때만 닫기
            await redis_client.close()

    try:
        await worker_task
        await health_task
        await summary_task
        await rag_task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=main_lifespan)

@app.get("/")
def read_root():
    return {"message": "Protostar Worker is Running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/test-ai")
async def test_ai(prompt:str = "자기소개 부탁해", context:str = ""):
    """
    Query Parameter로 prompt를 받아서 AI 답변을 반환
    예: /test-ai?prompt=Docker가 뭐야?
    """

    return StreamingResponse(
        generate_response_stream(prompt, context),
        media_type="text/plain"
    )