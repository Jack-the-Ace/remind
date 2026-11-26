"""Persist immutable per-account proposals. An exposure never implies a visit."""
import json
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import planner
from .accounts import current_user, db, ranking_profile, CheckIn, record_checkin, mood_for_plan
from .survey_stats import scope_for
from .trip import Trip
from .mood import interpret

router = APIRouter(prefix="/api")

SCHEMA = """
CREATE TABLE IF NOT EXISTS planner_runs (
    id TEXT PRIMARY KEY,
    owner INTEGER NOT NULL REFERENCES users(id),
    inputs TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    owner INTEGER NOT NULL REFERENCES users(id),
    run_id TEXT NOT NULL REFERENCES planner_runs(id),
    course TEXT NOT NULL,
    lang TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS proposals_by_owner ON proposals(owner, created_at);
CREATE TABLE IF NOT EXISTS decisions (
    proposal TEXT NOT NULL REFERENCES proposals(id),
    kind TEXT NOT NULL CHECK(kind IN ('selected','rejected','visited')),
    reason TEXT,
    satisfaction INTEGER CHECK(satisfaction BETWEEN 1 AND 5),
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(proposal,kind)
);
"""


def init_plans():
    with db() as conn:
        conn.executescript(SCHEMA)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkIn: CheckIn | None = None
    moodId: int | None = None
    wishText: str = Field(default="",max_length=800,repr=False)
    trip: Trip = Field(default_factory=Trip)
    language: Literal["en", "ko"] = "en"


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reject", "visit"]
    reason: str | None = Field(None, max_length=180)
    satisfaction: int | None = Field(None, ge=1, le=5, strict=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def history_for(conn, user: int):
    rows = conn.execute(
        """SELECT p.id, p.course, p.created_at, d.kind, d.reason, d.satisfaction
           FROM proposals p LEFT JOIN decisions d ON d.proposal=p.id
           WHERE p.owner=? ORDER BY p.rowid DESC, d.recorded_at DESC""", (user,)
    )
    history = []
    seen = set()
    for proposal, raw, created, kind, reason, satisfaction in rows:
        course = json.loads(raw)
        ids = [stop["id"] for day in course["days"] for stop in day["stops"]]
        if proposal not in seen:
            history.append({"action": "exposed", "placeIds": ids})
            seen.add(proposal)
        if kind:
            history.append({"action": kind, "placeIds": ids, "reason": reason,
                            "satisfaction": satisfaction, "createdAt": created})
    return history


def owned(conn, user, proposal):
    row = conn.execute("SELECT course, lang FROM proposals WHERE id=? AND owner=?",
                       (proposal, user)).fetchone()
    if row is None:
        raise HTTPException(404, "PLAN_NOT_FOUND")
    return json.loads(row[0]), row[1]


@router.get("/places")
def places(language: Literal["en", "ko"] = "en"):
    return planner.place_options(language)


def merge_hints(conditions, hints):
    for field in ("avoid", "mustVisit"):
        conditions[field] = list(dict.fromkeys([*conditions[field], *hints.get(field, [])]))
    if hints.get("indoor") == "only":
        conditions["indoor"] = "only"
    elif hints.get("indoor") == "prefer" and conditions["indoor"] == "any":
        conditions["indoor"] = "prefer"
    if hints.get("walking") == "stepFree":
        conditions["walking"] = "stepFree"
    if hints.get("diet") and hints["diet"] != conditions["diet"]:
        conditions["diet"] = ", ".join(x for x in (conditions["diet"],hints["diet"]) if x)


@router.post("/plans")
def recommend(request: PlanRequest, user: int = Depends(current_user)):
    if request.checkIn and request.moodId is not None:
        raise HTTPException(422, "CHOOSE_ONE_CHECKIN")
    conditions = request.trip.model_dump(mode="json")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if request.checkIn:
            mood = record_checkin(conn, user, request.checkIn, planner.PLACES)
            merge_hints(conditions,mood["suggestedConditions"])
        else:
            mood = mood_for_plan(conn, user, request.moodId) if request.moodId is not None else None
            if mood:
                implicit = {k:v for k,v in mood["suggestedConditions"].items() if k not in request.trip.model_fields_set}
                merge_hints(conditions, implicit)
        if request.wishText.strip():
            _, interests, limits = interpret(request.wishText, planner.PLACES)
            conditions["interests"] = list(dict.fromkeys([*conditions["interests"], *interests]))
            merge_hints(conditions, limits)
        context = ranking_profile(conn, user)
        context["surveyScope"] = scope_for(context.pop("residenceCountry"), planner.RULES["minimumResidenceSample"])
        context["currentMood"] = mood
        history = history_for(conn, user)
        other_language = "ko" if request.language == "en" else "en"
        args = (context, context.get("currentMood") or {}, conditions, history)
        try:
            result = planner.generate(*args, request.language)
            alternate = planner.generate(*args, other_language)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        originals = [c["id"] for c in result["courses"]]
        if originals != [c["id"] for c in alternate["courses"]]:
            raise RuntimeError("Language versions disagree on itinerary order")
        created = now()
        run = secrets.token_urlsafe(18)
        inputs = {"trip": conditions, "artInterest":context["artInterest"], "preferences": context["preferences"],
                  "mood": context.get("currentMood"), "language": request.language,
                  "history": history}
        outcome = {k: result[k] for k in ("rulesVersion", "catalogVersion", "providers", "excluded", "notices")}
        conn.execute("INSERT INTO planner_runs VALUES(?,?,?,?,?)",
                     (run, user, json.dumps(inputs, ensure_ascii=False),
                      json.dumps(outcome, ensure_ascii=False), created))
        for course, translated in zip(result["courses"], alternate["courses"], strict=True):
            proposal = secrets.token_urlsafe(18)
            for variant in (course, translated):
                variant["courseId"] = variant["id"]
                variant["id"] = proposal
            saved = {**course, "alternateHandoff": planner.handoff(translated, other_language)}
            conn.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?)",
                         (proposal, user, run, json.dumps(saved, ensure_ascii=False),
                          request.language, created))
        result["activeMood"] = mood
        result["trip"] = conditions
        result["alternate"] = alternate
    return result


class Selection(BaseModel):
    reason: str | None = Field(default=None, max_length=180)
    detailMode: Literal["P","PnJ","J"] = "P"


@router.post("/plans/{proposal}/select")
def select(proposal: str, selection: Selection | None = None, language: Literal["en","ko"] | None = None, user: int = Depends(current_user)):
    with db() as conn:
        course, original_language = owned(conn, user, proposal)
        if language and language != original_language:
            document = course.get("alternateHandoff")
            if document is None:
                raise HTTPException(409, "TRANSLATION_UNAVAILABLE")
        else:
            document = planner.handoff(course, original_language)
        reason = selection.reason.strip() if selection and selection.reason else None
        conn.execute("""INSERT INTO decisions(proposal,kind,reason,recorded_at) VALUES(?,'selected',?,?)
                        ON CONFLICT(proposal,kind) DO UPDATE SET reason=COALESCE(excluded.reason, decisions.reason)""",
                     (proposal, reason, now()))
        document["selectionReason"] = conn.execute("SELECT reason FROM decisions WHERE proposal=? AND kind='selected'", (proposal,)).fetchone()[0]
        document.setdefault("personalitySummary", course.get("personalitySummary"))
        document["schemaVersion"] = "mia.itinerary/2"
        document["detailMode"] = selection.detailMode if selection else "P"
    return document


@router.post("/plans/{proposal}/feedback")
def feedback(proposal: str, event: Feedback, user: int = Depends(current_user)):
    if event.satisfaction is not None and event.kind != "visit":
        raise HTTPException(422, "RATE_AFTER_VISIT")
    with db() as conn:
        owned(conn, user, proposal)
        kind = "visited" if event.kind == "visit" else "rejected"
        conn.execute("""INSERT INTO decisions VALUES(?,?,?,?,?)
                        ON CONFLICT(proposal,kind) DO UPDATE SET
                          reason=excluded.reason,satisfaction=excluded.satisfaction,
                          recorded_at=excluded.recorded_at""",
                     (proposal, kind, event.reason, event.satisfaction, now()))
    return {"saved": True, "kind": kind}
