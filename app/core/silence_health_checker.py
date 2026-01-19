import logging
from core.redis import get_redis_client
import psutil
import asyncio
import time
import json

logger = logging.getLogger("uvicorn")

async def report_health_status_to_redis(instance_id: str):
    """
    [시스템 상태 파악 및 생존 신고용]
    - 주기 : 
    - 전략 : 침묵 전략(자원 부족 시 침묵 + 로깅)
    """

    redis_client = get_redis_client()

    psutil.cpu_percent(interval=None)

    while True:
        try:
            # 1. 상태 파악 
            cpu_usage = psutil.cpu_percent(interval=None)
            memory_usage = psutil.virtual_memory().percent

            is_health = True
            fail_reason = None

            # 2. 판단 로직
            if cpu_usage > 80 or memory_usage > 80:
                is_health = False
                fail_reason = f"overload (CPU: {cpu_usage}%, MEM: {memory_usage}%)"

            # 3. 행동 결정
            if is_health:    
                await redis_client.zadd("cluster:heartbeats", {instance_id: time.time()})
            else:
                log_payload = {
                    "level": "warn",
                    "event": "heartbeat_skipped",
                    "instance": instance_id,
                    "reason": fail_reason,
                    "cpu": cpu_usage,
                    "memory": memory_usage,
                }

                logger.warning(json.dumps(log_payload))
                
        # exception 이유 
        # heart beat  무한 루프를 돌며 생존 신고를 해야하고, 
        # 따라서 대응할 수 있는 명료한 에러 핸들링이 아닌, 범용적이고, 그냥 핸들링만 간단히 하고 넘어가는게 더 중요.
        except Exception as e: 
            error_payload = {
                "level": "error",
                "event": "heartbeat_error",
                "instance": instance_id,
                "error": str(e),
            }
            logger.exception(json.dumps(error_payload))

        await asyncio.sleep(3)