from contextlib import asynccontextmanager
from fastapi import FastAPI
from core.redis import init_test_redis  
from core.database import init_db
from core.ai import generate_response_stream
from core.ai import init_ai_context
from core.worker import run_worker
import asyncio
from fastapi.responses import StreamingResponse
from core.silence_health_checker import report_health_status_to_redis
import uuid
from core.redis import get_redis_client

INSTANCE_ID = f"fastapi:{str(uuid.uuid4())[:8]}"

@asynccontextmanager
async def main_lifespan(app: FastAPI): # context manager 패턴
    # 영역 1 - on module init
    # 시작 시 Redis 연결 테스트
    await init_test_redis()
    await init_db()
    
    await init_ai_context()

    worker_task = asyncio.create_task(run_worker())
    health_task = asyncio.create_task(report_health_status_to_redis(INSTANCE_ID))
    
    print(f"🚀 FastAPI Instance {INSTANCE_ID} Started & Reporting Health...")
    
    yield # 기준점
    # 영역 2 - on module destroy 
    worker_task.cancel()
    health_task.cancel()

    # Graceful Shutdown - 종료 시 출석부에서 즉시 제거

    try:
        redis_client = get_redis_client()
        await redis_client.zrem("cluster:heartbeats", INSTANCE_ID)
    except Exception as e:
        pass
    finally:
        await redis_client.close()

    try:
        await worker_task
        await health_task
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