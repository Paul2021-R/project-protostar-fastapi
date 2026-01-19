# app/core/worker_knowledge.py
import asyncio
import json
import logging
import httpx
import re
from openai import AsyncOpenAI
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from core.config import settings
from core.redis import get_redis_client
from core.minio_client import minio_client
from core.database import AsyncSessionLocal
from core.vectorized_doc import VectorizedDoc

logger = logging.getLogger("uvicorn")

MAX_CONCURRENT_JOBS = 3
semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

ai_client = AsyncOpenAI(
  api_key=settings.OPENROUTER_API_KEY,
  base_url="https://openrouter.ai/api/v1",
)

async def extract_metadata_from_llm(text_preview: str) -> dict:
  """
  문서 앞 부분을 읽고 메타 데이터를 추출 
  """
  system_prompt = """
    Analyze the provided markdown text. 
    Return a JSON object with the following keys:
    - "summary": A one-sentence summary of the content (Korean).
    - "keywords": A list of top 5 key concepts or tech stacks (English/Korean mixed).
    - "category": Choose one from [Technical, Business, General, Memo].
    
    Output JSON only. No markdown formatting.
    """
  try:
    response = await ai_client.chat.completions.create(
      model=settings.OPENROUTER_MODEL,
      messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Text:\n{text_preview[:3000]}"} 
      ],
      temperature=0.3,
      response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content

    if content.startswith("```"):
      content = re.sub(r"^```json\s*", "", content)
      content = re.sub(r"^```\s*", "", content)
      content = re.sub(r"```$", "", content)
    
    return json.loads(content)
  except Exception as e:
    logger.warning(f"⚠️ Metadata extraction failed: {e}")
    # 실패해도 죽지 않고 빈 값 리턴 (기본 로직은 돌아가야 하므로)
    return {
      "summary": "failed",
      "keywords": [],
      "category": "Uncategorized"
      }


async def get_embeddings(text_chunks: list[str]) -> list[list[float]]:
  """
  openRouter 에서 받아서 임베딩 생성
  """
  try:
    response = await ai_client.embeddings.create(
      model=settings.OPENROUTER_EMBEDDING_MODEL,
      input=text_chunks,
    )

    return [data.embedding for data in response.data]
  except Exception as e:
    logger.error(f"❌ OpenRouter Embedding Error: {e}")
    raise e

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
      # mime_type = task_data.get("mimeType")

      logger.info(f"📚 [Start] RAG Job | DocID: {doc_id}")

      # 2. MinIO 파일 다운로드
      logger.info(f"📥 Downloading: {minio_key} ({bucket_name})")
      file_content = await minio_client.get_file_content(
          object_name=minio_key, 
          bucket_name=bucket_name
      )
      
      if not file_content:
          raise ValueError("File content is empty")

      text_content = file_content.decode("utf-8")

      file_size_kb = len(file_content) / 1024
      logger.info(f"✅ Downloaded: {file_size_kb:.2f} KB")
      logger.info("🏷️ Extracting Metadata via LLM...")
      extracted_meta = await extract_metadata_from_llm(text_content)
      logger.info(f"🏷️ Extracted: {extracted_meta}")

      # 3. 천킹 (헤더 기준, 문자수 기준)
      # 3-1. 헤더 기준 크게 자르기 
      headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
      ]
      markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
      md_header_splits = markdown_splitter.split_text(text_content)
      
      # 3-2. 문자수 기준 작은 단위로 재귀 자르기
      text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
      )
      final_chunks = text_splitter.split_documents(md_header_splits)

      chunk_texts = [chunk.page_content for chunk in final_chunks]
      logger.info(f"🧩 Chunking Complete: {len(chunk_texts)} chunks generated.")

      # 4. 임베딩 생성
      embeddings = await get_embeddings(chunk_texts)
      logger.info(f"🧠 Embedding Complete: {len(embeddings)} vectors generated.")

      # 5. DB 저장
      # async with AsyncSessionLocal() as db:
      vector_docs = []
      for idx, (chunk_obj, vector) in enumerate(zip(final_chunks, embeddings)):
        combined_meta = {
          **chunk_obj.metadata, # 
          **extracted_meta,
        }

        vector_docs.append(VectorizedDoc(
          chunk_index=idx,
          content=chunk_obj.page_content,
          meta_data=combined_meta,
          token_count=len(chunk_obj.page_content),
          embedding=vector,
          embedding_model=settings.OPENROUTER_EMBEDDING_MODEL,
          knowledge_doc_id=doc_id,
          uploader_id=task_data.get("uploaderId")
        ))
      # db.add_all(vector_docs)
      # await db.commit()
      # logger.info(f"💾 DB Insert Complete: {len(vector_docs)} rows.")

      async with AsyncSessionLocal() as db:
        try:
            db.add_all(vector_docs)
            await db.commit()
            logger.info(f"💾 DB Insert Complete: {len(vector_docs)} rows.")
        except Exception as e:
            await db.rollback() # 에러 나면 롤백
            raise e # 에러 다시 던져서 바깥 try-except에 잡히게 함
      
      # 6. 성공 Webhook
      await send_webhook(
          doc_id=doc_id, 
          status="COMPLETED", 
          result_meta={
            "chunkCount": len(final_chunks),
            "embeddingModel": settings.OPENROUTER_EMBEDDING_MODEL,
          }
      )
      logger.info(f"✅ Job Finished: {doc_id}")

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
          result = await redis_client.brpop("ai:job:queue", timeout=5)

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