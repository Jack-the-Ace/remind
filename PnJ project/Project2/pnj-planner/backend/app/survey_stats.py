"""Verified historical participation. Only load the aggregate artefact, once."""
import json
from pathlib import Path

DATA = json.loads(Path(__file__).with_name("data").joinpath("seoul_survey_2025.json").read_text(encoding="utf-8"))
# Editorial crosswalk to the main experience in this catalogue. No score for unknown mappings.
EXPERIENCE = {
    "gwangjang":"food", "mangwon":"food", "namdaemun":"shopping", "ktown":"shopping",
    "noryangjin":"food", "myeongdong":"shopping", "deoksu":"history", "gyeongbok":"history",
    "changdeok":"history", "nationalmuseum":"history", "baekje":"history",
    "buksema":"art", "namsema":"art", "seosomun":"art", "sejong":"performance",
    "pureun":"nature", "boramae":"nature", "botanic":"nature", "seonyudo":"nature",
    "forest":"nature", "seoseoul":"nature", "dream":"nature", "naksan":"night", "banpo":"night",
    "seokchon":"nature",
}
ALIASES = {v:k for k, names in {"JP":("jp","jpn","japan","일본"), "CN":("cn","chn","china","중국"),
           "TW":("tw","twn","taiwan","대만"), "HK":("hk","hkg","hong kong","홍콩")}.items() for v in names}


def scope_for(residence, minimum):
    key = ALIASES.get((residence or "").strip().casefold())
    if key and DATA["groups"].get(key, {}).get("rawN", 0) >= minimum:
        return key
    return "all"


def provenance(scope):
    group = DATA["groups"][scope]
    return {"id":DATA["id"], "surveyYear":DATA["surveyYear"], "source":DATA["source"],
            "publishedAt":DATA["publicationDate"], "scope":scope, "scopeVariable":DATA["scopeVariable"],
            "rawN":group["rawN"], "weightedDenominator":group["weightedDenominator"], "weight":"WT"}


def contribution(place_id, scope, weight):
    activity = EXPERIENCE.get(place_id)
    if not activity or not weight:
        return None
    cell = DATA["groups"][scope]["activities"][activity]
    return {"match":activity, "points":round(weight * cell["rate"], 6),
            "variable":DATA["metrics"]["activities"][activity]["variable"], "observedRate":cell["rate"],
            "rawYes":cell["rawYes"], "scope":scope, "dataset":DATA["id"]}
