"""Runtime configuration loaded from environment variables or a .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_base_url: str = "http://ollama:11434"
    model_name: str = "llama3"
    ingress_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
