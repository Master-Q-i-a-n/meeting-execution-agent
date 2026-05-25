from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "meeting-execution-agent"
    app_env: str = "local"
    debug: bool = Field(default=True, validation_alias="APP_DEBUG")

    api_host: str = "127.0.0.1"
    api_port: int = 8003
    api_log_level: str = "info"

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "meeting_execution_agent"
    sql_echo: bool = False

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/0"
    qdrant_url: str = "http://127.0.0.1:6333"

    # 百炼提供 OpenAI 兼容接口，后面的业务代码不用感知底层平台差异。
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 2000

    embedding_model: str = "text-embedding-v3"
    embedding_dimensions: int = 1024

    linear_api_key: str | None = None
    linear_api_url: str = "https://api.linear.app/graphql"
    linear_default_team_id: str | None = None

    langsmith_api_key: str | None = None
    langsmith_tracing: bool = True
    langsmith_project: str = "meeting-execution-agent-evals"
    langsmith_endpoint: str | None = None

    agent_max_steps: int = 12
    agent_timeout_seconds: int = 120

    @computed_field
    @property
    def mysql_url(self) -> str:
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+aiomysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


config = get_settings()
