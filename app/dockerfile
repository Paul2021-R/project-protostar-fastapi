# Dockerfile

# ======= 1. Builder Stage =======
# uv가 포함된 공식 이미지 사용
FROM astral/uv:python3.13-bookworm-slim AS builder
WORKDIR /app

# 컴파일에 필요한 환경변수 설정
ENV UV_COMPILE_BYTECODE=1 
ENV UV_LINK_MODE=copy

# 의존성 파일 복사
COPY pyproject.toml uv.lock ./

# 의존성 설치 (시스템 패키지가 아닌 가상환경에 설치)
# --no-dev: 개발용 패키지 제외
# --frozen: lock 파일 기준 설치
RUN uv sync --frozen --no-dev

# ======= 2. Dev Stage (로컬 개발용) =======
# 개발용은 dev dependencies도 필요할 수 있으므로 별도 처리
FROM astral/uv:python3.13-bookworm-slim AS dev
WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
# 개발용 패키지 포함 설치
RUN uv sync --frozen

# 소스 코드는 볼륨 마운트 하므로 COPY 생략
# PATH에 가상환경 bin 추가
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ======= 3. Runner Stage (운영 배포용) =======
FROM astral/uv:python3.13-bookworm-slim AS runner
WORKDIR /app

# Builder에서 생성한 가상환경만 복사 (매우 가벼움)
COPY --from=builder /app/.venv /app/.venv

# 소스 코드 복사
COPY . .

# 가상환경을 PATH에 추가하여 별도 activate 불필요
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]