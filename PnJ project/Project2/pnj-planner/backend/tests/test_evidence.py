"""Counterfactuals use the same catalogue, history and rules unless specified."""
from datetime import date
import pytest

from app import personality, planner, survey_stats
from app.mood import interpret
from app.schedule import assess_limits
from app.sources import applicable
from app.trip import Trip


@pytest.mark.parametrize("text,mood,wanted,excluded", [
    ("피곤하지 않아. 오늘은 많이 걷고 싶어.", None, {"active","walk"}, set()),
    ("지쳤지만 혼자 있고 싶지는 않아. 활기찬 시장에 가고 싶어.", "tired", {"busy","market"}, {"solo"}),
    ("I’m not sad. I just want somewhere quiet.", None, {"quiet"}, set()),
    ("I’m excited, but I don’t want crowded places.", "happy", set(), {"busy"}),
    ("피곤하지 않고 숲에서 쉬고 싶어.", None, {"rest","nature"}, set()),
])
def test_feeling_is_independent_of_wanted_experience(text, mood, wanted, excluded):
    choices, tags, limits = interpret(text)
    assert choices.get("mood") == mood
    assert set(tags) == wanted and set(limits.get("avoid", [])) == excluded
    result = planner.generate({}, {"action":"new","choices":choices,"tags":tags}, limits, [], "ko")
    assert len(result["courses"]) == 3
    for course in result["courses"]:
        for stop in course["scoreTrace"]:
            assert excluded.isdisjoint(planner.PLACES[stop]["tags"])


def activity_profile(level):
    answers = {item:3 for item,*_ in personality.SURVEY["items"]}
    answers.update({"e4-1":level, "e4-2":6-level})
    scores = personality.score(personality.SURVEY["version"], answers)
    return {"preferences":personality.initial_preferences(scores)}


def test_single_facet_dose_and_current_request(monkeypatch):
    mood = {"action":"new", "tags":["rest","quiet"], "choices":{}}
    for level, expected in [(3,0), (4,0.4), (5,0.8)]:
        context = activity_profile(level)
        score, trace = planner._score(planner.PLACES["forest"], context, mood, Trip(), [])
        assert sum(h["points"] for h in trace["contributions"]["hypothesis"]) == expected
        courses = planner.generate(context,mood,{},[],"ko")["courses"]
        assert all({"rest","quiet"} <= set(planner.PLACES[next(iter(c["scoreTrace"]))]["tags"]) for c in courses)
    no_profile = planner.generate({}, {}, {}, [], "en")["courses"]
    assert len(no_profile) == 3
    monkeypatch.setitem(planner.RULES["weights"], "historicalActivity", 0)
    without = planner.generate({}, {}, {}, [], "en")["courses"]
    assert no_profile[0]["title"] != without[0]["title"]
    assert all(not t["contributions"]["statistics"] for c in without for t in c["scoreTrace"].values())


def test_official_multiple_response_rates_and_residence_fallback():
    data = survey_stats.DATA
    assert data["integratedAudit"]["rowsByYear"] == {"2019":6098,"2023":1614,"2024":3216,"2025":2423}
    assert sum(data["finalWaves"].values()) == 6067
    assert not data["integratedAudit"]["combinedWithFinal"]
    base = data["groups"]["all"]
    assert base["rawN"] == 6067 and base["weightedDenominator"] == pytest.approx(11587037.513)
    assert base["activities"]["shopping"]["rate"] == pytest.approx(0.8311204812)
    assert base["visits"]["gyeongbok"]["rate"] == pytest.approx(0.4221660218)
    for residence, minimum, expected in [(None,100,"all"),("unmapped",100,"all"),("일본",100,"JP"),("JP",2000,"all")]:
        assert survey_stats.scope_for(residence,minimum) == expected
    assert survey_stats.contribution("namdaemun","JP",0.2)["observedRate"] == pytest.approx(.8874153045)
    assert survey_stats.contribution("kstar","all",0.2) is None


def test_no_double_credit_for_the_same_pace_and_no_guess_for_legacy_scores():
    prefs = {"activity":{"value":1,"source":"personality"}, "pace":{"value":5,"source":"direct"}}
    _, trace = planner._score(planner.PLACES["pureun"], {"preferences":prefs}, {}, Trip(), [])
    assert trace["contributions"]["direct"][0]["match"] == "rest"
    assert not trace["contributions"]["hypothesis"]


def test_incomparable_costs_and_record_validity():
    for cost in [{"currency":"USD","basis":"one_visitor_whole_itinerary","total":999},
                 {"currency":"KRW","basis":"group_per_day","total":999}]:
        conflict, pending = assess_limits(Trip(budgetKrw=10), [], cost, "en")
        assert not conflict and pending
    event = {"placeId":"sejong","validFrom":"2026-05-01","validThrough":"2026-05-02",
             "updatedAt":"2026-04-28T00:00:00+09:00","retrievedAt":"2026-04-28T01:00:00+09:00",
             "sourceUrl":"https://example.invalid/event",
             "usageTerms":"test fixture","status":"verified","sourceType":"official_static"}
    for d in (None, date(2026,4,30), date(2026,5,3)):
        assert applicable([event], d, ["sejong"]) == []
    assert applicable([event], date(2026,5,2), ["sejong"]) == [event]
    assert applicable([{**event,"sourceType":"test_fixture"}], date(2026,5,2), ["sejong"]) == []


@pytest.mark.parametrize(("sentence","wanted","avoid"), [
    ("Go dancing", {"dance"}, set()),
    ("No alcohol and wanna dance", {"dance"}, {"alcohol"}),
    ("I got a club sandwich", set(), set()),
    ("A fan club", {"fanclub"}, set()),
    ("맞춤 여행을 원해", set(), set()),
    ("클럽 말고 춤추고 싶어", {"dance"}, {"club"}),
])
def test_activity_vocabulary_keeps_context(sentence, wanted, avoid):
    _, tags, limits = interpret(sentence)
    assert set(tags) == wanted and set(limits.get("avoid", [])) == avoid
