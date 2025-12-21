import os
import glob
from textwrap import dedent
from openai import AsyncOpenAI
from core.config import settings

# [전역 변수] 문단 단위로 쪼개진 지식 조각들 (Chunks)
KNOWLEDGE_CHUNKS = []

client = AsyncOpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": settings.SITE_URL, 
        "X-Title": settings.SITE_NAME,
    }
)

def load_and_chunk_files(directory: str):
    """
    MD 파일을 읽어서 '문단(\n\n)' 단위로 쪼개서 리스트에 저장함.
    이게 RAG의 핵심인 'Chunking' 과정입니다.
    """
    chunks = []
    file_paths = glob.glob(os.path.join(directory, "*.md"))
    
    for file_path in file_paths:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                filename = os.path.basename(file_path)
                
                # 1. 문단 단위로 분리 (빈 줄 기준)
                raw_chunks = content.split("\n\n")
                
                # 2. 의미 있는 내용만 저장
                for i, text in enumerate(raw_chunks):
                    if len(text.strip()) > 10:  # 너무 짧은 건 무시
                        chunks.append(f"[Source: {filename} / Para {i+1}]\n{text.strip()}")
        except Exception as e:
            print(f"⚠️ Error loading {file_path}: {e}")
            
    return chunks

async def init_ai_context():
    global KNOWLEDGE_CHUNKS
    base_dir = "prompts"
    
    print(f"📂 Chunking Knowledge Base from {base_dir}/user_data/...")
    KNOWLEDGE_CHUNKS = load_and_chunk_files(os.path.join(base_dir, "user_data"))
    
    print(f"✅ Total Knowledge Chunks: {len(KNOWLEDGE_CHUNKS)}")


def retrieve_relevant_chunks(query: str, top_k: int = 3) -> str:
    """
    [Retrieval] 질문과 관련된 문단만 찾아내는 검색 엔진
    """
    if not KNOWLEDGE_CHUNKS:
        return ""

    query_tokens = set(query.split()) # 질문을 단어로 쪼갬
    scores = []

    for chunk in KNOWLEDGE_CHUNKS:
        # 문단 안에 질문의 단어가 몇 개나 포함되어 있는지 점수 계산
        score = sum(1 for token in query_tokens if token in chunk)
        if score > 0:
            scores.append((score, chunk))
    
    # 점수 높은 순으로 정렬해서 top_k개만 뽑음
    scores.sort(key=lambda x: x[0], reverse=True)
    top_results = [item[1] for item in scores[:top_k]]
    
    if not top_results:
        return "" # 관련 내용이 하나도 없으면 빈 문자열 반환

    return "\n\n---\n\n".join(top_results)


async def generate_response(prompt: str, context: str = ''):
    # 1. Retrieval (검색): 질문과 관련된 자료만 가져오기
    # 사용자가 직접 넘겨준 context가 있으면 그걸 우선, 없으면 DB에서 검색
    found_context = context if context else retrieve_relevant_chunks(prompt)

    # 2. Generation (생성): 찾은 자료가 없으면 바로 모른다고 하기
    if not found_context:
        return "죄송합니다. 학습된 문서 내에서 해당 질문에 대한 정보를 찾을 수 없습니다."

    # 3. 프롬프트 조립 (자료가 있으니 답변 생성)
    full_prompt = dedent(f"""
    <relevant_documents>
    {found_context}
    </relevant_documents>

    <instruction>
    You are 'Protostar', a strict AI assistant.
    Answer the user's question using **ONLY** the information in <relevant_documents>.
    
    Rules:
    1. If the exact answer is not in the documents, say "문서에 내용이 없습니다."
    2. Do NOT summarize the whole document, just answer the specific question.
    3. Answer in Korean.
    </instruction>

    <user_question>
    {prompt}
    </user_question>
    """).strip()

    try:
        response = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            temperature=1, # 사실 기반 답변
        )
        return response.choices[0].message.content
        
    except Exception as e:
        return f"❌ AI Error: {str(e)}"