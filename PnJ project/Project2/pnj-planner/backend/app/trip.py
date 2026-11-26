"""Validate and normalize the travel conditions accepted by the offline demo."""
from datetime import date, timedelta
from typing import Literal

from .sources import external_context
from .survey_stats import provenance

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Lock(StrictModel):
    day: int = Field(ge=1, le=14)
    source: Literal["example","user"] = "user"
    label: str = Field(min_length=1, max_length=180)
    place: str | None = Field(default=None, max_length=160)
    start: str | None = None
    end: str | None = None

    @field_validator("start", "end")
    @classmethod
    def time_or_unknown(cls, value):
        if value in (None, ""):
            return None
        parts = value.split(":")
        if (len(parts) != 2 or any(len(p) != 2 or not p.isdigit() for p in parts)
                or int(parts[0]) > 23 or int(parts[1]) > 59):
            raise ValueError("Use HH:MM for an appointment time.")
        return value


class Trip(StrictModel):
    days: int | None = Field(default=None, ge=1, le=14)
    startDate: date | None = None
    lodging: str | None = Field(default=None, max_length=180)
    lodgingSource: Literal["example","user"] | None = None
    startPoint: str | None = Field(default=None, max_length=180)
    returnPoint: str | None = Field(default=None, max_length=180)
    companions: str | None = Field(default=None, max_length=100)
    transport: str | None = Field(default=None, max_length=100)
    diet: str | None = Field(default=None, max_length=200)
    walking: Literal["any", "low", "stepFree"] = "any"
    budgetKrw: int | None = Field(default=None, ge=0, le=100000000)
    indoor: Literal["any", "prefer", "only"] = "any"
    weather: Literal["unknown", "rain", "clear"] = "unknown"
    interests: list[str] = Field(default_factory=list, max_length=32)
    mustVisit: list[str] = Field(default_factory=list, max_length=33)
    avoid: list[str] = Field(default_factory=list, max_length=40)
    locked: list[Lock] = Field(default_factory=list, max_length=56)
    availableMinutes: int | None = Field(default=None, gt=0, le=20160)
    avoidHeights: bool = False

    @property
    def slots(self):
        # A flexible experience has one display group, not a booked one-day trip.
        return self.days or max((lock.day for lock in self.locked), default=1)

    @property
    def groups(self):
        if self.days is None:
            return [*sorted({lock.day for lock in self.locked}), None]
        return list(range(1, self.days + 1))

    @field_validator("startDate", "days", "availableMinutes", "budgetKrw", "lodging", "startPoint", "returnPoint", "transport", "companions", "diet", mode="before")
    @classmethod
    def blank_date(cls, value):
        return None if value == "" else value

    @field_validator("interests", "mustVisit", "avoid")
    @classmethod
    def clean_terms(cls, values):
        if any(not term or len(term) > 100 for term in values):
            raise ValueError("Use a short non-empty term.")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def days_in_trip(self):
        if self.startDate is not None:
            try:
                self.startDate + timedelta(days=self.slots - 1)
            except OverflowError:
                raise ValueError("The trip end date is out of range. 여행 종료 날짜를 확인하세요.") from None
        if self.days is not None and any(lock.day > self.days for lock in self.locked):
            raise ValueError("A fixed day falls outside the trip. 여행 기간 밖에 고정 일정이 있습니다.")
        return self


def weather_snapshot(scenario):
    # A scenario can be explored without dates. Its value is never a forecast.
    return {"provider": "scenario" if scenario != "unknown" else "offline", "scenario": scenario,
            "forecast": None, "verifiedForDate": False}


def integrations(trip, place_ids, scope="all"):
    return {**external_context(trip.startDate, place_ids),
            "weather": weather_snapshot(trip.weather),
            "statistics": {"status":"verified_historical_aggregate", "aggregate":provenance(scope)}}


