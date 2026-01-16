from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import settings
import sys
import logging

logger = logging.getLogger("uvicorn")

# 1. 엔진 및 세션 팩토리 (기존 동일)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

Base = declarative_base()

# 2. 의존성 주입 (기존 동일)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# 3. 자체적으로 에러를 처리하는 초기화 함수
async def init_db():
    try:
        # 여기서 테이블을 만들어야 들어가는 구조다..! 
        from core.models import Message

        # 연결 시도 및 테이블 생성
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ PostgreSQL Connected & Tables Initialized!")
    except Exception as e:
        # 에러 발생 시 여기서 로그를 남기고, 필요하면 알림을 보냄
        # 메인 서버가 죽지 않게 하거나, 반대로 여기서 sys.exit()을 호출해 강제 종료할 수도 있음
        logger.error(f"❌ PostgreSQL Connection Failed: {e}")
        sys.exit(1)