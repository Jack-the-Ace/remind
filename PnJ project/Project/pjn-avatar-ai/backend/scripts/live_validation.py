"""Run the required personalization cases against the real configured LLM.

Usage (from backend): ./.venv/Scripts/python.exe scripts/live_validation.py
Requires OPENAI_API_KEY in backend/.env. Results are written locally and ignored by Git.
"""
import asyncio
import json
from pathlib import Path

from app.llm import generate_recommendation
from app.models import RecommendationRequest
from app.seed_data import SEED_USERS


def profile(user_id: str) -> dict:
    return next(user for user in SEED_USERS if user["id"] == user_id)


CASES = [
    ("same-user-calm", profile("minji"), "마음이 복잡해서 조용히 회복하고 싶어요.", "ko"),
    ("same-user-curious", profile("minji"), "새로운 풍경을 보며 가볍게 영감을 받고 싶어요.", "ko"),
    ("different-user-same-mood", profile("junho"), "마음이 복잡해서 조용히 회복하고 싶어요.", "ko"),
    ("optional-mbti-empty-history", profile("sofia"), "I feel drained and want a gentle reset.", "en"),
    ("english-input", profile("minji"), "I want a calm weekend with a little cultural discovery.", "en"),
]


async def main():
    results = []
    for case_id, user, mood, language in CASES:
        recommendation, model = await generate_recommendation(RecommendationRequest(profile=user, mood=mood, language=language))
        results.append({
            "case": case_id, "user": user["name"], "mood": mood, "language": language, "model": model,
            "theme": recommendation.travelTheme,
            "destinations": [f"{item.name} ({item.region})" for item in recommendation.recommendedDestinations],
            "empathy": recommendation.empathyMessage,
            "changeFromPrevious": recommendation.changeFromPrevious,
        })
        print(f"✓ {case_id}: {recommendation.travelTheme}")
    output = Path(__file__).parents[1] / "live-validation-results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {output}")


if __name__ == "__main__":
    asyncio.run(main())
