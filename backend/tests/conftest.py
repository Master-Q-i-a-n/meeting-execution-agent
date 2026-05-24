import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """FastAPI 测试客户端。

    这里不真正启动 uvicorn，而是在测试进程里直接调用 app。
    适合测试基础接口，不需要浏览器或端口。
    """
    with TestClient(app) as test_client:
        yield test_client
