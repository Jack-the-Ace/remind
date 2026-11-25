from typing import Literal

from pydantic import BaseModel, Field


class HistoryItem(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    destination: str = Field(default="", max_length=100)
    theme: str = Field(default="", max_length=100)
    selected: bool | None = None
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    note: str = Field(default="", max_length=300)


class UserProfile(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=50)
    ageRange: str = Field(default="", max_length=30)
    personalityNotes: str = Field(min_length=1, max_length=700)
    mbti: str = Field(default="", max_length=12)
    travelPreferences: str = Field(min_length=1, max_length=700)
    avoidConditions: str = Field(default="", max_length=400)
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)


class RecommendationRequest(BaseModel):
    profile: UserProfile
    mood: str = Field(min_length=1, max_length=500)
    language: Literal["ko", "en"] = "ko"


class Destination(BaseModel):
    name: str
    region: str
    reason: str


class Recommendation(BaseModel):
    empathyMessage: str
    moodSummary: str
    travelTheme: str
    recommendedDestinations: list[Destination] = Field(min_length=3, max_length=3)
    recommendationReasons: list[str] = Field(min_length=3, max_length=3)
    preferredActivities: list[str] = Field(min_length=1, max_length=6)
    avoidConditions: list[str] = Field(default_factory=list, max_length=6)
    changeFromPrevious: str
    confidenceNotes: str


class RecommendationResponse(BaseModel):
    recommendation: Recommendation
    model: str
