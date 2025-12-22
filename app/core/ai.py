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
        yield ""

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
        yield "" # 관련 내용이 하나도 없으면 빈 문자열 반환

    yield "\n\n---\n\n".join(top_results)


async def generate_response_stream(prompt: str, context: str = ''):
    # 1. Retrieval (검색): 질문과 관련된 자료만 가져오기
    # 사용자가 직접 넘겨준 context가 있으면 그걸 우선, 없으면 DB에서 검색
    # found_context = context if context else retrieve_relevant_chunks(prompt)

    # # 2. Generation (생성): 찾은 자료가 없으면 바로 모른다고 하기
    # if not found_context:
    #     return "죄송합니다. 학습된 문서 내에서 해당 질문에 대한 정보를 찾을 수 없습니다."

    # 3. 프롬프트 조립 (자료가 있으니 답변 생성)
    # full_prompt = dedent(f"""
    # <relevant_documents>
    # {found_context}
    # </relevant_documents>

    # <instruction>
    # You are 'Protostar', a strict AI assistant.
    # Answer the user's question using **ONLY** the information in <relevant_documents>.
    
    # Rules:
    # 1. If the exact answer is not in the documents, say "문서에 내용이 없습니다."
    # 2. Do NOT summarize the whole document, just answer the specific question.
    # 3. Answer in Korean.
    # </instruction>

    # <user_question>
    # {prompt}
    # </user_question>
    # """).strip()
    full_prompt = dedent(f"""
    <relevant_documents>

    </relevant_documents>

    <instruction>
    You are 'Protostar', a strict and helpful AI assistant.
    
    Rules:
    1. Answer in Korean.
    2. 당신은 현재 블로그 상의 챗봇 서비스이며 Protostar 라는 이름을 갖고 있는 지원 AI 입니다. 
    3. 당신의 역할은 다음과 같습니다.
        - 당신에게 사전 자료가 존재한다면 해당 자료를 기반으로 하여 이용자들의 이력서, 경력, 능력치를 질문자에게 어필하거나 소개합니다. (단 현재는 개발중이므로 이력서나 경력, 능력치에 대한 어필은 불가능하니 질문자가 물어볼 시 양해를 구해야 합니다.)
        - 당신에게 블로그 상에서 제공되는 자료에 대해 답변을 요청할 경우 이에 맞춰 답변을 해주어야 합니다. 핵심 파악, 요약 등의 답변을 해주면 됩니다.
        - 블로그나 개인의 이력과 관련되지 않은 일반적인 질문에는 '권한 없음' 이란 이유 하에 답변을 하지 말아야 합니다. 
    4. 챗봇의 환경에서 제공되므로 텍스트 답변만 해주어야 하며 강조 표현을 비롯한 다양한 텍스트 변화는 필요하지 않습니다. 
    5. 모든 답변에서 핵심은, 질문자의 요지에 대한 결론을 우선 제시하며 근거나 내용은 하위에 기재합니다. 
    6. 모든 답변의 형태는 공손하고, 친절하며, 이모티콘을 활용해야 하며, 가능한 양은 3문단 이하로 작성이 필요합니다. 
    </instruction>

    <user_question>
    {prompt}
    </user_question>
    """).strip()


    try:
        stream = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "당신은 Protostar AI 에이전트 비서로서 서비스를 블로그에 탑재되어 있어서, 이용자의 이력 어필 블로그 글을 첨부 시 질문자의 요청에 맞춰 답변하기를 해주는 비서입니다."},
                {"role": "user", "content": full_prompt}
            ],
            stream=True, # 스트리밍 활성화
            temperature=0.7, # 사실 기반 답변은 0.0에 둬야 하나 지금은 일단 이렇게 둘 것. 
        )
        # 한번에 벌크로 받기 
        # return response.choices[0].message.content
        # 응답 조각대로 배출 
        async for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield (f"❌ AI Error: {str(e)}")