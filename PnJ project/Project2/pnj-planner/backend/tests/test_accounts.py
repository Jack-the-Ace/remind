import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import accounts, personality


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv("PNJ_PLANNER_DB", str(tmp_path / "isolated.sqlite3"))
    accounts.init_db()
    app = FastAPI()
    app.include_router(accounts.router)
    with TestClient(app) as first, TestClient(app) as second:
        yield first, second


def registration(name):
    return {
        "username": name, "password": "example-passphrase",
        "profile": {"nationality": "France", "residenceCountry": "Japan", "mbti": ""},
        "language": "en", "version": personality.SURVEY["version"],
        "answers": {item["id"]: 3 for item in personality.definition()["items"]},
    }


def sign_in(client, name):
    payload = registration(name)
    assert client.post("/api/signup", json=payload).status_code == 201
    assert client.get("/api/me").status_code == 401
    response = client.post("/api/login", json={"username": name, "password": payload["password"]})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    return response.json()


def test_key_matches_reference_and_both_extremes():
    # Official Johnson facet key. O1 is +/+ and C6 is -/- in the selected pairs.
    facets = ("E3","E4","E2","E1","O4","O5","O2","O3","O1","C5","C6","A3")
    version = personality.definition()["version"]
    base = {row["id"]:3 for row in personality.definition()["items"]}
    assert len(base) == 24
    for facet in facets:
        for val, expected in [(5,100),(1,0),(4,75)]:
            values = {**base, facet.lower()+"-1":6-val if facet=="C6" else val,
                      facet.lower()+"-2":val if facet=="O1" else 6-val}
            assert personality.score(version,values) == {**dict.fromkeys(facets,50),facet:expected}
    with pytest.raises(ValueError,match="SURVEY_INCOMPLETE"):
        personality.score(version,dict(list(base.items())[:-1]))


def test_server_rechecks_survey_atomically(clients):
    client, _ = clients
    data = registration("atlas-a")
    for change in [
        {"version": "old-travel-test"}, {"answers": {"m01": 4}},
        {"answers": {**data["answers"], "other": 5}}, {"answers": {**data["answers"], "e2-1": True}},
        {"answers": {**data["answers"], "e2-1": 0}},
    ]:
        assert client.post("/api/signup", json={**data, **change}).status_code == 422
    assert client.post("/api/signup", json=data).status_code == 201
    assert client.post("/api/signup", json=data).status_code == 409
    with accounts.db() as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        row = conn.execute("SELECT * FROM personality_results").fetchone()
        assert json.loads(row["answers"]) == data["answers"] and row["language"] == "en" and row["answered_at"]
        assert len(conn.execute("SELECT password_hash FROM users").fetchone()[0]) == 32


def test_sessions_isolation_preferences_and_relogin(clients):
    first, second = clients
    start = sign_in(first, "atlas-one")
    sign_in(second, "atlas-two")
    assert start["profile"]["residenceCountry"] == "Japan" and start["profile"]["mbti"] is None
    assert start["preferences"]["social"] == {"value": 3.0, "source": "personality", "confirmed": False}
    assert start["preferences"]["crowds"]["value"] is None
    data = {"values": {"social": 1, "crowds": 4}}
    updated = first.put("/api/preferences", json=data).json()
    assert updated["preferences"]["social"] == {"value": 1, "source": "direct", "confirmed": True}
    assert second.get("/api/me").json()["preferences"]["crowds"]["value"] is None
    first.post("/api/logout")
    assert first.get("/api/me").status_code == 401
    assert second.get("/api/me").status_code == 200
    after = first.post("/api/login", json={"username": "atlas-one", "password": "example-passphrase"}).json()
    assert after["preferences"] == updated["preferences"] and after["survey"] == start["survey"]
    assert first.put("/api/preferences", json={"values": {"crowds": None}}).json()["preferences"]["crowds"]["value"] is None
    assert first.put("/api/preferences", json={"values": {"social": None}}).json()["preferences"]["social"]["source"] == "personality"


def test_mood_controlled_storage_skip_reuse_and_date(clients):
    first, second = clients
    sign_in(first, "sam-one")
    sign_in(second, "sam-two")
    assert first.post("/api/mood", json={"action": "reuse"}).status_code == 409
    assert first.post("/api/mood", json={"action": "new", "tags": ["raw private text"]}).status_code == 422
    assert first.post("/api/mood", json={"action": "new", "rawText": "raw private text"}).status_code == 422
    saved = first.post("/api/mood", json={"action": "new", "choices": {"goal": "learn"}, "tags": ["culture"]}).json()
    assert saved["choices"] == {"goal": "learn"}
    old = "2020-01-01T00:00:00.000000+00:00"
    with accounts.db() as conn:
        conn.execute("UPDATE mood_checks SET confirmed_at=?", (old,))
    assert first.get("/api/me").json()["currentMood"] is None
    skipped = first.post("/api/mood", json={"action": "skip", "choices": {"activity": "high"}}).json()
    assert skipped["choices"] == {} and skipped["tags"] == []
    assert first.get("/api/me").json()["lastMood"]["confirmedAt"] == old
    reused = first.post("/api/mood", json={"action": "reuse"}).json()
    assert reused["choices"] == saved["choices"] and reused["tags"] == saved["tags"] and reused["reusedFrom"] == old
    assert second.get("/api/me").json()["lastMood"] is None
    assert second.post("/api/mood", json={"action": "reuse"}).status_code == 409


def test_legacy_update_keeps_original_record_and_direct_preferences(clients):
    first, second = clients
    sign_in(first, "legacy-test")
    sign_in(second, "another-user")
    first.put("/api/preferences", json={"values":{"activity":1}})
    legacy_answers=json.dumps({f"m{i:02d}":3 for i in range(1,21)})
    legacy_version="mini-ipip-en-ko-review-1"
    with accounts.db() as conn:
        owner=conn.execute("SELECT id FROM users WHERE username=?",("legacy-test",)).fetchone()[0]
        conn.execute("UPDATE personality_results SET version=?,answers=?,scores=? WHERE user_id=?",
                     (legacy_version,legacy_answers,'{"extraversion":12}',owner))
    assert not first.get("/api/me").json()["survey"]["current"]
    data=registration("legacy-test")
    update={k:data[k] for k in ("version","answers","language")}
    assert first.put("/api/survey",json={**update,"answers":{}}).status_code==422
    assert first.put("/api/survey",json=update).json()["preferences"]["activity"]["value"]==1
    assert first.put("/api/survey",json=update).status_code==200
    with accounts.db() as conn:
        old=conn.execute("SELECT user_id,version,answers FROM survey_archive").fetchall()
        assert [tuple(row) for row in old] == [(owner,legacy_version,legacy_answers)]
    assert second.get("/api/me").json()["preferences"]["activity"]["source"]=="personality"
