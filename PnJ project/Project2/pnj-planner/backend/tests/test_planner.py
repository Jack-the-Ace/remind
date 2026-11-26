from pathlib import Path

import pytest
from pydantic import ValidationError

from app.opening_calendar import regular_closure
from app.planner import PLACES, generate, handoff


def proposals(trip=None, prefs=None, mood=None, history=None, lang="en"):
    return generate({"preferences": prefs or {}}, mood or {}, trip or {}, history or [], lang)


def ids(course):
    return [stop["id"] for day in course["days"] for stop in day["stops"]]


def test_catalogue_is_cited_with_real_local_photos():
    assert sum(not p.get('offer') for p in PLACES.values()) == 33
    photos = [p["photo"] for p in PLACES.values() if p["photo"]]
    assert len(photos) == 30
    assert sum(bool(p["coordinates"]) for p in PLACES.values()) == 21
    public = Path(__file__).resolve().parents[2] / "frontend" / "public"
    for photo in photos:
        assert photo["author"] and photo["changes"] and photo["source"].startswith("https://commons.wikimedia.org/")
        assert photo["licenseUrl"] and (public / photo["src"].lstrip("/")).read_bytes().startswith(b"\xff\xd8")


def test_unknown_mood_and_weather_are_not_assigned_fake_values():
    a = proposals(mood={"action":"skip","choices":{"goal":"connect"}})
    b = proposals()
    assert [ids(c) for c in a["courses"]] == [ids(c) for c in b["courses"]] and b["providers"]["weather"]["forecast"] is None
    assert b["providers"]["trends"]["status"] == "unconnected"
    for c in b["courses"]:
        assert not any(t["contributions"]["current"] for t in c["scoreTrace"].values())
        assert c["costs"]["total"] is None


def test_fractional_hypothesis_direct_and_current_are_ranked_separately():
    a = proposals(prefs={"social":{"value":3.25,"source":"personality"}})["courses"][0]
    assert "social" in PLACES[ids(a)[0]]["tags"]
    b = proposals(prefs={"social":{"value":1,"source":"direct"}})["courses"][0]
    assert "solo" in PLACES[ids(b)[0]]["tags"]
    c = proposals({"interests":["history"]}, {"social":{"value":5,"source":"direct"}},
                  {"action":"new","choices":{"atmosphere":"green","goal":"rest"}})["courses"]
    for course in c:
        assert any("history" in PLACES[p]["tags"] for p in ids(course))
    quiet = proposals(mood={"action":"new","choices":{"atmosphere":"quiet","goal":"rest"}})
    active = proposals(mood={"action":"new","choices":{"activity":"high","goal":"discover"}})
    assert [p["id"] for p in quiet["courses"]] != [p["id"] for p in active["courses"]]
    # Mood label alone doesn't presume the traveller wants activity or rest.
    assert [ids(c) for c in proposals(mood={"action":"new","choices":{"mood":"restless"}})["courses"]] == [ids(c) for c in proposals()["courses"]]


@pytest.mark.parametrize("spec", [
    {"indoor":"only","mustVisit":["forest"]}, {"diet":"severe shellfish allergy","mustVisit":["noryangjin"]},
    {"avoid":["art"],"mustVisit":["seosomun"]},
])
def test_conflicts_do_not_pass(spec):
    r=proposals(spec)
    assert not r["courses"] and r["notices"]


@pytest.mark.parametrize("spec",[{"budgetKrw":0},{"budgetKrw":100000},{"availableMinutes":20},{"walking":"stepFree"},{"avoidHeights":True},{"avoid":["unrecognised condition"]}])
def test_unverified_limits_return_conditional_experiences(spec):
    courses=proposals(spec)["courses"]
    assert len(courses)==3
    for c in courses:
        assert c["conditionMatch"]["status"]=="needs_check" and c["conditionMatch"]["pending"]
        assert c["conditions"]["days"] is None and c["format"]=="experience"
        assert c["conditions"]|spec == c["conditions"]


def test_rain_scenario_explicit_indoor_preference_and_allergy():
    r = proposals({"weather":"rain","indoor":"only","diet":"peanut allergy","walking":"low"})
    assert r["providers"]["weather"] == {"provider":"scenario","scenario":"rain","forecast":None,"verifiedForDate":False}
    assert r["courses"]
    for c in r["courses"]:
        for p in ids(c):
            assert PLACES[p]["setting"] == "indoor" and PLACES[p]["walking"] == "self-paced"
            assert not {"food","market"} & set(PLACES[p]["tags"])
    assert proposals({"indoor":"prefer","mustVisit":["forest"]})["courses"]


def test_slot_solver_preserves_five_day_partial_trip_and_unknown_times():
    locked = [{"day":1,"label":"Conference","place":"COEX","start":"10:00","end":"16:00"},
              {"day":2,"label":"Family visit"},{"day":3,"label":"Team dinner","place":"Gangnam","start":"18:00"}]
    trip = {"days":5,"startDate":"2026-12-01","lodging":"City Hall","returnPoint":"Gimpo","locked":locked}
    for course in proposals(trip)["courses"]:
        assert all(not day["stops"] for day in course["days"][:3])
        assert [day["locked"][0]["label"] for day in course["days"][:3]] == [i["label"] for i in locked]
        assert course["days"][1]["locked"][0]["start"] is None
        assert course["days"][2]["locked"][0]["end"] is None
        for day in course["days"][3:]:
            assert day["stops"] and set(day["notes"]) == {"P","PnJ","J"}
            assert all(edge["minutes"] is None for edge in day["transfers"])
            assert day["transfers"][0]["from"] == "City Hall"
        assert course["days"][-1]["transfers"][-1]["to"] == "Gimpo"
        assert len(set(ids(course))) == len(ids(course))
        out=handoff({**course,"password":"secret","answers":{"q01":3},"extraProfile":"private"})
        assert out["validation"]["status"] == "draft-demo" and not out["validation"]["routeVerified"]
        assert out["planId"] == course["id"] and out["days"][0]["date"] == "2026-12-01"
        assert [s["id"] for d in out["days"] for s in d["stops"]] == ids(course)
        assert not {"password","answers","extraProfile"} & set(out)


def test_overlapping_and_back_to_back_appointments_are_not_accepted():
    trip = {"days":2,"locked":[{"day":1,"label":"A","place":"Myeongdong","start":"09:00","end":"10:30"},
                               {"day":1,"label":"B","place":"Gangnam","start":"10:00","end":"11:00"}]}
    assert not proposals(trip)["courses"]
    trip["locked"][1]["start"] = "10:30"
    assert not proposals(trip)["courses"]


def test_known_gallery_closures_checked_on_assigned_day_including_mandatory_stops():
    monday = "2026-11-30"
    assert not proposals({"startDate":monday,"mustVisit":["seosomun"]})["courses"]
    courses = proposals({"startDate":monday,"days":2,"mustVisit":["seosomun","namsema"]})["courses"]
    assert courses
    for course in courses:
        for day in course["days"]:
            assert all(not regular_closure(s["id"],monday,day["day"]) for s in day["stops"])
        assert {p["id"] for p in course["days"][1]["stops"]} == {"seosomun","namsema"}


def test_diversity_replay_and_feedback():
    base=proposals({"interests":["art"]})
    assert len({c["id"] for c in base["courses"]}) == 3
    anchor=ids(base["courses"][0])[0]
    reject=proposals({"interests":["art"]},history=[{"action":"rejected","placeIds":[anchor]}])
    assert ids(reject["courses"][0])[0] != anchor
    assert proposals({"interests":["art"]}) == base
    assert not any("rated" in reason for c in base["courses"] for reason in c["reasons"])
    preferred=proposals({"mustVisit":[anchor]},history=[{"action":"rejected","placeIds":[anchor]}])
    assert preferred["courses"] and all(anchor in ids(c) for c in preferred["courses"])


def test_invalid_data_fails_closed():
    with pytest.raises(ValidationError):
        proposals({"indors":"only"})
    with pytest.raises(ValidationError):
        proposals({"days":3,"locked":[{"day":4,"label":"outside trip"}]})


def test_verified_time_and_money_fixture_distinguishes_missing_cost_from_free():
    from app.schedule import assess_limits
    from app.trip import Trip
    # Fixture only. These are not times or prices for a Seoul attraction.
    spec = Trip(availableMinutes=60, budgetKrw=5000)
    day = {"stops":[{"typicalStayMinutes":45,"timeRangeVerified":True}],"transfers":[{"minutes":15}]}
    costs = {"total":5000, "currency":"KRW", "basis":"one_visitor_whole_itinerary", "unknownCategories":[], "unknownAdmissionPlaceIds":[]}
    assert assess_limits(spec, [day], costs, "en") == ([],[])
    day["transfers"][0]["minutes"] = 16
    assert assess_limits(spec, [day], costs, "en")[0]
    day["transfers"][0]["minutes"] = 0
    assert assess_limits(spec, [day], {**costs, "total":5001}, "en")[0]
    assert assess_limits(spec, [day], {**costs, "total":None, "unknownCategories":["meal"]}, "en")[1]
    assert assess_limits(spec, [day], {**costs, "total":None, "knownBasicAdmissionSubtotal":5001}, "en")[0]


def test_meal_candidates_reference_only_selected_markets_and_unknown_prices():
    c = proposals({"mustVisit":["mangwon"]})["courses"][0]
    notes = c["days"][0]["notes"]
    assert any("Mangwon Market" in s and "prices" in s for s in notes["PnJ"])
    assert any("relative to arrival" in s for s in notes["J"])
    assert c["providers"]["statistics"]["aggregate"]["rawN"] == 6067
    assert c["providers"]["trends"]["signals"] is None

def test_undecided_duration_does_not_place_experience_on_a_booked_day():
    out=proposals({"locked":[{"day":1,"label":"Appointment"}]})
    assert len(out["courses"])==3
    for course in out["courses"]:
        assert course["conditions"]["days"] is None
        booked, flexible = course["days"]
        assert booked["day"]==1 and not booked["stops"] and booked["locked"]
        assert flexible["day"] is None and flexible["date"] is None and flexible["stops"]
