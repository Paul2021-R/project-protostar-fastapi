import os

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379"
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/protostar_prod"

    OPENROUTER_API_KEY: str = ''
    OPENROUTER_MODEL: str = '' 
    SITE_URL: str = 'https://service-protostar.ddns.net'
    SITE_NAME: str = "Protostar Service"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()