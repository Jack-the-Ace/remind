"""Compare UI requests on the same QA account. Only the before/after QA DBs are allowed."""
import argparse
import json
import os
import sqlite3

from playwright.sync_api import expect, sync_playwright
from browser_flow import BASE, RUNTIME, button, verify_target

CASE = "Just wanna go to CLUB and dance with pretty KOrean girls... and wanna get drunken so much..."


def run(phase, pair):
    before = RUNTIME / f"qa-nightlife-before-{pair}.sqlite3"
    after = RUNTIME / f"qa-nightlife-after-{pair}.sqlite3"
    target = verify_target(before if phase == "before" else after)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto(BASE)
        credentials = {"username":"qa-nightlife-" + pair, "password":os.environ["PNJ_QA_PASSWORD"]}
        if phase == "before":
            survey = page.request.get(BASE+"/api/survey").json()
            answers = {q["id"]:3 for q in survey["items"]}
            answers.update({"c5-1":5, "c5-2":1})
            created = page.request.post(BASE+"/api/signup", data={**credentials, "version":survey["version"],
                "profile":{}, "language":"en", "answers":answers})
            assert created.status == 201
        button(page,"Sign in").first.click()
        page.get_by_label("Username", exact=True).fill(credentials["username"])
        page.get_by_label("Password", exact=True).fill(credentials["password"])
        button(page,"Sign in").last.click()
        expect(page.locator("textarea")).to_be_visible()
        with sqlite3.connect(target.as_uri()+"?mode=ro",uri=True) as conn:
            assert conn.execute("SELECT count(*) FROM proposals").fetchone()[0] == 0
            if phase == "before":
                if after.exists():
                    raise RuntimeError("Choose a new QA pair; snapshot already exists.")
                with sqlite3.connect(after) as snapshot:
                    conn.backup(snapshot)
        button(page,"Restless").click()
        page.locator("textarea").fill(CASE)
        with page.expect_response(lambda r:r.url.endswith("/api/plans") and r.status==200) as pending:
            button(page,"Find experiences for me").click()
        response = pending.value
        body = response.request.post_data_json
        assert body["checkIn"]["text"] == CASE and body["checkIn"]["choices"] == {"mood":"restless"} and body["trip"] == {}
        result = response.json()
        cards = page.locator(".cards > article")
        expect(cards).to_have_count(len(result["courses"]))
        for i, c in enumerate(result["courses"]):
            expect(cards.nth(i)).to_contain_text(c["reasons"][0])
            print([s["id"] for d in c["days"] for s in d["stops"]], c["reasons"], flush=True)
        print("Version, mood, activities, exclusions:",result["rulesVersion"],result["activeMood"]["choices"],
              result["activeMood"]["tags"],len(result["excluded"]))
        if phase == "after":
            assert {"club","dance","music","nightlife","social"} <= set(result["activeMood"]["tags"])
            assert all(c["activityMatch"]["level"] in {"direct","area"} for c in result["courses"])
            assert result["courses"][0]["activityMatch"]["level"] == "direct"
            button(page,"View itinerary").first.click()
            button(page,"J · Detailed").click()
            button(page,"Select plan for Mia").click()
            with page.expect_download() as download:
                page.get_by_role("link",name="Download JSON").click()
            data = json.loads(download.value.path().read_text(encoding="utf-8"))
            assert data["activityMatch"] == result["courses"][0]["activityMatch"] and data["detailMode"] == "J"
        with sqlite3.connect(target.as_uri()+"?mode=ro",uri=True) as conn:
            assert not any(CASE in row for row in conn.iterdump())
        browser.close()


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before","after"))
    parser.add_argument("pair", type=int)
    args=parser.parse_args()
    run(args.phase, f"{args.pair:02d}")
