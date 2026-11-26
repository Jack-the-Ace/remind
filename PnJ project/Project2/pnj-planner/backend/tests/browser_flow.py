"""Manual end-to-end regression against a start.bat instance using a new planner QA database."""

import argparse
import json
import re
import secrets
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:5186"
RUNTIME = ROOT / ".runtime"


def verify_target(path):
    target = path.resolve(strict=True)
    record = json.loads((RUNTIME / "server.json").read_text(encoding="utf-8-sig"))
    if target.parent != RUNTIME or not re.fullmatch(r"qa-[\w-]+\.sqlite3", target.name):
        raise SystemExit("Use a dedicated .runtime/qa-*.sqlite3 test database.")
    if target != Path(record["database"]).resolve(strict=True):
        raise SystemExit("start.bat is serving another database. No browser writes were attempted.")
    with build_opener(ProxyHandler({})).open(BASE + "/api/health", timeout=5) as response:
        health = json.load(response)
    if health.get("service") != "pnj-planner" or health.get("providers", {}).get("planning") != "offline_rules":
        raise SystemExit("Unexpected service or provider. No browser writes were attempted.")
    return target


def button(page, name):
    return page.get_by_role("button", name=name)


def fill_passwords(page, password):
    page.locator("input[type=password]").nth(0).fill(password)
    page.locator("input[type=password]").nth(1).fill(password)


def signup(page, name, password):
    button(page, re.compile("create.*account|sign up|register", re.I)).first.click()
    page.get_by_label(re.compile("^Username", re.I)).fill(name)
    fill_passwords(page, password)
    button(page, re.compile("Start questionnaire")).click()
    items=page.request.get(BASE+"/api/survey").json()["items"]
    assert len(items)==24
    def position(i, answered, lang="en"):
        q=items[i]
        expect(page.locator(".quiz")).to_have_attribute("data-question-id",q["id"])
        expect(page.locator(".question")).to_have_text(q["text"][lang])
        expect(page.locator(".quiz .eyebrow")).to_contain_text(f"{i+1} / {len(items)}")
        assert page.locator("progress").evaluate("e=>[e.value,e.max]")==[answered,len(items)]
    for i, item in enumerate(items):
        position(i,i)
        if i==4:
            button(page,"한국어").click();position(i,i,"ko")
            page.reload();position(i,i,"ko")
            button(page,"이전").click();position(i-1,i,"ko")
            button(page,re.compile("^다음")).click();position(i,i,"ko")
            button(page,"EN").click();position(i,i)
            # Simulate a translator detaching the live text node.
            page.locator(".quiz .eyebrow").evaluate("e=>{const f=document.createElement('font');f.textContent=e.textContent;e.replaceChildren(f)}")
        if i==23:
            expect(button(page,re.compile("Finish questionnaire"))).to_be_disabled()
        value=5 if item["id"].endswith("-1") else 1
        page.locator(".answers button").filter(has_text=re.compile("^"+str(value))).click()
        button(page, re.compile("Finish questionnaire|^Next")).click()
    expect(page.get_by_text("Questionnaire complete", exact=True)).to_be_visible()
    expect(page.get_by_label(re.compile("^Username", re.I))).to_have_value(name)
    expect(page.locator("input[type=password]").first).to_have_value("")
    assert password not in page.evaluate("JSON.stringify(sessionStorage) + JSON.stringify(localStorage)")
    fill_passwords(page, password)
    # A real browser fetch failure must leave the completed questionnaire and form in place.
    page.route("**/api/signup", lambda route: route.abort("connectionfailed"), times=1)
    button(page, re.compile("Complete registration")).click()
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page.get_by_text("Questionnaire complete", exact=True)).to_be_visible()
    expect(page.locator("input[type=password]").first).to_have_value(password)
    with page.expect_response(lambda r: r.url.endswith("/api/signup") and r.status == 201):
        button(page, re.compile("Complete registration")).click()
    expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
    assert page.evaluate("sessionStorage.getItem('pnj-planner.v1.signup')") is None
    page.get_by_label("Username", exact=True).fill(name)
    page.get_by_label("Password", exact=True).fill(password)
    button(page, re.compile("^Sign in$", re.I)).click()


def submit_plan(page, name):
    with page.expect_response(lambda r:r.url.endswith("/api/plans") and r.status==200) as response:
        button(page,re.compile(name)).click()
    result=response.value.json()
    expect(page.locator(".cards > article")).to_have_count(len(result["courses"]))
    return result


def quick_paths(page):
    def raw(text):
        page.locator("textarea").fill(text)
        expect(button(page,"Find experiences for me")).to_be_enabled()
        return submit_plan(page,"^Find experiences for me")
    def home():
        button(page,"PnJ planner home").click()
    first=raw("오늘 너무 지쳤어. 그냥 편하게 쉬고 싶어.")
    assert len(first["courses"])==3 and "rest" in first["activeMood"]["tags"]
    expect(page.get_by_text(re.compile("Sounds like a tiring day"))).to_be_visible()
    assert all(first["trip"][field] is None for field in ("days","startDate","lodging","startPoint","returnPoint","transport","budgetKrw","availableMinutes"))
    assert all(c["format"]=="experience" for c in first["courses"])
    page.screenshot(path=str(RUNTIME/"qa-mood-first-desktop.png"))
    home()
    lively=raw("기분 좋아서 서울에서 재밌는 걸 하고 싶어.")
    assert "new" in lively["activeMood"]["tags"] and first["courses"][0]["reasons"]!=lively["courses"][0]["reasons"]
    assert [c["title"] for c in first["courses"]] != [c["title"] for c in lively["courses"]]
    print("Rest vs fun:",[c["title"] for c in first["courses"]], [c["title"] for c in lively["courses"]])
    home()
    unknown=raw("아직 모르겠어. 나한테 어울리는 곳 추천해줘.")
    assert len(unknown["courses"])==3 and not unknown["activeMood"]["choices"]
    assert any(t["contributions"]["hypothesis"] for c in unknown["courses"] for t in c["scoreTrace"].values())
    home()
    skipped=submit_plan(page,"^Skip mood and explore")
    assert len(skipped["courses"])==3 and skipped["activeMood"]["action"]=="skip" and not skipped["activeMood"]["tags"]
    home()
    reused=submit_plan(page,"^Use my previous answers")
    assert reused["activeMood"]["action"]=="reuse" and reused["activeMood"]["reusedFrom"]
    button(page,"Refine trip conditions").click()
    page.get_by_text("Travel conditions and must-visits",exact=True).click()
    budget=page.get_by_label(re.compile("^Whole-trip spending cap"))
    budget.fill("100000")
    capped=submit_plan(page,"^Find itineraries")
    assert len(capped["courses"])==3 and all(c["conditionMatch"]["pending"] for c in capped["courses"])
    expect(page.get_by_text(re.compile("full trip cost still needs checking")).first).to_be_visible()
    button(page,"Refine trip conditions").click()
    page.get_by_text("Travel conditions and must-visits",exact=True).click()
    expect(budget).to_have_value("100000")
    budget.fill("")
    page.get_by_role("combobox",name=re.compile("^Indoor activities")).select_option("only")
    page.get_by_role("combobox",name=re.compile("^Places to avoid")).select_option("seosomun")
    limited=submit_plan(page,"^Find itineraries")
    assert len(limited["courses"])==3
    assert all(p["id"]!="seosomun" and p["setting"]=="indoor" for c in limited["courses"] for d in c["days"] for p in d["stops"])
    home()
    for sentence, feeling, interests, exclusions in [
        ("피곤하지 않아. 오늘은 많이 걷고 싶어.",None,{"active","walk"},set()),
        ("지쳤지만 혼자 있고 싶지는 않아. 활기찬 시장에 가고 싶어.","tired",{"busy","market"},{"solo"}),
        ("I’m not sad. I just want somewhere quiet.",None,{"quiet"},set()),
        ("I’m excited, but I don’t want crowded places.","happy",set(),{"busy"}),
    ]:
        checked = raw(sentence)
        assert checked["activeMood"]["choices"].get("mood") == feeling
        assert set(checked["activeMood"]["tags"]) == interests and set(checked["trip"]["avoid"]) == exclusions
        expect(page.locator(".cards > article")).to_have_count(3)
        home()
    raw("I feel tired. I want to relax.")
    button(page,"Adjust mood interpretation").click()
    page.get_by_role("button",name="Rest",exact=True).click()
    page.get_by_role("button",name="Art",exact=True).click()
    edited=submit_plan(page,"^Find experiences for me")
    assert "art" in edited["activeMood"]["tags"] and "rest" not in edited["activeMood"]["tags"]
    return first


def trip(page):
    button(page,"Refine trip conditions").click()
    page.locator("textarea").fill("history, culture")
    page.get_by_label("Lodging or neighbourhood").fill("Example Seoul hotel")
    page.get_by_text("Locked days and appointments", exact=True).click()
    page.get_by_label("Days in Seoul").fill("5")
    button(page, re.compile("Add a locked segment")).click()
    page.locator(".lock").get_by_label("Day", exact=True).fill("2")
    page.locator(".lock").get_by_label("Appointment", exact=True).fill("Pre-booked meeting")
    page.locator(".lock").get_by_label("Location", exact=True).fill("Seoul meeting point")
    button(page, "Use 5-day example").click()
    button(page, "Use 5-day example").click()
    expect(page.locator(".lock")).to_have_count(3)
    with page.expect_response(lambda r: r.url.endswith("/api/plans") and r.status == 200) as response:
        button(page, re.compile("Find itineraries")).click()
    courses = response.value.json()["courses"]
    assert len(courses) == 3
    for course in courses:
        assert set(course["conditions"]["interests"]) >= {"history","culture"}
        assert len(course["days"]) == 5
        assert all(d["locked"] and not d["stops"] for d in course["days"][:3])
        assert all(d["stops"] for d in course["days"][3:])
        assert course["days"][1]["locked"][0]["label"] == "Pre-booked meeting"
        assert course["days"][1]["locked"][0]["start"] is None
        assert course["conditions"]["lodging"] == "Example Seoul hotel"
    return courses


def verify_photos(page, selector, expected_count):
    photos = page.locator(selector)
    expect(photos).to_have_count(expected_count)
    assert expected_count > 0
    for photo in photos.all():
        photo.scroll_into_view_if_needed()
        expect(photo).to_be_visible()
        assert photo.evaluate("async el => {await el.decode(); return el.naturalWidth > 0 && el.naturalHeight > 0;}")


def same_page_width(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"


def inspect_results(page, courses):
    expect(page.get_by_role("heading", name="Your Seoul itineraries")).to_be_visible()
    cards = page.locator(".cards > article")
    expect(cards).to_have_count(3)
    photo_count = sum(bool(c["photo"]) for c in courses)
    verify_photos(page, ".cards img", photo_count)
    desktop = [card.bounding_box() for card in cards.all()]
    assert max(b["y"] for b in desktop) - min(b["y"] for b in desktop) < 2
    same_page_width(page)
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(RUNTIME / "qa-desktop-results.png"))

    page.set_viewport_size({"width": 390, "height": 844})
    same_page_width(page)
    assert all(card.bounding_box()["width"] <= 390 for card in cards.all())
    page.screenshot(path=str(RUNTIME / "qa-mobile-results.png"))
    button(page, re.compile("^View itinerary")).first.click()
    course = courses[0]
    detail = page.locator(".detail")
    stops = [p for d in course["days"] for p in d["stops"]]
    for mode in ("P · Overview", "PnJ · Guided", "J · Detailed"):
        detail.get_by_role("button", name=mode, exact=True).click()
        expect(detail).to_have_attribute("data-course-id", course["courseId"])
        expect(detail.locator(".day")).to_have_count(5)
        expect(detail.locator(".stops h4")).to_have_text([s["name"] for s in stops])
        expect(detail.locator(".locked-list")).to_have_count(3)
        same_page_width(page)
    detail_photo_count = sum(bool(s["photo"]) for s in stops)
    verify_photos(page, ".detail .stops img", detail_photo_count)
    page.get_by_text("Add a reason for choosing this course (optional)").click()
    page.get_by_label("My reason for Mia").fill("I want to explore art")
    with page.expect_response(lambda r: urlsplit(r.url).path.endswith("/select") and r.status == 200) as incoming:
        button(page, re.compile("Select plan for Mia")).click()
    document = incoming.value.json()
    page.get_by_text("View structured JSON").click()
    assert json.loads(page.locator(".handoff pre").inner_text()) == document
    same_page_width(page)
    with page.expect_download() as downloaded:
        page.get_by_role("link", name=re.compile("Download JSON")).click()
    assert json.loads(downloaded.value.path().read_text(encoding="utf-8")) == document
    assert document["selectionReason"]=="I want to explore art" and document["moodSummary"]["tags"]==["art"]
    assert document["detailMode"] == "J" and document["moodSummary"]["editedFrom"]
    assert len(document["personalitySummary"]["scores"]) == 12
    detail.get_by_role("button", name="PnJ · Guided", exact=True).click()
    assert json.loads(page.locator(".handoff pre").inner_text())["detailMode"] == "PnJ"
    assert document["planId"] == course["id"] and document["validation"]["status"] == "draft-demo"
    assert [s["id"] for day in document["days"] for s in day["stops"]] == [s["id"] for s in stops]
    assert all(d["locked"] == v["locked"] for d, v in zip(document["days"], course["days"]))
    assert not ({"profile", "password", "username", "preferences", "answers", "session"} & document.keys())
    print(f"Photos decoded: {photo_count} cards and {detail_photo_count} detail stops; "
          f"modes retained {len(stops)} ordered stops and 3 locked days.")
    # Only deliberate actions become feedback. Record them on separate synthetic courses.
    button(page, re.compile("^View itinerary")).nth(1).click()
    button(page, "Reject this itinerary").click()
    page.get_by_label("Reason for rejecting (optional)").fill("Prefer a quieter course")
    button(page, "Save feedback").click()
    expect(page.get_by_text("Your rejection was recorded.")).to_be_visible()
    button(page, re.compile("^View itinerary")).nth(2).click()
    button(page, "Record an actual visit").click()
    page.get_by_label(re.compile("^I visited this course")).select_option("4")
    button(page, "Save feedback").click()
    expect(page.get_by_text("Your actual visit was recorded.")).to_be_visible()


def finish_checkins(page, name, password, courses):
    button(page, "한국어").click()
    expect(page.locator("html")).to_have_attribute("lang", "ko")
    expect(page.get_by_role("heading", name="나를 위한 서울 코스")).to_be_visible()
    expect(page.locator(".cards > article")).to_have_count(3)
    catalog = json.loads((ROOT / "backend/app/data/places.json").read_text(encoding="utf-8"))
    for index, original in enumerate(courses):
        button(page, re.compile("^코스 자세히 보기")).nth(index).click()
        detail = page.locator(".detail")
        expect(detail).to_have_attribute("data-course-id", original["courseId"])
        ids = [s["id"] for d in original["days"] for s in d["stops"]]
        expect(detail.locator(".stops h4")).to_have_text([catalog[i]["name"]["ko"] for i in ids])
        if index == 0:
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith("/select") and r.status == 200) as handoff:
                button(page, re.compile("이 계획을 미아 인계용으로 선택")).click()
            localized = handoff.value.json()
            assert localized["language"] == "ko" and localized["planId"] == original["id"]
    same_page_width(page)
    button(page, "PnJ 플래너 홈").click()
    expect(button(page, "지난 답과 같아요")).to_be_visible()
    skipped=submit_plan(page,"^기분 없이 추천받기")
    assert len(skipped["courses"])==3 and skipped["activeMood"]["action"]=="skip"
    button(page, "PnJ 플래너 홈").click()
    page.locator("textarea").fill("아직 모르겠어. 알아서 추천해줘")
    three=submit_plan(page,"^지금 마음으로 추천받기")
    assert len(three["courses"])==3
    same_page_width(page)
    page.screenshot(path=str(RUNTIME/"qa-mood-first-mobile.png"))
    button(page, "마이페이지").click()
    expect(page.get_by_role("heading", name="성격검사 결과")).to_be_visible()
    expect(page.locator("meter")).to_have_count(12)
    expect(page.locator(".axis-grid select")).to_have_count(10)
    page.locator(".axis-grid select").first.select_option("5")
    button(page, "선호 저장").click()
    expect(page.get_by_text("선호를 저장했어요.")).to_be_visible()
    button(page, "로그아웃").click()
    page.get_by_role("navigation").get_by_role("button", name="로그인").click()
    page.get_by_label("아이디", exact=True).fill(name)
    page.get_by_label("비밀번호", exact=True).fill(password)
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_text("지난 답변", exact=True)).to_be_visible()
    button(page, "마이페이지").click()
    expect(page.locator(".axis-grid select").first).to_have_value("5")


def check_legacy_upgrade(browser, target):
    """A fresh synthetic legacy row in the guarded QA DB, using its original survey version."""
    import hashlib
    from datetime import datetime, timezone
    who="qa-legacy-"+secrets.token_hex(4)
    pw=secrets.token_urlsafe(16)
    salt=secrets.token_bytes(16)
    old=json.loads((ROOT/"backend/app/data/mini_ipip.json").read_text(encoding="utf8"))
    original=json.dumps({item[0]:3 for item in old["items"]})
    direct=json.dumps({"learning":5})
    axes=json.loads((ROOT/"backend/app/data/preference_rules.json").read_text(encoding="utf8"))["axes"]
    hypotheses={k:{"source":"unknown","value":None,"confirmed":False} for k in axes}
    with sqlite3.connect(target) as conn:
        uid=conn.execute("INSERT INTO users(username,salt,password_hash,profile) VALUES(?,?,?,?)",
                         (who,salt,hashlib.pbkdf2_hmac("sha256",pw.encode(),salt,600000),'{"mbti":"INFP"}')).lastrowid
        scores={item[1]:12 for item in old["items"]}
        conn.execute("INSERT INTO personality_results VALUES(?,?,?,?,?,?)",(uid,old["version"],"en",original,json.dumps(scores),datetime.now(timezone.utc).isoformat()))
        conn.execute("INSERT INTO travel_preferences VALUES(?,?,?,?)",(uid,"preference-hypotheses-1",json.dumps(hypotheses),direct))
    page=browser.new_page(viewport={"width":390,"height":844})
    page.goto(BASE)
    page.get_by_role("navigation").get_by_role("button",name="Sign in").click()
    page.get_by_label("Username",exact=True).fill(who)
    page.get_by_label("Password",exact=True).fill(pw)
    page.get_by_role("button",name="Sign in",exact=True).click()
    # Older users can request experiences without retesting.
    old_courses = submit_plan(page,"^Skip mood and explore")["courses"]
    assert len(old_courses) == 3
    snapshot = page.request.post(BASE+"/api/plans/"+old_courses[0]["id"]+"/select").json()["personalitySummary"]
    assert snapshot == {"version":old["version"], "scores":scores}
    button(page,"My profile").click()
    expect(page.locator("meter")).to_have_count(5)
    button(page,"Take the PnJ questionnaire").click()
    for i in range(24):
        expect(page.locator(".quiz .eyebrow")).to_contain_text(f"{i+1} / 24")
        page.locator(".answers button").nth(1).click()
        button(page,re.compile("Finish questionnaire|^Next")).click()
    expect(page.locator("meter")).to_have_count(12)
    expect(page.locator(".axis-grid select").nth(5)).to_have_value("5")
    with sqlite3.connect(target.as_uri()+"?mode=ro",uri=True) as conn:
        assert conn.execute("SELECT version,answers FROM survey_archive WHERE user_id=?",(uid,)).fetchall()==[(old["version"],original)]
        assert conn.execute("SELECT count(*) FROM proposals WHERE owner=?",(uid,)).fetchone()[0]==3
    page.close()
    print("Legacy login, direct recommendation, optional 20-to-24 retest, archived original and direct preferences passed.")


def run(qa_db):
    target = verify_target(qa_db)
    name = "qa-browser-" + secrets.token_hex(5)
    password = secrets.token_urlsafe(18)
    external, page_errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1360, "height": 900}, locale="en-GB",
                                      service_workers="block", accept_downloads=True)
        def local_only(route):
            parsed = urlsplit(route.request.url)
            if parsed.scheme in {"http", "https"} and (parsed.scheme != "http" or parsed.netloc != "127.0.0.1:5186"):
                external.append(parsed.netloc)
                route.abort()
            else:
                route.continue_()
        context.route("**/*", local_only)
        page = context.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.set_default_timeout(8_000)
        try:
            page.goto(BASE, wait_until="networkidle")
            signup(page, name, password)
            quick_paths(page)
            courses = trip(page)
            inspect_results(page, courses)
            finish_checkins(page, name, password, courses)
            check_legacy_upgrade(browser,target)
            assert not external and not page_errors, (external, page_errors)
        except Exception:
            page.screenshot(path=str(RUNTIME / "browser-failure.png"))
            print("Failed page:", page.title(), page.locator("h1").all_text_contents(), file=sys.stderr)
            raise
        finally:
            browser.close()
    with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()
        assert row is not None
        checks = conn.execute("SELECT action,choices,tags FROM mood_checks WHERE user_id=? ORDER BY id", row).fetchall()
        assert {c[0] for c in checks} == {"new","skip","reuse"}
        assert all("private-check-in prose" not in str(c) for c in checks)
        decisions = conn.execute(
            "SELECT kind,reason,satisfaction FROM decisions JOIN proposals ON proposals.id=decisions.proposal "
            "WHERE proposals.owner=? ORDER BY kind", row,
        ).fetchall()
        assert decisions == [("rejected", "Prefer a quieter course", None),
                             ("selected", "I want to explore art", None), ("visited", None, 4)]
        assert conn.execute("SELECT count(*) FROM proposals WHERE owner=?", row).fetchone()[0] >= 3
    print("Browser flow passed. Survey 24/24, interrupted registration recovered, English & Korean, "
          "desktop & mobile, loaded photos, consistent detail views, Mia JSON download, skip & explicit reuse. "
          "External browser requests: 0. Browser exceptions: 0.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-db", required=True, type=Path)
    run(parser.parse_args().qa_db)
