"""PnJ facet scoring and the independent, editable travel-preference mapping."""

import json
from pathlib import Path

DATA = Path(__file__).with_name("data")
SURVEY = json.loads((DATA / "pnj_facets.json").read_text(encoding="utf-8"))
PREFERENCE_RULES = json.loads((DATA / "preference_rules.json").read_text(encoding="utf-8"))


def definition():
    return {
        "version": SURVEY["version"],
        "facets": SURVEY["facets"],
        "items": [
            {"id": item_id, "text": {"en": en, "ko": ko}}
            for item_id, _, _, en, ko in SURVEY["items"]
        ],
        "sources": SURVEY["sources"],
        "koreanTranslation": SURVEY["koreanTranslation"],
    }


def score(version, answers):
    if version != SURVEY["version"]:
        raise ValueError("SURVEY_VERSION")
    items = SURVEY["items"]
    if set(answers) != {item[0] for item in items}:
        raise ValueError("SURVEY_INCOMPLETE")
    totals = {}
    for item_id, domain, direction, _, _ in items:
        value = answers[item_id]
        if type(value) is not int or not 1 <= value <= 5:
            raise ValueError("SURVEY_RESPONSE")
        totals[domain] = totals.get(domain, 0) + (value if direction == 1 else 6 - value)
    return {facet: (value - 2) * 100 / 8 for facet, value in totals.items()}


def initial_preferences(scores):
    result = {}
    for axis in PREFERENCE_RULES["axes"]:
        domain = PREFERENCE_RULES["hypotheses"].get(axis)
        value = 1 + scores[domain] / 25 if domain in scores else None
        result[axis] = {
            "value": value,
            "source": "personality" if value is not None else "unknown",
            "confirmed": False,
        }
    return result


def preference_view(initial, direct):
    return {
        axis: (
            {"value": direct[axis], "source": "direct", "confirmed": True}
            if axis in direct else initial[axis]
        )
        for axis in PREFERENCE_RULES["axes"]
    }
