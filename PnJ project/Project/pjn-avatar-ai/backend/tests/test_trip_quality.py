from app.catalog import candidates
from app.trip_intent import interpret
from app.seoul_places import PLACES, ADDITIONS

PROFILE = {"traits": {"setting": ["city"], "pace": ["active"], "company": ["social"]}, "avoid": ""}
WISH = ("차가 안 막히는 시간대에 내 차를 끌고 힐링 여행을 하고 싶어. 숙소는 남구로역 근처였으면 좋겠고, "
        "사람들이 붐비지 않는 시간대에 이동하며 1박 2일 힐링 여행을 하고 싶어.")


def test_overnight_matches_every_day_and_marks_unknowns():
    intent = interpret("답답해", WISH)
    assert intent.car and intent.light_traffic and intent.low_crowd
    assert intent.anchor == "남구로역" and intent.nights == 1
    cards = candidates("답답해", WISH, PROFILE, "ko")[:3]
    assert len(cards) == 3 and cards[0]["id"] == "pureun"
    for card in cards:
        assert "busy" not in card["tags"] and "rest" in card["match"]["wish"]
        assert len(card["days"]) == 2
        assert {step["placeId"] for d in card["days"] for step in d} == {p["id"] for p in card["places"]}
        assert all(p["photo"]["source"] and p["source"] for p in card["places"])
    assert interpret("", "강아지와 함께, 자차로 갈래").review
    assert "car" in interpret("", "차 없이 산책").blocked
    assert "busy" in interpret("", "less crowded parks").blocked
    assert interpret("", "1박2일").nights == 1
    assert interpret("", "홍대 근처 숙소").anchor == "홍대"
    assert interpret("", "남구로역 근처 숙소는 말고 홍대 근처 호텔").anchor == "홍대"
    assert interpret("", "stay near Seoul Forest Station").anchor == "Seoul Forest Station"


def test_rank_order_is_stable_and_prior_suggestions_only_break_ties(monkeypatch):
    cards = candidates("", "아직 모르겠어", {"traits": {}, "avoid": ""}, "ko")
    ids = [c["id"] for c in cards]
    reranked = candidates("", "지난번과 다른 곳", {"traits": {}, "avoid": ""}, "ko", previous_ids=ids[:3])
    assert [c["id"] for c in reranked][-3:] == ids[:3]
    indoor = candidates("", "실내만", PROFILE, "ko")
    assert len(indoor) >= 3 and all("indoor" in c["tags"] for c in indoor)
    # Preserve the original nine-place fixture and its exact expected result.
    with monkeypatch.context() as original:
        for key in ADDITIONS:
            original.delitem(PLACES, key)
        assert candidates("", "실내만", PROFILE, "ko")[0]["id"] == "botanic"
    for card in candidates("피곤해", "조용히 쉬고 싶어", PROFILE, "ko"):
        assert "busy" not in card["tags"]

