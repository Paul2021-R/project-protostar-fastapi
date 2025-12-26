# Protostar FastAPI (AI Worker)

**Project Protostar**의 AI Worker 서비스로, RAG(Retrieval-Augmented Generation) 파이프라인과 LLM 추론 요청을 비동기로 처리합니다.
NestJS가 발행한 작업을 Redis Queue에서 구독(Consume)하여 처리한 뒤, 결과를 업데이트합니다.

## 🏗 아키텍처 (Architecture)

본 프로젝트는 **Python** 환경의 장점을 살려 AI/ML 라이브러리 활용을 극대화하도록 설계되었습니다.

### 핵심 역할
1.  **AI Worker**: Redis(BullMQ)를 구독하며 대기하다가, 메시지 생성 요청이 오면 작업을 수행합니다.
2.  **RAG Pipeline**: 문서 임베딩 검색 및 컨텍스트 구성을 담당합니다.
3.  **LLM Interface**: 외부 LLM API (OpenAI, Gemini 등) 혹은 로컬 모델과의 통신을 추상화합니다.

### 기술 스택 (Tech Stack)
-   **Framework**: FastAPI (Python 3.10+)
-   **Queue Consumer**: Redis (BullMQ 호환 처리)
-   **AI Logic**: LangChain (implied), Vector Handling
-   **Package Manager**: `uv` (Fast Python Package Installer)

---

## 📂 프로젝트 구조 (Project Structure)

```
app/
├── core/
│   ├── worker.py    # Redis Queue 구독 및 이벤트 루프 처리
│   ├── ai.py        # 실제 AI 로직 (LLM 호출, 프롬프트 조합)
│   ├── database.py  # DB 연결 (필요 시)
│   └── redis.py     # Redis 연결 설정
├── prompts/         # 시스템 프롬프트 및 페르소나 관리
│   ├── system/
│   └── user_data/
├── main.py          # 앱 진입점
└── pyproject.toml   # 의존성 관리
```

---

## 🚀 시작하기 (Getting Started)

### 사전 요구사항 (Prerequisites)
- Python 3.10+
- `uv` (권장 패키지 매니저)
- Docker & Docker Compose
- Redis (필수)

### 설치 및 실행 (Installation & Run)

#### 1. 환경 설정
`init.env` 내용을 참고하여 `.env` 파일을 생성합니다.

```bash
# .env 예시
REDIS_HOST="localhost"
REDIS_PORT=6379
OPENAI_API_KEY="sk-..."
```

#### 2. 로컬 개발 모드 실행

```bash
# Docker Compose 기반 실행
docker compose up fastapi-dev
```

#### 3. 배포 
app 폴더 상위 루트는 production 을 위하여 준비된 구성입니다. 

---

## 🔗 관련 문서 (References)
- **AI Rules & Guide**: [docs/guide](../../docs/guide)
- **Architecture Note**: [ArchitectNote.md](../../docs/project-official/ArchitectNote.md)
