from app.core.config import Settings, config


def test_config_loads_basic_settings() -> None:
    """配置对象能正常加载 .env 和默认值。"""
    assert config.app_name == "meeting-execution-agent"
    assert config.api_port == 8003
    assert config.mysql_database == "meeting_execution_agent"
    assert config.embedding_dimensions == 1024
    assert config.qdrant_url.startswith("http")
    assert config.dashscope_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_dashscope_defaults_use_qwen_plus() -> None:
    """默认模型配置不依赖本地 .env 覆盖。"""
    settings = Settings(_env_file=None)

    assert settings.llm_model == "qwen-plus"
    assert settings.embedding_model == "text-embedding-v3"
    assert settings.embedding_dimensions == 1024
    assert settings.linear_api_url == "https://api.linear.app/graphql"
