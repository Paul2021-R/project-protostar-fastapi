import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector  # pgvector 필수
from core.database import Base

class VectorizedDoc(Base):
  __tablename__ = "vectorized_docs"

  id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

  chunk_index = Column(Integer, nullable=False)
  content = Column(Text, nullable=False)
  meta_data = Column(JSONB, nullable=False)
  token_count = Column(Integer, default=0)

  embedding = Column(Vector(1536))
  embedding_model = Column(String, default="openrouter/text-embedding-3-small")

  knowledge_doc_id = Column(String, nullable=False)
  uploader_id = Column(String, nullable=False)

  created_at = Column(DateTime, default=datetime.utcnow)