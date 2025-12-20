import redis.asyncio as redis
import sys
from core.config import settings

pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)

def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=pool)

async def init_test_redis():
    redis = get_redis_client()
    try:
        await redis.ping()
        print("✅ Redis Connected Successfully!")
    except Exception as e:
        print(f"❌ Redis Connection Failed: {e}")
        await redis.close()
        sys.exit(1)
    finally:
        await redis.close()