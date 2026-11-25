from app.catalog import candidates
from app.survey import QUESTIONS, VERSION, Survey, score, strengths
from app.trip_memory import memories


def test_strength_and_midpoint():
    raw = dict(version=VERSION, answers={q["id"]:0 for q in QUESTIONS})
    assert strengths(raw)["company"]["solo"] == 4
    raw["answers"]["s1"] = 1
    assert strengths(raw)["company"] == {"solo":3,"social":1}
    raw["answers"]["s6"] = 1
    assert strengths(raw)["company"] == {"solo":2,"social":2}
    assert strengths(None) == {}


def test_strength_changes_rank_with_same_winning_tags():
    raw = dict(version=VERSION,answers={q["id"]:0 for q in QUESTIONS})
    first = []
    winners = []
    for answer in (0,1):
        raw["answers"]["s1"] = answer
        winners.append(score(Survey(**raw)))
        profile = dict(traits=winners[-1],strengths=strengths(raw),avoid="")
        first.append(candidates("","",profile,"en")[0]["id"])
    assert winners[0] == winners[1]
    assert first == ["pureun","boramae"]


def test_visit_and_decision_are_independent_across_trips():
    latest = memories([{"feedback":{"pureun":{"decision":"like","updated":2}}},
                       {"feedback":{"pureun":{"visited":True,"rating":4,"updated":1}}}])
    assert latest["pureun"] == dict(visited=True,rating=4,decision="like",reason=None)


def test_current_wish_overrides_memory():
    profile = {"traits":{}, "avoid":""}
    def rank(wish, memory):
        return candidates("보통",wish,profile,"ko",memory=memory)
    assert rank("",{})[0]["match"]["memoryNote"] == ""
    assert rank("",{"botanic":{"decision":"like"}})[0]["id"] == "botanic"
    declined = {"pureun":{"decision":"reject","reason":"taste"}}
    assert rank("",declined)[0]["id"] != "pureun"
    liked_market = {"gwangjang":{"decision":"like","visited":True,"rating":5}}
    assert rank("조용한 자연에서 쉬고 싶어", liked_market)[0]["id"] != "gwangjang"
