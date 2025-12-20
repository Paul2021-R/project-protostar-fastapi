from contextlib import asynccontextmanager
from fastapi import FastAPI
from core.redis import init_test_redis  
from core.database import init_db
from core.ai import generate_response
from core.ai import init_ai_context

@asynccontextmanager
async def main_lifespan(app: FastAPI): # context manager 패턴
    # 영역 1 - on module init
    # 시작 시 Redis 연결 테스트
    await init_test_redis()
    await init_db()
    
    await init_ai_context()
    
    yield # 기준점
    # 영역 2 - on module destroy 

app = FastAPI(lifespan=main_lifespan)

@app.get("/")
def read_root():
    return {"message": "Protostar Worker is Running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/test-ai")
async def test_ai(prompot:str = "자기소개 부탁해", context:str = ""):
    """
    Query Parameter로 prompt를 받아서 AI 답변을 반환
    예: /test-ai?prompt=Docker가 뭐야?
    """
    answer = await generate_response(prompot, context)
    return {"answer": answer}