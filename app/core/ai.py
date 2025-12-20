import os
import glob
from typing import List, Optional
from openai import AsyncOpenAI
from core.config import settings

GLOBAL_SYSTEM_PROMPT: str = ''
GLOBAL_KNOWLEDGE_BASE: str = '' 

# 1. OpenRouter 클라이언트 설정
# Base URL을 반드시 'https://openrouter.ai/api/v1'으로 설정해야 함
client = AsyncOpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    # [권장] OpenRouter에 내 앱 정보를 알려주는 헤더
    default_headers={
        "HTTP-Referer": settings.SITE_URL, 
        "X-Title": settings.SITE_NAME,
    }
)

def read_markdown_files(directory: str) -> str:
    """
    디렉토리 내의 모든 md 파일을 찾아 하나의 문자열로 합치기
    """
    combined_text = []
    file_paths = glob.glob(os.path.join(directory, "*.md"))
    file_paths.sort()

    for file_path in file_paths:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                filename = os.path.basename(file_path)
                combined_text.append(f"### [Source: {filename}]\n{content}")
        
        except Exception as e:
            print(f"⚠️ Failed to read {file_path}: {e}")
    return "\n\n".join(combined_text)

async def init_ai_context():
    """
    서버 시작 시 호출하여 전체 시스템 프롬프트 로드 
    """

    global GLOBAL_SYSTEM_PROMPT
    global GLOBAL_KNOWLEDGE_BASE

    base_dir = "prompts"
    # 1. 시스템 프롬프트 로드
    print(f"📂 Loading System Prompts from {base_dir}/system/...")
    system_text = read_markdown_files(os.path.join(base_dir, "system"))
    if system_text:
        GLOBAL_SYSTEM_PROMPT = system_text
        print(f"✅ System Prompt Loaded ({len(GLOBAL_SYSTEM_PROMPT)} chars)")
    else:
        print("⚠️ No system prompts found. Using default.")
    
    # 2. 지식 데이터 로드 
    print(f"📂 Loading User Data from {base_dir}/user_data/...")
    knowledge_text = read_markdown_files(os.path.join(base_dir, "user_data"))
    if knowledge_text:
        GLOBAL_KNOWLEDGE_BASE = knowledge_text
        print(f"✅ Knowledge Base Loaded ({len(GLOBAL_KNOWLEDGE_BASE)} chars)")
    else:
        print("ℹ️ No user data found.")


async def generate_response(prompt: str, context: str = ''):
    """
    로드된 전역 변수들을 활용하여 기본 답변을 생성해낸다.
    """

    if not context:
        full_user_content = f"""

        You are an intelligent assistant named "Protostar".
        Answer the user's question based ONLY on the provided context below.
        
        <instruction>
        Answer the following question based on the context above.
        If the answer is not in the context, strictly say "I don't know based on the provided documents."
        Do not halluciation or generate external information.
        </instruction>

        <question>
        {prompt}
        </question>

        <context>
        {GLOBAL_KNOWLEDGE_BASE}
        </context>
        """
    else: 
        full_user_content = f"""

        You are an intelligent assistant named "Protostar".
        Answer the user's question based ONLY on the provided context below.
        
        <instruction>
        Answer the following question based on the context above.
        If the answer is not in the context, strictly say "I don't know based on the provided documents."
        Do not halluciation or generate external information.
        </instruction>

        <question>
        {prompt}
        </question>

        <context>
        {context}

        {GLOBAL_KNOWLEDGE_BASE}
        </context>
        """

    try:
        # 2. 비동기 호출 (Standard OpenAI Format)
        response = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": GLOBAL_SYSTEM_PROMPT},
                {"role": "user", "content": full_user_content}
            ],
            temperature=0.3,
        )
        
        # 3. 텍스트 추출
        return response.choices[0].message.content
        
    except Exception as e:
        return f"❌ OpenRouter Error: {str(e)}"