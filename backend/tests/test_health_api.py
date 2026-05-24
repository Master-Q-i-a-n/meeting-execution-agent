from fastapi.testclient import TestClient


def test_health_api(client: TestClient) -> None:
    """基础健康检查不依赖外部服务，应该始终可用。"""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "meeting-execution-agent",
    }
