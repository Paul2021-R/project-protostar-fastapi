import os
import glob
import logging
from textwrap import dedent
from openai import AsyncOpenAI
from core.config import settings

# [전역 변수] 문단 단위로 쪼개진 지식 조각들 (Chunks)
KNOWLEDGE_CHUNKS = []

logger = logging.getLogger("uvicorn")

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
            logger.error(f"⚠️ Error loading {file_path}: {e}")
            
    return chunks

async def generate_response_stream(
    prompt: str, 
    mode: str = 'general',
    context: str = '', # worker.py에서 검색된 RAG 데이터가 여기에 들어옵니다.
    history: list[dict] = None
):
    if history is None:
        history = []

    # ---------------------------------------------------------
    # 1. 시스템 프롬프트 구성 (페르소나 & 규칙 정의)
    # ---------------------------------------------------------
    # context(RAG 검색 결과)가 있으면 포함시키고, 없으면 '정보 없음' 처리
    context_block = ""
    if context:
        context_block = f"""
<relevant_documents>
{context}
</relevant_documents>
"""

    system_instruction = dedent(f"""
    당신은 류한솔 개발자의 기술 블로그 및 포트폴리오를 담당하는 AI 비서 'Protostar(프로토스타)'입니다.
    
    [Role & Purpose]
    - 당신의 주 목적은 질문자에게 **류한솔(Paul)** 의 경력, 기술 스택, 프로젝트 경험을 전달해주는 것입니다.
    - 제공된 <relevant_documents> 정보를 최우선 근거로 사용하여 답변해야 합니다.
    
    [Strict Rules]
    1. **Language**: **한국어**로 답변하십시오. 다른 언어가 들어올 때만 이에 맞게 대응하십시오.
    2. **Context First**: 
       - <relevant_documents>에 있는 내용이라면, 해당 내용을 요약 및 인용하여 전문적으로 답변하십시오.
       - 문서에 없는 내용이지만 개발/IT 일반 상식이라면 답변하되, "제공된 문서에는 없지만 일반적인 지식으로는..." 이라고 서두를 떼십시오.
       - **블로그/이력/개발과 전혀 무관한 질문**(예: 오늘 점심 메뉴 추천, 연예인 가십 등)에는 "죄송합니다. 저는 기술 블로그 안내를 위한 AI이므로 해당 질문에는 답변드리기 어렵습니다."라고 정중히 거절하십시오.
    3. **Tone & Manner**:
       - 공손하고 친절하며 전문적인 '비서'의 말투를 사용하십시오.
       - 적절한 이모지(😊, 💡, 🚀 등)를 사용하여 딱딱하지 않게 답변하십시오.
    4. **Format**:
       - 핵심 결론을 먼저 제시하고(두괄식), 부연 설명을 하위에 작성하십시오.
       - 답변은 가독성을 위해 3문단 이내로 간결하게 구성하십시오.
       - 답변 양식으로 Markdown 문법은 쓰지 말며, 띄워쓰기, 줄바꿈등을 포함한 일반 텍스트 방식으로 답변하며, 강조가 필요시 ', "  를 사용하거나, 제목을 작성 시 [] 를 사용하십시아.
    {context_block}
    """).strip()

    # ---------------------------------------------------------
    # 2. 메시지 배열 구성
    # ---------------------------------------------------------
    # [System Message] -> [History] -> [User Question] 순서
    messages = [
        {"role": "system", "content": system_instruction}
    ]
    
    # 히스토리 추가 (System 메시지 바로 뒤에 붙임)
    if history:
        messages.extend(history)
        
    # 현재 사용자 질문 추가
    messages.append({"role": "user", "content": prompt})

    try:
        # ---------------------------------------------------------
        # 3. LLM 호출 및 스트리밍
        # ---------------------------------------------------------
        stream = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL, # worker.py의 설정을 따름
            messages=messages,
            stream=True,
            temperature=0.7, # 창의성과 사실성의 밸런스
            # max_tokens=1000, # 필요 시 제한
        )

        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    except Exception as e:
        logger.error(f"❌ AI Generation Error: {e}")
        raise e

async def generate_summary(original_text: str, model: str = None) -> dict:
    """
    Main Worker 의 답변을 요약하는 함수
    - 입력 : 원본 답변 텍스트
    - 출력 : {"summary": "요약된 텍스트", "usage": {input, output, model}}
    """

    if not original_text:
        return {"summary": "", "usage": {}}

    if len(original_text) < 150:
        return {
            "summary": original_text, 
            "usage": {
                "input": 0,
                "output": 0,
                "model": "bypass"
            }
        }

    system_prompt = dedent("""
    당신은 대화 요약 전문가입니다. AI 어시스턴트의 답변을 3문장 이내의 한 문단으로 요약합니다.

    ## 요약 원칙
    1. **핵심 결론/답변**을 첫 문장에 배치
    2. **구체적 데이터**(숫자, 이름, 코드명 등)는 반드시 보존
    3. **사용자가 다음 질문에 활용할 맥락**을 우선 포함

    ## 제외 대상
    - 인사말, 부연 설명, 예시의 상세 내용
    - "~할 수 있습니다", "~것 같습니다" 등의 완곡 표현

    ## 출력 형식
    - 한 문단, 3문장 이내
    - 존댓말 없이 간결한 정보 전달체 사용
    """).strip()
    
    try:
        target_model = model if model else settings.OPENROUTER_MODEL

        response = await client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": original_text}
            ],
            stream=False,
            temperature=0.3,
        )

        summary_text = response.choices[0].message.content.strip()
        usage_info = response.usage

        if usage_info:
            input_tokens = usage_info.prompt_tokens
            output_tokens = usage_info.completion_tokens
        else:
            logger.warning("⚠️ Usage info missing in API response.")
            input_tokens = 0
            output_tokens = 0

        return {
            "summary": summary_text,
            "usage": {
                "input": input_tokens,
                "output": output_tokens,
                "model": target_model
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Summary Generation Error: {str(e)}")
        return {
            "summary": original_text[:500],
            "usage": {}
        }