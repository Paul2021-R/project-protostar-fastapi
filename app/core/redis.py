import redis.asyncio as redis
import sys
from core.config import settings
import logging

logger = logging.getLogger("uvicorn")

pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=1000,
)

def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=pool)

async def init_test_redis():
    redis_client = get_redis_client()
    try:
        await redis_client.ping()
        logger.info("✅ Redis Connected Successfully!")
    except Exception as e:
        logger.error(f"❌ Redis Connection Failed: {e}")
        await redis_client.close()
        sys.exit(1)
    finally:
        await redis_client.close()