from contextlib import asynccontextmanager
from fastapi import FastAPI
from core.redis import init_test_redis  

@asynccontextmanager
async def main_lifespan(app: FastAPI): # context manager 패턴
    # 영역 1 - on module init
    # 시작 시 Redis 연결 테스트
    await init_test_redis()
    
    yield # 기준점
    # 영역 2 - on module destroy 

app = FastAPI(lifespan=main_lifespan)

@app.get("/")
def read_root():
    return {"message": "Protostar Weorker is Running"}

@app.get("/health")
def health_check():
    return {"status": "ok"}