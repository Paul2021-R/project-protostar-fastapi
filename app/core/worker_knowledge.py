# app/core/worker_knowledge.py

import asyncio
import json
import logging
import httpx
from core.config import settings
from core.redis import get_redis_client
from core.minio_client import minio_client

logger = logging.getLogger("uvicorn")

MAX_CONCURRENT_JOBS = 3
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

async def send_webhook(doc_id: str, status: str, result_meta: dict = None, error_msg: str = None):
    """
    NestJS: KnowledgeController.handleWebhook 호출
    """
    url = f"{settings.NEST_API_URL}/api/v1/upload/knowledge-docs/webhook"
    
    # NestJS RagWebhookDto 구조에 맞춤
    payload = {
        "docId": doc_id,
        "status": status, # 'COMPLETED' | 'FAILED'
    }

    if result_meta:
        payload["resultMeta"] = result_meta
    
    if error_msg:
        payload["errorMessage"] = error_msg

    headers = {
        "x-webhook-secret": settings.INTERNAL_WEBHOOK_SECRET,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
            if resp.status_code in [200, 201]:
                logger.info(f"🔔 Webhook Success: {doc_id} -> {status}")
            else:
                logger.error(f"⚠️ Webhook Failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"❌ Webhook Connection Error: {e}")

async def process_knowledge_job(payload_json: str):
    """
    로직 정리
    1. Payload 파싱
    2. MinIO 다운로드
    3. RAG 벡터화 (TODO)
    4. 결과 Webhook 전송
    """
    doc_id = None
    try:
        # 1. Payload 파싱 (NestJS: AiTaskService가 보낸 데이터)
        task_data = json.loads(payload_json)
        doc_id = task_data.get("docId")
        minio_key = task_data.get("minioKey")
        bucket_name = task_data.get("minioBucket")
        mime_type = task_data.get("mimeType")

        logger.info(f"📚 [Start] RAG Job | DocID: {doc_id}")

        # 2. MinIO 파일 다운로드
        logger.info(f"📥 Downloading: {minio_key} ({bucket_name})")
        
        file_content = await minio_client.get_file_content(
            object_name=minio_key, 
            bucket_name=bucket_name
        )
        
        if not file_content:
            raise ValueError("File content is empty")

        file_size_kb = len(file_content) / 1024
        logger.info(f"✅ Downloaded: {file_size_kb:.2f} KB")

        # ---------------------------------------------------------
        # [3. RAG 벡터화 구간] - 다음 단계에서 이곳에 로직 주입
        # ---------------------------------------------------------
        # 예: text = pdf_parser(file_content) -> chunks -> embeddings -> DB
        
        # (임시 결과 데이터)
        result_meta = {
            "chunkCount": 123, # 가상 데이터
            "embeddingModel": "openai-text-embedding-3-small",
            "vectorStoreKey": f"vec_{doc_id}" 
        }
        # ---------------------------------------------------------

        # 4. 성공 Webhook
        await send_webhook(
            doc_id=doc_id, 
            status="COMPLETED", 
            result_meta=result_meta
        )

    except Exception as e:
        logger.error(f"❌ Job Failed ({doc_id}): {e}")
        # 실패 Webhook (doc_id가 있을 때만)
        if doc_id:
            await send_webhook(
                doc_id=doc_id, 
                status="FAILED", 
                error_msg=str(e)
            )

async def run_knowledge_worker():
    """
    Redis Queue 리스너 (Queue Name: ai:job:queue)
    """
    logger.info("🚀 Knowledge Worker Listening on 'ai:job:queue'...")
    redis_client = get_redis_client()
    
    try:
        while True:
            await semaphore.acquire()
            
            # NestJS가 넣는 큐 이름과 일치해야 함
            result = await redis_client.brpop("ai:job:queue", timeout=1)

            if result:
                logger.info(f"✅ [BRPOP] Job received: {result}")
                _, payload = result
                # bytes to string
                if isinstance(payload, bytes):
                    payload = payload.decode('utf-8')
                
                # 비동기 Task 실행
                task = asyncio.create_task(process_knowledge_job(payload))
                task.add_done_callback(lambda t: semaphore.release())
            else:
                semaphore.release()
                await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        logger.info("🛑 Worker Cancelled")
    finally:
        await redis_client.close()