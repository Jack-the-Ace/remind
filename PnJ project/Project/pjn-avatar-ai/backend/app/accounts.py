import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from .travel_copy import present_history

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field, StringConstraints

from .survey import QUESTIONS, VERSION, Survey, score, strengths

router = APIRouter(prefix="/api")
DB = Path(__file__).resolve().parents[1] / "data" / "pnj.sqlite3"
TTL = 8 * 3600
AVATAR_COLUMN = "avatarId TEXT NOT NULL DEFAULT 'miho' CHECK (avatarId IN ('miho','min'))"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, nickname TEXT NOT NULL, mbti TEXT NOT NULL, avoid TEXT NOT NULL,
 salt BLOB NOT NULL, digest BLOB NOT NULL, survey TEXT NOT NULL, traits TEXT NOT NULL, {AVATAR_COLUMN});
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, owner TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS trips (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, result TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS trips_owner ON trips(owner,id);
"""

def connect():
    path = Path(os.getenv("PNJ_DB", str(DB)))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=8)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        if not has_avatar_column(db):
            with db:
                db.execute("BEGIN IMMEDIATE")
                # A concurrent first request may already have migrated the table.
                if not has_avatar_column(db):
                    db.execute(f"ALTER TABLE users ADD COLUMN {AVATAR_COLUMN}")
    except sqlite3.Error:
        db.close()
        raise
    return db

def has_avatar_column(db):
    return any(row["name"] == "avatarId" for row in db.execute("PRAGMA table_info(users)"))

Handle = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z0-9_-]{3,32}$")]
class Credentials(BaseModel):
    id: Handle
    password: str = Field(min_length=8,max_length=128,repr=False)

class Profile(BaseModel):
    nickname: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=40)]
    mbti: str = Field(default="", pattern=r"^(|[IE][NS][FT][JP])$")
    avoid: str = Field(default="",max_length=300)

class AvatarChoice(BaseModel):
    avatarId: Literal["miho","min"]

class Signup(Credentials,Profile):
    survey: Survey
    avatarId: Literal["miho","min"] = "miho"

def digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current(pnj_session: str = Cookie(default="")):
    with closing(connect()) as db:
        row = db.execute("""SELECT users.* FROM users JOIN sessions ON owner=users.id
            WHERE token=? AND expires>?""",(token_hash(pnj_session),time.time())).fetchone()
    if row is None:
        raise HTTPException(401,"LOGIN_REQUIRED")
    return dict(row)

def public(user):
    raw = json.loads(user['survey'] or 'null') or {}
    return {'strengths':strengths(raw), **{k:user[k] for k in ("id","nickname","mbti","avoid","avatarId")},
            "traits":json.loads(user["traits"]), "survey":raw}

@router.get("/survey")
def definition():
    return {"version":VERSION,"questions":QUESTIONS}

@router.post("/survey/score")
def preview(payload: Survey):
    return score(payload)

@router.post("/signup",status_code=201)
def signup(data: Signup):
    traits = score(data.survey)
    salt = secrets.token_bytes(16)
    try:
        with closing(connect()) as db, db:
            db.execute("INSERT INTO users(id,nickname,mbti,avoid,salt,digest,survey,traits,avatarId) VALUES(?,?,?,?,?,?,?,?,?)",
                       (data.id,data.nickname,data.mbti,data.avoid,salt,digest(data.password,salt),
                        data.survey.model_dump_json(),json.dumps(traits),data.avatarId))
    except sqlite3.IntegrityError:
        raise HTTPException(409,"ID_TAKEN") from None
    return {"id":data.id}

@router.post("/login")
def login(data: Credentials,response: Response):
    with closing(connect()) as db, db:
        user = db.execute("SELECT * FROM users WHERE id=?",(data.id,)).fetchone()
        candidate = digest(data.password, user["salt"] if user else bytes(16))
        if not user or not hmac.compare_digest(candidate,user["digest"]):
            raise HTTPException(401,"INVALID_LOGIN")
        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM sessions WHERE expires<=?",(time.time(),))
        db.execute("INSERT INTO sessions VALUES(?,?,?)",(token_hash(token),user["id"],int(time.time())+TTL))
    response.set_cookie("pnj_session",token,max_age=TTL,httponly=True,samesite="strict",path="/api",
                        secure=os.getenv("PNJ_SHARE_DEMO") == "1")
    return public(user)

@router.post("/logout")
def logout(response: Response,pnj_session: str = Cookie(default="")):
    with closing(connect()) as db, db:
        db.execute("DELETE FROM sessions WHERE token=?",(token_hash(pnj_session),))
    response.delete_cookie("pnj_session",path="/api",secure=os.getenv("PNJ_SHARE_DEMO") == "1",
                           httponly=True,samesite="strict")
    return {"ok":True}

@router.get("/me")
def me(user=Depends(current)):
    return public(user)

@router.put("/me")
def update(data: Profile,user=Depends(current)):
    with closing(connect()) as db, db:
        db.execute("UPDATE users SET nickname=?,mbti=?,avoid=? WHERE id=?",(data.nickname,data.mbti,data.avoid,user["id"]))
    return {**public(user),**data.model_dump()}

@router.put("/me/survey")
def retake(data: Survey,user=Depends(current)):
    traits = score(data)
    with closing(connect()) as db, db:
        db.execute("UPDATE users SET survey=?,traits=? WHERE id=?",(data.model_dump_json(),json.dumps(traits),user["id"]))
    return {**public(user),"survey":data.model_dump(),"traits":traits,"strengths":strengths(data.model_dump())}

@router.put("/me/avatar")
def select_avatar(data: AvatarChoice, user=Depends(current)):
    with closing(connect()) as db, db:
        db.execute("UPDATE users SET avatarId=? WHERE id=?", (data.avatarId, user["id"]))
    return data

class Feedback(BaseModel):
    action: Literal["like","reject","visit"]
    reason: Literal["crowds","walking","been","new","taste"] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


@router.put("/me/trips/{trip_id}/{course_id}/feedback")
def save_feedback(trip_id: str, course_id: str, data: Feedback, user=Depends(current)):
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id,result FROM trips WHERE owner=? AND json_extract(result,'$.id')=?",
                         (user["id"],trip_id)).fetchone()
        trip = json.loads(row["result"]) if row else {}
        if not any(c["id"] == course_id for c in trip.get("courses", [])):
            raise HTTPException(404, "TRIP_NOT_FOUND")
        feedback = trip.setdefault("feedback", {}).setdefault(course_id, {})
        feedback['updated'] = time.time_ns()
        if data.action == "visit":
            feedback.update(visited=True, rating=data.rating)
        else:
            feedback.update(decision=data.action, reason=data.reason if data.action=="reject" else None)
        db.execute("UPDATE trips SET result=? WHERE id=? AND owner=?",
                   (json.dumps(trip,ensure_ascii=False),row["id"],user["id"]))
    return feedback


@router.get("/me/history")
def history(user=Depends(current)):
    with closing(connect()) as db:
        rows = db.execute("SELECT result FROM trips WHERE owner=? ORDER BY id DESC LIMIT 20",(user["id"],)).fetchall()
    return [present_history(json.loads(row[0])) for row in rows]
