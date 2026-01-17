import logging
from sqlalchemy import select
from core.database import AsyncSessionLocal
from core.vectorized_doc import VectorizedDoc 
from core.worker_knowledge import get_embeddings # 임베딩 함수 재사용, 나중에 AI 쪽 리펙토링 필요

logger = logging.getLogger("uvicorn")

async def search_similar_docs(query: str, top_k: int = 3):
  """
  질문과 가장 유사한 문서를 DB 에서 검색 (Cosine Similarity)
  """

  try:
    # 1 질문을 벡터로 변환 
    query_vectors = await get_embeddings([query])
    
    if not query_vectors:
      logger.warning("⚠️ Failed to generate embedding for query.")
      return []
    
    query_embedding = query_vectors[0]

    async with AsyncSessionLocal() as db:
      stmt = (
        select(VectorizedDoc)
        .order_by(VectorizedDoc.embedding.cosine_distance(query_embedding))
        .limit(top_k)
      )

      result = await db.execute(stmt)
      docs = result.scalars().all()
      
      logger.info(f"🔍 RAG Search found {len(docs)} docs for: '{query}'")
      return docs

  except Exception as e:
    logger.error(f"❌ Search Similar Docs Error: {e}")
    raise e

def format_rag_context(docs: list[VectorizedDoc]) -> str:
  """
  검색된 문서들을 LLM 프롬프트에 넣기 좋게 텍스트로 변환
  """

  if not docs:
    return ""

  context_list = []
  for i, doc in enumerate(docs):
    meta = doc.meta_data if doc.meta_data else {}
    keywords = ", ".join(meta.get('keywords', [])) 
    summary = meta.get('summary', 'No summary')

    source_block = f"""
    [Document #{i+1}]
    - Keywords: {keywords}
    - Summary: {summary}
    - Content:
    {doc.content}
    """

    context_list.append(source_block)
    
  return "\n\n--\n\n".join(context_list)
