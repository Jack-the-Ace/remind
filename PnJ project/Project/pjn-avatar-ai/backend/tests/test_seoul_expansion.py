from pathlib import Path

import pytest

from app.catalog import candidates
from app.personas import VOICES, empathy
from app.seoul_places import PLACES, PHOTOS, describe
from app.travel_copy import guidance, present_history
from app.trip_intent import interpret

NATURE = dict(traits={"pace":["rest"], "setting":["nature"], "company":["solo"]}, avoid="")
CITY = dict(traits={"pace":["active"], "setting":["city"], "company":["social"]}, avoid="")


def top(mood="", wish="", profile=NATURE, **kwargs):
    return candidates(mood, wish, profile, "ko", **kwargs)[:3]


@pytest.mark.parametrize("wish,tag", [
    ("역사문화 여행", "history"), ("K-POP 팬 여행", "kpop"), ("쇼핑", "shopping"),
    ("맛집 여행", "food"), ("야경 사진", "night"), ("가성비 여행", "budget"),
    ("뮤지컬이나 공연", "performance"), ("미술 전시", "art"),
])
def test_specific_experiences(wish, tag):
    cards = top("피곤해", wish)
    assert len(cards) == 3 and all(tag in c["tags"] for c in cards)
    assert all(c["match"]["wish"] for c in cards)


@pytest.mark.parametrize("wish,days", [("야경 사진 2박3일", 3), ("1박 2일", 2),
                                        ("night views for two nights", 3), ("실내만", 1)])
def test_disjoint_regional_itineraries(wish, days):
    used = set()
    for card in top(wish=wish):
        assert len(card["days"]) == days
        ids = {p["id"] for p in card["places"]}
        assert not (ids & used)
        used.update(ids)
        assert len({PLACES[k]["zone"] for k in ids}) == 1
        order = [step["placeId"] for day in card["days"] for step in day]
        assert len(order) == len(set(order)) and ids == set(order)
        assert card["stops"] == [a for day in card["days"] for step in day for a in step["activities"]]


def test_restrictions_memory_and_mood():
    def ids(cards):
        return [c["id"] for c in cards]
    assert ids(top(profile=NATURE)) != ids(top(profile=CITY))
    assert ids(top("피곤해")) != ids(top("일상이 지루해"))
    liked = {"gwangjang": {"decision":"like", "visited":True, "rating":5}}
    fresh = top("지루해", "새로운 경험", memory=liked)
    assert "gwangjang" not in ids(fresh)
    limited = top("피곤해", "붐비지 않는 곳, 적은 활동량", memory=liked)
    assert len(limited) == 3
    assert all(not PLACES[p["id"]]["tags"] & {"busy","active","walk"} for c in limited for p in c["places"])
    for card in top(wish="무료만"):
        assert all(p["fee"] == "free-basic" for p in card["places"])
    assert interpret("", "2박3일, 남구로역 근처 숙소").anchor == "남구로역"
    museums = top("tired", "history and museums for two nights")
    assert len(museums) == 3 and all("museum" in c["tags"] for c in museums)


def test_voices_and_bilingual_reasons():
    for lang in ("ko","en"):
        cards = candidates("tired","K-pop",NATURE,lang)[:3]
        for card in cards:
            reasons = [guidance(card["match"],card["name"],card["stops"][0],v,lang) for v in VOICES.values()]
            assert len(set(reasons)) == 2 and all("Survey matches:" not in t for t in reasons)
        assert empathy("min","tired",{"rest"},lang) != empathy("miho","tired",{"rest"},lang)
    legacy = {"mode":"demo","language":"en","courses":[dict(stops=["Look at the pond"],
              profileReason="Survey matches: familiar, flex.",match={"survey":["familiar","flex"]})]}
    restored = present_history(legacy)["courses"][0]
    assert "familiar surroundings" in restored["profileReason"] and "spontaneous plans" in restored["basis"]["survey"]


def test_place_metadata_and_photo_assets():
    image_root = Path(__file__).resolve().parents[2] / "frontend/public"
    assert 30 <= len(PLACES) <= 50
    assert len({p["district"] for p in PLACES.values()}) >= 15
    for key in PLACES:
        for lang in ("ko", "en"):
            item = describe(key, lang)
            assert item["source"].startswith("https://") and item["address"]
            assert item["activities"] and item["fee"] in {"unknown","paid","free-basic"}
            if lang == "ko":
                assert all(a.endswith("기") for a in item["activities"])
        if key in PHOTOS:
            p = PHOTOS[key]
            assert all(p.get(k) for k in ("title","author","source","licenseUrl","license"))
            assert (image_root / p["src"].lstrip("/")).read_bytes()[:2] == b"\xff\xd8"
