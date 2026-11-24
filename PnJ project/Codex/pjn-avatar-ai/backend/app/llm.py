import json
import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, AuthenticationError, RateLimitError

from .models import Recommendation, RecommendationRequest

load_dotenv()

RESPONSE_SCHEMA = {
    "name": "personalized_travel_recommendation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "empathyMessage": {"type": "string"}, "moodSummary": {"type": "string"},
            "travelTheme": {"type": "string"},
            "recommendedDestinations": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "region": {"type": "string"}, "reason": {"type": "string"}}, "required": ["name", "region", "reason"]}},
            "recommendationReasons": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "string"}},
            "preferredActivities": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "string"}},
            "avoidConditions": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
            "changeFromPrevious": {"type": "string"}, "confidenceNotes": {"type": "string"},
        },
        "required": ["empathyMessage", "moodSummary", "travelTheme", "recommendedDestinations", "recommendationReasons", "preferredActivities", "avoidConditions", "changeFromPrevious", "confidenceNotes"],
    },
}


def build_messages(request: RecommendationRequest) -> list[dict[str, str]]:
    language = "Korean" if request.language == "ko" else "English"
    system = f"""You are PnJ, one warm and friendly travel-avatar voice. Return only valid JSON matching the supplied schema. Write every text field in {language}.
Use the user's stated current mood as a major input, together with preferences, avoid conditions, and actual history. Recommend exactly three feasible travel destinations or travel concepts with a real place name and region. Do not violate avoid conditions.
Be empathetic without diagnosing, treating, or claiming psychological facts. MBTI is optional context only: never stereotype or conclude personality from it. Test persona notes are fictional, not clinical results. Never invent prior records; if history is empty, explicitly say there is no previous recommendation to compare. Do not cite research, statistics, or facts you cannot support. Make changeFromPrevious specifically compare only with the records included, or state that comparison is unavailable."""
    payload = {"profile": request.profile.model_dump(), "currentMood": request.mood}
    return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured on the server.")
    return AsyncOpenAI(api_key=key, timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")))


async def generate_recommendation(request: RecommendationRequest) -> tuple[Recommendation, str]:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    completion = await get_client().chat.completions.create(
        model=model,
        messages=build_messages(request),
        response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
        temperature=0.65,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("The LLM returned an empty response.")
    return Recommendation.model_validate_json(content), model


LLM_ERRORS = (APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError, APIError)
