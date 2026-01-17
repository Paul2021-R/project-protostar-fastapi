from pydantic_settings import BaseSettings

# env 설정 기반으로 덮어씌워짐
class Settings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379"
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/protostar_prod"

    OPENROUTER_API_KEY: str = ''
    OPENROUTER_MODEL: str = '' 
    OPENROUTER_EMBEDDING_MODEL: str = ''
    SITE_URL: str = 'https://service-protostar.ddns.net'
    SITE_NAME: str = "Protostar Service"

    # MinIO 설정
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "admin"
    MINIO_SECRET_KEY: str = "admin"
    MINIO_BUCKET_NAME: str = "protostar-knowledge"
    MINIO_SECURE: bool = False  # True면 https, False면 http
    
    LOG_LEVEL: str = "INFO"

    NEST_API_URL: str = "http://localhost:5859"
    INTERNAL_WEBHOOK_SECRET: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()