import asyncio
from minio import Minio
from minio.error import S3Error
import logging
from core.config import settings

logger = logging.getLogger("uvicorn")

class MinioClientWrapper:
  def __init__(self):
    self.client = Minio(
      endpoint=settings.MINIO_ENDPOINT,
      access_key=settings.MINIO_ACCESS_KEY,
      secret_key=settings.MINIO_SECRET_KEY,
      secure=settings.MINIO_SECURE,
    )
    self.bucket_name = settings.MINIO_BUCKET_NAME

  async def check_connection(self):
    """
    서버 상태 확인용
    """

    try:
      # 비동기로 동작
      found = await asyncio.to_thread(
        self.client.bucket_exists,
        self.bucket_name
      )

      if found : 
        logger.info(f"✅ MinIO Connected & Bucket '{self.bucket_name}' Found")
      else:
        logger.warning(f"⚠️ Bucket '{self.bucket_name}' not found!")
    except Exception as e:
      logger.error(f"❌ MinIO Connection Failed: {e}")

  async def get_file_content(self, object_name: str, bucket_name: str = None) -> bytes:
    """
    MinIO 에서 원본 데이터를 다운 + 바이트로 변환함.
    """
    target_bucket = bucket_name if bucket_name else self.bucket_name
    response = None
    try:
      response = await asyncio.to_thread(
        self.client.get_object,
        target_bucket,
        object_name
      )

      # 데이터 읽는 과정 IO 블로킹 막기, 스레드 처리
      content = await asyncio.to_thread(response.read)
      return content
    except S3Error as e:
      logger.error(f"❌ MinIO File Download Failed: {e}")
    finally:
      if response:
        response.close()

minio_client = MinioClientWrapper()
    