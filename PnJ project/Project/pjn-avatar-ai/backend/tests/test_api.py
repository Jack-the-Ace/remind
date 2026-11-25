from fastapi.testclient import TestClient

from app.llm import build_messages
from app.main import app
from app.models import RecommendationRequest
from app.seed_data import SEED_USERS


def test_prompt_requires_no_fake_history_and_optional_mbti():
    request = RecommendationRequest(profile=SEED_USERS[2], mood="I feel drained.", language="en")
    system = build_messages(request)[0]["content"]
    assert "Never invent prior records" in system
    assert "MBTI is optional" in system


def test_missing_key_returns_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = TestClient(app).post("/api/recommendations", json={"profile": SEED_USERS[0], "mood": "조용히 쉬고 싶어요", "language": "ko"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LLM_NOT_CONFIGURED"
