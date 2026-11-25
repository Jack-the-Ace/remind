"""Exercise the account and travel lifecycle using an isolated local database."""
import json
import secrets
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.accounts import connect
from app.main import app
from app.survey import VERSION, QUESTIONS
from app.catalog import candidates

@pytest.fixture
def account(monkeypatch):
    runtime=Path(__file__).resolve().parents[2]/".runtime"
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime) as folder:
        monkeypatch.setenv("PNJ_DB",str(Path(folder)/"qa.sqlite3"))
        monkeypatch.delenv("OPENAI_API_KEY",raising=False)
        yield dict(id="traveler",nickname="여행자",mbti="",avoid="",password=secrets.token_urlsafe(18),
                   survey=dict(version=VERSION,answers={q["id"]:0 for q in QUESTIONS}))

@pytest.fixture
def client():
    return TestClient(app)

def signed_in(c,account):
    assert c.post("/api/signup",json=account).status_code==201
    assert c.get("/api/me").status_code==401
    r=c.post("/api/login",json=account)
    assert r.is_success and "HttpOnly" in r.headers["set-cookie"]
    return r.json()

def test_survey_validation_and_retry(client,account):
    answers=account["survey"]["answers"]
    for survey in [dict(version="old",answers=answers),dict(version=VERSION,answers={}),
                   dict(version=VERSION,answers={**answers,"s1":2}),
                   dict(version=VERSION,answers={**answers,"s1":True})]:
        r=client.post("/api/signup",json={**account,"survey":survey,"completed":True})
        assert r.status_code==422 and account["password"] not in r.text
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(lambda _: TestClient(app).post("/api/signup",json=account).status_code,range(2)))
    assert sorted(statuses)==[201,409]
    assert client.post("/api/signup",json={**account,"id":"retry"}).status_code==201
    assert client.get("/api/me").status_code==401

def test_personalization_scope_and_expiry(client,account):
    a=client
    assert signed_in(a,account)["mbti"]==""
    b=TestClient(app)
    signed_in(b,{**account,"id":"second","mbti":"INFP"})
    assert a.put("/api/me",json={"id":"second","nickname":"updated","avoid":"혼잡한 곳"}).is_success
    assert b.get("/api/me").json()["nickname"]==account["nickname"]
    first=a.post("/api/travel/mood",json={"mood":"오늘은 피곤해"}).json()
    assert "courses" not in first and first["mode"]=="demo"
    data={"turn":first["turn"],"wish":"조용히 혼자 걷고 싶어"}
    assert b.post("/api/travel/courses",json=data).status_code==409
    trip=a.post("/api/travel/courses",json=data).json()
    assert len({c["id"] for c in trip["courses"]})==3
    assert not {"gwangjang","namdaemun"} & {p["id"] for c in trip["courses"] for p in c["places"]}
    assert a.post("/api/travel/courses",json={**data,"mode":"ai"}).status_code==503
    assert b.get("/api/me/history").json()==[]
    assert a.get("/api/me/history").json()==[trip]
    newer={**account["survey"],"answers":{q["id"]:len(q["choices"])-1 for q in QUESTIONS}}
    assert a.put("/api/me/survey",json=newer).json()["traits"]["pace"]==["active"]
    assert b.get("/api/me").json()["traits"]["pace"]==["rest"]
    wish={"turn":first["turn"],"wish":"자동차로 가고 싶고 주차가 편했으면 좋겠어"}
    drive = a.post("/api/travel/courses", json=wish).json()
    assert len({c["id"] for c in drive["courses"]}) == 3
    assert {p["id"] for c in drive["courses"] for p in c["places"]} <= {"pureun","boramae","seonyudo","forest","botanic"}
    assert any("주차" in check for check in drive["checks"])
    with closing(connect()) as db,db:
        db.execute("UPDATE turns SET day='2000-01-01'")
    assert a.post("/api/travel/courses",json=data).status_code==409
    with closing(connect()) as db,db:
        db.execute("UPDATE sessions SET expires=0 WHERE owner='traveler'")
    assert a.get("/api/me/history").status_code==401
    assert b.post("/api/logout").is_success and b.get("/api/me").status_code==401

def test_explicit_restrictions():
    profile={"traits":{},"avoid":"사람 많은 곳"}
    assert candidates("피곤해","유명하고 북적이는 곳",profile,"ko")==[]
    routes=candidates("무릎이 아파 오래 걷기 어려워","아직 모르겠어",profile,"ko")
    assert len(routes)>=3
    assert all(not {"walk","busy","active"}.intersection(c["tags"]) for c in routes)

def test_avatar_migration_and_account_scope(client, account):
    before = signed_in(client, {**account, "mbti":"ISFP"})
    mood = client.post("/api/travel/mood", json={"mood":"편안해"}).json()
    request = {"turn":mood["turn"], "wish":"산책하고 싶어"}
    trip = client.post("/api/travel/courses", json=request).json()
    # Recreate the previous release's missing column in this disposable fixture.
    with closing(connect()) as db, db:
        db.execute("ALTER TABLE users DROP COLUMN avatarId")
    with ThreadPoolExecutor(max_workers=2) as pool:
        migrated = list(pool.map(lambda _: client.get("/api/me").json(), range(2)))
    assert migrated == [before, before] and before["avatarId"] == "miho"
    second = TestClient(app)
    assert signed_in(second, {**account, "id":"min_member","avatarId":"min"})["avatarId"] == "min"
    assert TestClient(app).put("/api/me/avatar", json={"avatarId":"min"}).status_code == 401
    assert client.put("/api/me/avatar", json={"avatarId":"other"}).status_code == 422
    assert second.put("/api/me/avatar", json={"id":account["id"],"avatarId":"miho"}).is_success
    assert client.put("/api/me/avatar", json={"avatarId":"min"}).is_success
    assert second.get("/api/me").json()["avatarId"] == "miho"
    assert client.get("/api/me").json() == {**before,"avatarId":"min"}
    assert client.get("/api/me/history").json() == [trip]
    changed = client.post("/api/travel/courses", json=request).json()["courses"]
    assert [c["reason"] for c in changed] != [c["reason"] for c in trip["courses"]]
    assert [{k:v for k,v in c.items() if k!="reason"} for c in changed] == [
        {k:v for k,v in c.items() if k!="reason"} for c in trip["courses"]]
    url = f"/api/me/trips/{trip['id']}/{changed[0]['id']}/feedback"
    assert second.put(url,json={"action":"like"}).status_code == 404
    assert client.put(url,json={"action":"like"}).json()["decision"]=="like"
    assert "visited" not in client.get("/api/me/history").json()[-1]["feedback"][changed[0]["id"]]
    assert "history" in client.post("/api/travel/courses",json=request).json()["courses"][0]["basis"]
    assert client.post("/api/logout").is_success
    assert client.post("/api/login", json=account).json()["avatarId"] == "min"

def test_ai_speaker_uses_saved_avatar_for_both_stages(client, account, monkeypatch):
    """Inspect messages at the SDK boundary, independently of provider quota."""
    from app import travel

    signed_in(client, account)
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-placeholder")
    sdk = MagicMock()
    prompts = []

    def reply(*, messages, response_format, **kwargs):
        prompts.append(messages[0]["content"])
        if response_format is travel.Empathy:
            parsed = travel.Empathy(message="That sounds tiring.")
        else:
            catalog = json.loads(messages[1]["content"])["catalog"]
            parsed = travel.Picks(clarification="", courses=[
                travel.Pick(id=c["id"], reason="A quiet break.", profileReason="Matches your pace.") for c in catalog
            ])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])

    sdk.beta.chat.completions.parse = AsyncMock(side_effect=reply)
    monkeypatch.setattr(travel, "get_client", lambda: sdk)
    for avatar, name in [("miho","Miho (미호)"), ("min","Min (민)")]:
        client.put("/api/me/avatar", json={"avatarId":avatar}).raise_for_status()
        payload = {"language":"en", "mode":"ai"}
        turn = client.post("/api/travel/mood", json={**payload,"mood":"Tired"}).raise_for_status().json()
        trip = client.post("/api/travel/courses", json={**payload,"turn":turn["turn"],"wish":"A quiet break"}).raise_for_status().json()
        assert trip["mode"] == "ai" and len(trip["courses"]) == 3
        assert len(prompts) == 2 and all(name in p for p in prompts)
        prompts.clear()
