from fastapi import APIRouter, HTTPException

from app.integrations.linear import LinearIntegrationError, LinearTaskDispatchAdapter

router = APIRouter(tags=["integrations"])


@router.post("/integrations/linear/test")
def test_linear_integration():
    """校验 Linear API Key 和默认 Team 是否可用。"""
    try:
        return LinearTaskDispatchAdapter().test_connection()
    except LinearIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
