"""Planner-owned accounts, questionnaire results, optional preferences and check-ins."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator

from . import personality
from .mood import EXPERIENCES, interpret

router = APIRouter(prefix="/api")
DEFAULT_DB = Path(__file__).resolve().parents[2] / ".runtime" / "planner.sqlite3"
COOKIE = "pnj_planner_session_v1"
SESSION_SECONDS = 8 * 3600
SEOUL = timezone(timedelta(hours=9))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
    salt BLOB NOT NULL, password_hash BLOB NOT NULL, profile TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS personality_results (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    version TEXT NOT NULL, language TEXT NOT NULL, answers TEXT NOT NULL,
    scores TEXT NOT NULL, answered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS survey_archive (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    version TEXT NOT NULL, language TEXT NOT NULL, answers TEXT NOT NULL,
    scores TEXT NOT NULL, answered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS travel_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id), rule_version TEXT NOT NULL,
    hypotheses TEXT NOT NULL, direct_values TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS mood_checks (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL CHECK(action IN ('new','skip','reuse')),
    choices TEXT NOT NULL, tags TEXT NOT NULL, confirmed_at TEXT NOT NULL, reused_from TEXT
);
CREATE TABLE IF NOT EXISTS mood_constraints (check_id INTEGER PRIMARY KEY REFERENCES mood_checks(id), conditions TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mood_by_user ON mood_checks(user_id, id DESC);
"""


@contextmanager
def db():
    path = Path(os.environ.get("PNJ_PLANNER_DB", DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Answer = Annotated[StrictInt, Field(ge=1, le=5)]


class Profile(Input):
    ageGroup: ShortText | None = None
    gender: ShortText | None = None
    nationality: ShortText | None = None
    residenceCountry: ShortText | None = None
    hometown: ShortText | None = None
    maritalStatus: ShortText | None = None
    language: ShortText | None = None
    countriesVisited: Annotated[StrictInt, Field(ge=0, le=300)] | None = None
    preferredCountry: ShortText | None = None
    seoulVisits: ShortText | None = None
    mbti: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^([EI][NS][FT][JP])?$")] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class Credentials(Input):
    username: Annotated[str, StringConstraints(min_length=3, max_length=32, pattern=r"^[\w-]+$")]
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("username", mode="before")
    @classmethod
    def canonical_username(cls, value):
        return unicodedata.normalize("NFKC", value).casefold().strip() if isinstance(value, str) else value


class SurveySubmission(Input):
    version: str
    language: Literal["en", "ko"]
    answers: dict[str, Answer]


class Registration(Credentials, SurveySubmission):
    profile: Profile = Field(default_factory=Profile)


class PreferenceUpdate(Input):
    values: dict[str, Answer | None]


class MoodChoices(Input):
    mood: Literal["tired", "restless", "happy", "curious", "calm", "low"] | None = None
    goal: Literal["rest", "discover", "connect", "learn"] | None = None
    atmosphere: Literal["quiet", "lively", "green", "indoor"] | None = None
    activity: Literal["low", "medium", "high"] | None = None


MOOD_TAGS = {
    "tired", "restless", "happy", "curious", "calm", "low", "rest", "discover", "connect",
    "learn", "quiet", "lively", "green", "indoor", "medium", "high", "outdoor", "nature",
    "culture", "shopping", "food", "history", "accessible", "walking", "night",
}


class CheckIn(Input):
    text: str = Field(default="", max_length=800, repr=False)
    editedFromId: int | None = Field(default=None, gt=0)
    action: Literal["new", "skip", "reuse"]
    choices: MoodChoices = Field(default_factory=MoodChoices)
    tags: list[str] = Field(default_factory=list, max_length=24)


def current_user(token: str | None = Cookie(default=None, alias=COOKIE)) -> int:
    if not token:
        raise HTTPException(401, "LOGIN_REQUIRED")
    with db() as conn:
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE token_hash=? AND expires_at>?",
            (token_digest(token), int(time.time())),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "LOGIN_REQUIRED")
    return row["user_id"]


Owner = Annotated[int, Depends(current_user)]


def pack_mood(row):
    if row is None:
        return None
    conditions = json.loads(row["conditions"] or "{}")
    edited_from = conditions.pop("_editedFrom", None)
    return {
        "id": row["id"], "action": row["action"], "choices": json.loads(row["choices"]),
        "tags": json.loads(row["tags"]), "confirmedAt": row["confirmed_at"],
        "reusedFrom": row["reused_from"], "editedFrom":edited_from, "suggestedConditions": conditions,
    }


def latest_mood(conn, owner, *, reusable=False):
    condition = " AND action != 'skip'" if reusable else ""
    return pack_mood(conn.execute(
        "SELECT m.*,c.conditions FROM mood_checks m LEFT JOIN mood_constraints c ON c.check_id=m.id WHERE m.user_id=?" + condition + " ORDER BY id DESC LIMIT 1",
        (owner,),
    ).fetchone())


def preferences(conn, owner):
    row = conn.execute("SELECT hypotheses,direct_values FROM travel_preferences WHERE user_id=?", (owner,)).fetchone()
    return personality.preference_view(json.loads(row["hypotheses"]), json.loads(row["direct_values"]))


def ranking_profile(conn, owner):
    row = conn.execute("""SELECT p.version, p.scores, u.profile FROM personality_results p
                          JOIN users u ON p.user_id=u.id WHERE u.id=?""", (owner,)).fetchone()
    survey = {"version":row["version"], "scores":json.loads(row["scores"])}
    prefs = preferences(conn, owner)
    current = survey["version"] == personality.SURVEY["version"]
    if current:
        for axis, pref in prefs.items():
            if pref["source"] == "personality":
                pref["facet"] = personality.PREFERENCE_RULES["hypotheses"].get(axis)
    return {"survey":survey, "preferences":prefs, "artInterest":survey["scores"].get("O2") if current else None,
            "residenceCountry":json.loads(row["profile"]).get("residenceCountry")}


def today_mood(conn, owner):
    mood = latest_mood(conn, owner)
    if mood and datetime.fromisoformat(mood["confirmedAt"]).astimezone(SEOUL).date() == datetime.now(SEOUL).date():
        return mood
    return None


def get_context(user_id):
    """Only recommendation inputs, never credentials or private questionnaire answers."""
    with db() as conn:
        return {"preferences": preferences(conn, user_id), "currentMood": today_mood(conn, user_id)}


@router.get("/survey")
def survey():
    return personality.definition()


@router.post("/signup", status_code=201)
def signup(data: Registration):
    try:
        scores = personality.score(data.version, data.answers)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    salt = secrets.token_bytes(16)
    digest = password_digest(data.password, salt)
    with db() as conn:
        try:
            user_id = conn.execute(
                "INSERT INTO users(username,salt,password_hash,profile) VALUES(?,?,?,?)",
                (data.username, salt, digest, data.profile.model_dump_json()),
            ).lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, "USERNAME_TAKEN") from None
        conn.execute("INSERT INTO personality_results VALUES(?,?,?,?,?,?)", (
            user_id, data.version, data.language, json.dumps(data.answers), json.dumps(scores), now(),
        ))
        conn.execute("INSERT INTO travel_preferences VALUES(?,?,?,?)", (
            user_id, personality.PREFERENCE_RULES["version"],
            json.dumps(personality.initial_preferences(scores)), "{}",
        ))
    return {"username": data.username}


@router.put("/survey")
def update_survey(data: SurveySubmission, owner: Owner):
    try:
        scores = personality.score(data.version, data.answers)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT * FROM personality_results WHERE user_id=?", (owner,)).fetchone()
        if previous["version"] == data.version and json.loads(previous["answers"]) == data.answers and previous["language"] == data.language:
            return me(owner)
        conn.execute("""INSERT INTO survey_archive(user_id,version,language,answers,scores,answered_at)
                        SELECT user_id,version,language,answers,scores,answered_at FROM personality_results WHERE user_id=?""", (owner,))
        conn.execute("""UPDATE personality_results SET version=?,language=?,answers=?,scores=?,answered_at=? WHERE user_id=?""",
                     (data.version, data.language, json.dumps(data.answers), json.dumps(scores), now(), owner))
        conn.execute("UPDATE travel_preferences SET rule_version=?,hypotheses=? WHERE user_id=?",
                     (personality.PREFERENCE_RULES["version"], json.dumps(personality.initial_preferences(scores)), owner))
    return me(owner)


@router.post("/login")
def login(data: Credentials, response: Response):
    with db() as conn:
        account = conn.execute("SELECT salt,password_hash,id FROM users WHERE username=?", (data.username,)).fetchone()
        digest = password_digest(data.password, account["salt"] if account else bytes(16))
        if account is None or not hmac.compare_digest(digest, account["password_hash"]):
            raise HTTPException(401, "INVALID_LOGIN")
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
        conn.execute("INSERT INTO sessions VALUES(?,?,?)", (
            token_digest(token), account["id"], int(time.time()) + SESSION_SECONDS,
        ))
    response.set_cookie(COOKIE, token, path="/api", httponly=True, samesite="strict", max_age=SESSION_SECONDS)
    return me(account["id"])


@router.post("/logout")
def logout(response: Response, token: str | None = Cookie(default=None, alias=COOKIE)):
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest(token),))
    response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/me")
def me(owner: Owner):
    with db() as conn:
        row = conn.execute(
            """SELECT u.username,u.profile,p.version,p.language,p.answered_at,p.scores
               FROM users u JOIN personality_results p ON u.id=p.user_id WHERE u.id=?""", (owner,),
        ).fetchone()
        return {
            "username": row["username"], "profile": json.loads(row["profile"]), "scores": json.loads(row["scores"]),
            "survey": {"current": row["version"] == personality.SURVEY["version"],
                       "facets": personality.SURVEY["facets"] if row["version"] == personality.SURVEY["version"] else {},
                       "version": row["version"], "language": row["language"], "answeredAt": row["answered_at"]},
            "preferences": preferences(conn, owner),
            "currentMood": today_mood(conn, owner), "lastMood": latest_mood(conn, owner, reusable=True),
        }


@router.put("/preferences")
def update_preferences(data: PreferenceUpdate, owner: Owner):
    if not set(data.values).issubset(personality.PREFERENCE_RULES["axes"]):
        raise HTTPException(422, "UNKNOWN_PREFERENCE")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT direct_values FROM travel_preferences WHERE user_id=?", (owner,)).fetchone()
        direct = json.loads(row["direct_values"])
        for axis, value in data.values.items():
            if value is None:
                direct.pop(axis, None)
            else:
                direct[axis] = value
        conn.execute("UPDATE travel_preferences SET direct_values=? WHERE user_id=?", (json.dumps(direct), owner))
    return me(owner)


@router.post("/mood")
def check_in(data: CheckIn, owner: Owner):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return record_checkin(conn, owner, data)


def record_checkin(conn, owner, data, places=None):
    choices = data.choices.model_dump(exclude_none=True)
    tags = list(dict.fromkeys(data.tags))
    if not set(tags).issubset(MOOD_TAGS | EXPERIENCES.keys()):
        raise HTTPException(422, "UNKNOWN_MOOD_TAG")
    previous_time, limits = None, {}
    edited = None
    if data.editedFromId is not None:
        if data.action != "new":
            raise HTTPException(422, "INVALID_MOOD_EDIT")
        previous = mood_for_plan(conn, owner, data.editedFromId)
        edited = previous["confirmedAt"]
        limits = previous["suggestedConditions"]
    if data.action == "reuse":
        previous = latest_mood(conn, owner, reusable=True)
        if previous is None:
            raise HTTPException(409, "NO_PREVIOUS_MOOD")
        choices, tags, limits = previous["choices"], previous["tags"], previous["suggestedConditions"]
        previous_time = previous["reusedFrom"] or previous["confirmedAt"]
        edited = previous.get("editedFrom")
    elif data.action == "skip":
        choices, tags = {}, []
    elif data.text.strip():
        inferred, matches, limits = interpret(data.text, places)
        choices = {**inferred, **choices}
        tags = [tag for tag in dict.fromkeys([*tags, *matches]) if tag not in limits.get("avoid", [])]
    elif not (choices or tags or edited):
        raise HTTPException(422, "EMPTY_MOOD")
    key = conn.execute("INSERT INTO mood_checks(user_id,action,choices,tags,confirmed_at,reused_from) VALUES(?,?,?,?,?,?)",
                       (owner, data.action, json.dumps(choices), json.dumps(tags), now(), previous_time)).lastrowid
    if edited:
        limits["_editedFrom"] = edited
    if limits:
        conn.execute("INSERT INTO mood_constraints VALUES(?,?)", (key, json.dumps(limits)))
    return latest_mood(conn, owner)


def mood_for_plan(conn, owner, mood_id):
    row = conn.execute("SELECT m.*,c.conditions FROM mood_checks m LEFT JOIN mood_constraints c ON c.check_id=m.id WHERE m.id=? AND m.user_id=?", (mood_id, owner)).fetchone()
    if row is None:
        raise HTTPException(404, "CHECKIN_NOT_FOUND")
    return pack_mood(row)
