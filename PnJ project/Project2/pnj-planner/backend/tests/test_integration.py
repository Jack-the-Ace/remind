"""Check the public planner API with a disposable DB and disabled outbound sockets."""
import json
import socket



def test_explicit_clubbing_overrides_general_tour_on_the_same_account(app_client):
    client = app_client
    account(client, "nightlife-comparison")
    case = "Just wanna go to CLUB and dance with pretty KOrean girls... and wanna get drunken so much..."
    def ask(text, chip=None, trip=None):
        response = client.post("/api/plans", json={"checkIn":{"action":"new", "text":text,
                               "choices":{"mood":chip} if chip else {}}, "trip":trip or {}, "language":"en"})
        assert response.status_code == 200
        return response.json()

    for sentence, chip in ((case,"restless"), (case,None), ("I want to go clubbing and dance.",None),
                            ("오늘 클럽에서 춤추고 사람들과 어울리고 싶어.",None)):
        result = ask(sentence, chip)
        courses = result["courses"]
        assert {"club", "dance", "music", "nightlife"} <= set(result["activeMood"]["tags"])
        assert result["activeMood"]["choices"].get("mood") == chip and result["trip"]["avoid"] == []
        if sentence == case:
            assert "social" in result["activeMood"]["tags"]
        assert 0 < len(courses) < 3 and result["notices"]
        assert {c["activityMatch"]["level"] for c in courses} == {"direct","area"}
        assert len({c["reasons"][0] for c in courses}) == len(courses)
        for c in courses:
            assert c["conditionMatch"]["status"] == "needs_check"
            assert c["activityMatch"]["source"].startswith("https://")
            for day in c["days"]:
                for s in day["stops"]:
                    trace = c["scoreTrace"][s["id"]]
                    assert "club" in trace["placeEvidence"]["experienceTags"]
                    assert any("dance" in a.lower() for a in s["activities"])
                    assert any(h["match"] == "club" and h["points"] > 0 for h in trace["contributions"]["wish"])
                    assert s["timeRange"] == {"start":None,"end":None}
        for mode in ("P", "PnJ", "J"):
            handoff = client.post(f"/api/plans/{courses[0]['id']}/select",json={"detailMode": mode}).json()
            assert handoff["activityMatch"] == courses[0]["activityMatch"] and handoff["courseId"] == courses[0]["courseId"]
    sober = ask("I want to dance, but I don’t drink alcohol.")
    assert set(sober["trip"]["avoid"]) == {"alcohol"}
    assert sober["courses"] and all(c["activityMatch"]["offer"] == "dance_class" for c in sober["courses"])
    quiet = ask("I don’t want clubs. I want a quiet evening.")
    assert set(quiet["activeMood"]["tags"]) == {"quiet","evening"} and quiet["trip"]["avoid"] == ["club"]
    inside = ask("조용한 실내에서 쉬고 싶어")
    assert inside["trip"]["indoor"] == "prefer"
    for general in (quiet, inside):
        assert len(general["courses"]) == 3 and all("activityMatch" not in c for c in general["courses"])
        for c in general["courses"]:
            for day in c["days"]:
                for s in day["stops"]:
                    assert "quiet" in c["scoreTrace"][s["id"]]["placeEvidence"]["experienceTags"]
                    if general is inside:
                        assert s["setting"] == "indoor"
    for group in ("book club", "fan club"):
        r = ask("I’m looking for a "+group+".")
        assert r["activeMood"]["tags"] == [group.replace(" ","")] and not r["courses"]
        assert r["matchStatus"] == "no_activity_match"
    only = ask("Go to a club", trip={"indoor":"only","budgetKrw":500})
    assert only["courses"] and all(c["activityMatch"]["level"]=="direct" for c in only["courses"])
    assert only["courses"][0]["costs"]["total"] is None
    denied = ask("Go dancing", trip={"avoid":["dance"]})
    assert not denied["courses"] and denied["matchStatus"] == "no_activity_match"
    with db() as conn:
        assert not any(case in row for row in conn.iterdump())

import pytest
from fastapi.testclient import TestClient

from app.accounts import db
from app.main import app
from app.opening_calendar import opening_metadata, regular_closure


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PNJ_PLANNER_DB", str(tmp_path / "service.sqlite3"))
    monkeypatch.setenv("OPENAI_API_KEY", "unused-test-marker")
    connect = socket.socket.connect
    def local_connect(sock, address):
        # Windows asyncio creates its event-loop wakeup pair over loopback.
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
            pytest.fail("The offline planner attempted an external connection")
        return connect(sock, address)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    with TestClient(app) as client:
        yield client


def account(client, name):
    spec = client.get("/api/survey").json()
    credentials = {"username": name, "password": "local-test-pass"}
    payload = {**credentials, "version": spec["version"], "language": "en",
               "profile": {"hometown": "Private city", "mbti": "INTJ"},
               "answers": {item["id"]: 4 for item in spec["items"]}}
    assert client.post("/api/signup", json=payload).status_code == 201
    assert client.post("/api/login", json=credentials).status_code == 200
    return credentials


def test_selection_history_isolation_and_sanitised_export(app_client):
    c = app_client
    alice = account(c, "test-first")
    mood = c.post("/api/mood", json={"action": "new", "choices": {"mood":"restless", "goal":"learn"}}).json()
    trip = {"days":5, "lodging":"Seoul Station", "locked":[
        {"day":n, "label":"Booked appointment", "place":"Seoul Station"} for n in [1,2,3]]}
    results = c.post("/api/plans", json={"trip":trip, "language":"en","moodId":mood["id"]}).json()
    courses = results["courses"]
    assert [p["id"] for p in courses] == [p["id"] for p in results["alternate"]["courses"]]
    assert len(courses) == 3
    assert c.post("/api/plans",json={}).json()["activeMood"] is None
    selected = courses[0]
    uri = f"/api/plans/{selected['id']}"
    handoff = c.post(uri+"/select").json()
    assert handoff["planId"] == selected["id"]
    assert [d["stops"] for d in handoff["days"][:3]] == [[],[],[]]
    assert [d["locked"][0]["start"] for d in handoff["days"][:3]] == [None]*3
    assert handoff["days"][3]["transfers"] and handoff["days"][4]["transfers"]
    assert handoff["validation"]["status"] == "draft-demo"
    serialised = json.dumps(handoff)
    for private in ["test-first","Private city","INTJ","local-test-pass","extraversion","m01","pnj_planner_session"]:
        assert private not in serialised
    assert c.post(uri+"/select").json() == handoff
    translated = c.post(uri+"/select?language=ko").json()
    assert translated["language"] == "ko" and translated["planId"] == handoff["planId"]
    assert c.post(uri+"/feedback", json={"kind":"reject","satisfaction":3}).status_code == 422
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1
        audit = conn.execute("SELECT inputs FROM planner_runs").fetchone()[0]
        assert '"goal": "learn"' in audit and "Private city" not in audit
    c.post("/api/logout").raise_for_status()
    assert c.post(uri+"/select").status_code == 401
    account(c, "test-second")
    assert c.post(uri+"/select").status_code == 404
    assert c.post(uri+"/feedback", json={"kind":"visit","satisfaction":5}).status_code == 404
    c.post("/api/logout")
    c.post("/api/login", json=alice).raise_for_status()
    assert c.post(uri+"/feedback", json={"kind":"visit","satisfaction":4}).json()["kind"] == "visited"


def test_limits_closures_and_unavailable_feeds(app_client):
    c = app_client
    account(c, "check-conditions")
    assert c.get("/api/health").json()["providers"]["trends"]["status"] == "unconnected"
    assert c.get("/api/me").headers["cache-control"] == "no-store"
    for trip in [{"mustVisit":["seosomun"], "startDate":"2026-11-30"}]:
        result = c.post("/api/plans", json={"trip":trip}).json()
        assert result["courses"] == [] and result["notices"]
    assert c.post("/api/plans", json={"trip":{"indoor":"only","unexpected":1}}).status_code == 422
    assert c.post("/api/plans", json={"trip":{}, "mode":"openai"}).status_code == 422
    assert regular_closure("seosomun","2026-11-29",2) and not regular_closure("seosomun",None,1)
    assert opening_metadata("namsema")["source"].startswith("https://sema.seoul.go.kr/")


def test_quick_text_is_ephemeral_and_wishes_change_actual_rank(app_client):
    c=app_client
    account(c,"quick-member")
    texts=["오늘 너무 지쳤어. 그냥 편하게 쉬고 싶어.","기분 좋아서 서울에서 재밌는 걸 하고 싶어.","아직 모르겠어. 나한테 어울리는 곳 추천해줘."]
    results=[]
    for text in texts:
        out=c.post("/api/plans",json={"checkIn":{"action":"new","text":text},"language":"ko"}).json()
        assert len(out["courses"])==3
        cond=out["courses"][0]["conditions"]
        assert all(cond[k] is None for k in ("days","startDate","lodging","budgetKrw","transport"))
        results.append(out)
    assert results[0]["activeMood"]["tags"] == ["rest"] and "new" in results[1]["activeMood"]["tags"]
    assert [x["title"] for x in results[0]["courses"]] != [x["title"] for x in results[1]["courses"]]
    assert not results[2]["activeMood"]["choices"] and not results[2]["activeMood"]["tags"]
    with db() as conn:
        dump="".join(conn.iterdump())
        assert not any(t in dump for t in texts)
    a=c.post("/api/plans",json={"checkIn":{"action":"new","text":"실내만, 시장은 피하고 싶어"}}).json()
    assert a["trip"]["indoor"]=="only" and "market" in a["trip"]["avoid"]
    wishes=c.post("/api/plans",json={"wishText":"실내만, 서울숲은 피하고 싶어. 땅콩 알레르기가 있어."}).json()
    assert wishes["trip"]["indoor"]=="only" and "forest" in wishes["trip"]["avoid"]
    assert "nature" not in wishes["trip"]["avoid"]
    assert "peanut" in wishes["trip"]["diet"] and wishes["courses"]
    selected=c.post("/api/plans/"+wishes["courses"][0]["id"]+"/select",json={"reason":"I like this gallery"}).json()
    assert selected["selectionReason"]=="I like this gallery" and selected["durationDays"] is None
    assert "days" in selected["unconfirmedConditions"] and selected["days"][0]["day"] is None
    other=account(c,"other-quick")
    assert c.post("/api/plans",json={"moodId":results[0]["activeMood"]["id"]}).status_code == 404
    assert c.post("/api/plans",json={"checkIn":{"action":"new","tags":["art"],"editedFromId":results[0]["activeMood"]["id"]}}).status_code == 404


def test_cohort_field_and_immutable_survey_on_handoff(app_client):
    c = app_client
    account(c, "snapshot-test")
    with db() as conn:
        conn.execute("UPDATE users SET profile=?", (json.dumps({"nationality":"Japan","residenceCountry":"unmapped"}),))
    def plan():
        return c.post("/api/plans",json={"checkIn":{"action":"skip"}}).json()["courses"][0]
    assert plan()["providers"]["statistics"]["aggregate"]["scope"] == "all"
    with db() as conn:
        conn.execute("UPDATE users SET profile=?", (json.dumps({"nationality":"China","residenceCountry":"Japan"}),))
    course = plan()
    assert course["providers"]["statistics"]["aggregate"]["scope"] == "JP"
    with db() as conn:
        conn.execute("UPDATE personality_results SET version=?,scores=?", ("mini-ipip-en-ko-review-1", '{"extraversion":12}'))
    for lang in ["en","ko"]:
        doc = c.post("/api/plans/"+course["id"]+"/select?language="+lang,json={"detailMode":"PnJ"}).json()
        assert doc["personalitySummary"] == course["personalitySummary"] and len(doc["personalitySummary"]["scores"]) == 12
        assert doc["detailMode"] == "PnJ" and doc["moodSummary"]["confirmedAt"]
        assert "scope" not in doc["providers"]["statistics"]["aggregate"]
    old = plan()["personalitySummary"]
    assert old == {"version":"mini-ipip-en-ko-review-1","scores":{"extraversion":12}}

