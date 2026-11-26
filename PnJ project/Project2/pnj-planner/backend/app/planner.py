"""Offline itinerary generation. All rankings and tie breaks are reproducible."""
import hashlib
import json
from pathlib import Path

from .opening_calendar import regular_closure
from . import activity_match, survey_stats
from .schedule import build_days, handoff, lock_problems, assess_limits
from .trip import Trip, integrations

BASE = Path(__file__).parent
PLACES = json.loads((BASE / "data/places.json").read_text(encoding="utf-8"))
PLACES.update(json.loads((BASE / "data/activity_places.json").read_text(encoding="utf-8")))
RULES = json.loads((BASE / "ranking_rules.json").read_text(encoding="utf-8"))
TAGS = {tag for place in PLACES.values() for tag in place["tags"]}
LABELS = {
    "new": ("새로운 경험", "trying something new"), "familiar": ("익숙한 활동", "familiar activities"),
    "social": ("함께하는 활동", "shared activities"), "solo": ("혼자 즐기는 시간", "independent exploration"),
    "planned": ("순서가 있는 활동", "structured activities"), "flex": ("자유로운 진행", "flexibility"),
    "active": ("활동적인 하루", "an active day"), "rest": ("여유 있는 휴식", "an unhurried break"),
    "busy": ("활기찬 분위기", "a lively atmosphere"), "quiet": ("차분한 활동", "a quiet activity"),
    "culture": ("문화 체험", "culture"), "food": ("지역 음식", "local food"), "kpop": ("K-pop 체험", "K-pop"),
    "night": ("저녁 풍경", "evening views"), "nature": ("자연", "nature"), "city": ("도시 산책", "city exploration"),
    "indoor": ("실내 활동", "indoor activities"), "outdoor": ("야외 활동", "outdoor activities"),
    "art": ("미술", "art"), "history": ("역사", "history"), "museum": ("박물관", "museums"),
    "shopping": ("쇼핑", "shopping"), "market": ("시장 구경", "markets"), "walk": ("걷기", "walking"),
    "performance": ("공연", "performance"), "photo": ("사진 촬영", "photography"), "budget": ("가벼운 지출", "budget-conscious activities"),
    "paid": ("유료 관람", "ticketed attractions"),
}


def say(lang, ko, en):
    return en if lang == "en" else ko


def place_options(language):
    return sorted(({"id": p["id"], "name": p["name"][language]} for p in PLACES.values()), key=lambda p: p["name"])


def _site_failures(site, trip):
    tags = set(site["tags"])
    failures = []
    if trip.indoor == "only" and site["setting"] != "indoor":
        failures.append("indoor-only")
    if any(value == site["id"] or value in tags for value in trip.avoid):
        failures.append("explicit-avoid")
    if trip.walking == "low" and site["walking"] != "self-paced":
        failures.append("walking-load")
    if trip.diet and tags & {"market", "food"}:
        failures.append("ingredients-unverified")
    basic = site.get("basicAdmissionKrw")
    if trip.budgetKrw is not None and basic is not None and basic > trip.budgetKrw:
        failures.append("known-cost-over-cap")
    return failures


def _blocked(trip, lang):
    messages = []
    if any(site not in PLACES for site in trip.mustVisit):
        messages.append(say(lang, "필수 방문 장소를 장소 목록에서 다시 선택해 주세요.", "Please choose required stops from the catalogue."))
    return messages + lock_problems(trip, lang)


def _history_impact(site, history):
    """Use only explicitly recorded signals. Exposure and a visit are distinct."""
    effects = []
    for item in history:
        if not isinstance(item, dict):
            continue
        ids = item.get("placeIds") or []
        same = site["id"] in ids
        kind = item.get("action")
        if kind == "exposed" and same:
            effects.append(("exposed", -RULES["weights"]["exposure"]))
        elif kind == "rejected" and same:
            effects.append(("rejected", -RULES["weights"]["feedback"]))
        elif kind == "visited" and same:
            effects.append(("visited", -RULES["weights"]["repeatVisit"]))
        if kind in {"selected", "visited"}:
            satisfaction = item.get("satisfaction")
            sign = 1 if kind == "selected" or isinstance(satisfaction, int) and satisfaction >= 4 else -1 if isinstance(satisfaction, int) and satisfaction <= 2 else 0
            for prev in ids:
                if prev in PLACES and set(PLACES[prev]["tags"]) & set(site["tags"]) & {"history","art","nature","food","night","kpop","performance","shopping"}:
                    if sign:
                        effects.append((kind, sign * RULES["weights"]["feedback"]))
                    break
    return effects


def _score(site, context, mood, trip, history, focus=None, level=None):
    tags = set(site["tags"])
    hits = {key: [] for key in ("wish", "current", "direct", "hypothesis", "feedback", "weather")}
    weights = RULES["weights"]
    def add(source, key, points, **evidence):
        hits[source].append({"match": key, "points": points, **evidence})

    interests = set(trip.interests)
    if level:
        # One explicit request, even when dancing and music describe the same outing.
        add("wish", focus, weights["wish"], matchLevel=level, offer=site["offer"])
        interests -= activity_match.ACTIVITIES
    if trip.indoor == "prefer":
        interests.add("indoor")
    for term in sorted(interests & tags):
        add("wish", term, weights["wish"])
    if trip.budgetKrw is not None and site.get("basicAdmissionKrw") == 0:
        add("wish", "free-basic", 1)
    if trip.weather == "rain" and site["setting"] == "indoor":
        add("weather", "indoor", weights["weather"])
    if mood and mood.get("action") != "skip":
        choices = mood.get("choices", {})
        terms = {tag for field, mapping in RULES["mood"].items() for tag in mapping.get(choices.get(field), [])}
        terms.update(mood.get("tags") or [])
        if level:
            terms -= activity_match.ACTIVITIES
        if not terms and choices.get("mood") == "tired" and "rest" in tags:
            add("current", "gentle-option", 1)
        for tag in sorted(terms & tags):
            add("current", tag, weights["current"])

    for axis, pref in (context.get("preferences") or {}).items():
        value = pref.get("value")
        if axis not in RULES["axes"] or not isinstance(value, (int, float)) or not 1 <= value <= 5 or value == 3:
            continue
        pole = RULES["axes"][axis][0 if value > 3 else 1]
        if pole and pole in tags:
            source = "direct" if pref.get("source") == "direct" else "hypothesis" if pref.get("source") == "personality" else None
            if source:
                points = abs(value - 3) * weights[source]
                # Activity level and preferred pace can describe the same experience.
                same = next((h for h in hits[source] if h["match"] == pole), None)
                if same is None or same["points"] < points:
                    if same is not None:
                        hits[source].remove(same)
                    add(source, pole, points, axis=axis, value=value, facet=pref.get("facet"))
    art = context.get("artInterest")
    learning = (context.get("preferences") or {}).get("learning", {})
    if art is not None and art > 50 and "art" in tags and learning.get("source") != "direct":
        add("hypothesis", "art", (art - 50) / 25 * weights["hypothesis"], facet="O2", score=art)
    for match, points in _history_impact(site, history):
        add("feedback", match, points)
    # A direct statement replaces a matching personality-derived cue.
    direct_matches = {h["match"] for h in hits["direct"]}
    hits["hypothesis"] = [h for h in hits["hypothesis"] if h["match"] not in direct_matches]
    population = survey_stats.contribution(site["id"], context.get("surveyScope", "all"), weights["historicalActivity"])
    hits["statistics"] = [population] if population else []
    sums = {source: round(sum(h["points"] for h in rows), 6) for source, rows in hits.items()}
    # Priority is lexicographic. Any number of lower-level contributions cannot
    # outweigh an extra explicit interest match or break a mandatory filter.
    score = tuple(sums[k] for k in ("wish", "current", "weather", "direct", "hypothesis", "feedback", "statistics"))
    return score, {"contributions": hits, "priorityScore": score,
                   "placeEvidence":{"id":site["id"], "source":site["source"], "checkedOn":site["checkedOn"],
                                    "experienceTags":sorted(tags), "tagOrigin":"pnj_editorial",
                                    "proposedActivities":site["activities"]}}


def _reasons(site, trace, lang):
    matches = trace["contributions"]
    def labels(source):
        words = list(dict.fromkeys(x["match"] for x in matches[source]))
        return ", ".join(say(lang, *LABELS[key]) for key in words if key in LABELS)
    reasons = []
    if any(hit["match"] == "free-basic" for hit in matches["wish"]):
        reasons.append(say(lang, "예산을 고려해 기본 관람이 무료인 곳을 골랐어요.", "Basic admission is free here, which helps with your budget."))
    for key, ko, en in [
        ("wish", "이번에 관심을 보인 주제와 잘 맞아요. 여기서는 {v} 같은 경험을 할 수 있어요.", "This stop matches your interest in {v}."),
        ("current", "오늘 고른 답에서 이곳과 맞는 점을 찾았어요. {v}에 어울리는 곳이에요.", "Your choices for today point toward {v}."),
        ("direct", "평소에 관심을 보인 활동과 이어져요. 이곳에서 즐길 수 있는 건 {v}입니다.", "Your saved preferences include {v}."),
        ("hypothesis", "설문을 바탕으로 {v}에 관심이 있을 가능성을 약하게 참고했어요.", "Your survey suggests a possible interest in {v}."),
    ]:
        words = labels(key)
        if words:
            reasons.append(say(lang, ko, en).format(v=words))
    if any(row["match"] == "gentle-option" for row in matches["current"]):
        reasons.append(say(lang, "지친 날 가볍게 즐길 수 있는 활동이 있어요.", "There is a gentle activity here for a tiring day."))
    if matches["weather"]:
        reasons.append(say(lang, "비가 오는 검증 시나리오라 실내 활동을 고려했어요.", "The rain test scenario favours an indoor activity."))
    if any(x["points"] > 0 for x in matches["feedback"]):
        reasons.append(say(lang, "직접 선택했거나 방문 후 좋은 평가를 남긴 코스와 활동 주제가 겹쳐요.",
                           "This activity shares a theme with a course you selected or rated positively after a visit."))
    if not reasons and matches["statistics"]:
        activity = say(lang, *LABELS[matches["statistics"][0]["match"]])
        reasons.append(say(lang, f"이곳에서는 {activity} 경험을 할 수 있어요. 2025년 서울 방문객의 활동 기록도 참고했어요.",
                           f"This stop offers {activity}. We also considered activities reported in the 2025 Seoul visitor survey."))
    if not reasons:
        reasons.append(say(lang, "서울에서 해볼 수 있는 활동으로 골랐어요.", "An option to explore from the Seoul catalogue."))
    return reasons


def _assemble(anchor, ranked, traces, free_days, must, reserved, used, start_date):
    """Place mandatory stops in available open slots before filling optional stops."""
    slots = [day for day in free_days for _ in range(2)]
    allocated = {}
    required = list(dict.fromkeys([*must, anchor]))

    def place_required(pid, seen):
        # Prefer empty slots, moving earlier assignments only when necessary.
        for index in sorted(range(len(slots)), key=lambda i: (i in allocated, i)):
            if index in seen or regular_closure(pid, start_date, slots[index] or 1):
                continue
            seen.add(index)
            if index not in allocated or place_required(allocated[index], seen):
                allocated[index] = pid
                return True
        return False

    if not all(place_required(pid, set()) for pid in required):
        return {}
    chosen = set(allocated.values())
    result = {}
    for day in free_days:
        group = [pid for i,pid in sorted(allocated.items()) if slots[i] == day]
        for _ in range(2 - len(group)):
            base = PLACES[group[0]] if group else None
            candidates = [pid for pid in ranked if pid not in chosen and pid not in reserved
                          and not regular_closure(pid, start_date, day or 1)
                          and (not base or PLACES[pid]["zone"] == base["zone"])]
            if not candidates:
                break
            def partner_priority(pid):
                scores = traces[pid]["priorityScore"]
                return (*(-v for v in scores[:3]), pid in used,
                        bool(base and PLACES[pid]["region"]["en"] != base["region"]["en"]),
                        *(-v for v in scores[3:]), pid)
            pid = min(candidates, key=partner_priority)
            chosen.add(pid)
            group.append(pid)
        result[day] = group
    return result


def generate(context: dict, mood: dict, trip: dict, history: list, language: str):
    if mood and mood.get("action") == "skip":
        mood = {**mood, "choices":{}, "tags":[]}
    lang = "en" if language == "en" else "ko"
    spec = Trip.model_validate(trip)
    response = {"mode":"rules-demo", "rulesVersion": RULES["version"], "catalogVersion": RULES["catalogVersion"],
                "providers": integrations(spec, PLACES, context.get("surveyScope","all")), "courses": [], "notices": [], "excluded": {}}
    response["matchStatus"] = "conflict"
    response["conflicts"] = []
    response["notices"] = _blocked(spec, lang)
    if response["notices"]:
        if any(site not in PLACES for site in spec.mustVisit):
            response["matchStatus"] = "needs_check"
        response["conflicts"] = list(response["notices"])
        return response
    free_days = [d for d in spec.groups if not any(lock.day == d for lock in spec.locked)]
    visit_date = None if spec.days is None and spec.locked else spec.startDate
    focus = activity_match.focus_for(spec, mood)
    levels = {}
    eligible = []
    for pid, site in PLACES.items():
        level = activity_match.match_level(site, focus, spec.avoid)
        if pid not in spec.mustVisit and ((focus and not level) or (site.get("offer") and not focus)):
            continue
        if level:
            levels[pid] = level
        failed = _site_failures(site, spec)
        if free_days and all(regular_closure(pid, visit_date, day or 1) for day in free_days):
            failed.append("regular-closure")
        if failed:
            response["excluded"][pid] = failed
        else:
            eligible.append(pid)
    if focus and not any(pid in levels for pid in eligible):
        response["matchStatus"] = "no_activity_match"
        if focus in activity_match.GROUPS:
            notice = say(lang, "이 목록에는 참여할 수 있는 독서·팬 모임의 일정이 아직 없어요.", "The catalogue has no verified book-group or fan-club meetups yet.")
        else:
            notice = say(lang, "현재 자료와 선택한 조건에 맞는 활동 장소를 찾지 못했어요.", "No documented venue for this activity fits the selected conditions.")
        response["notices"].append(notice)
        return response
    if not eligible:
        message = say(lang, "지정한 필수·회피 조건을 함께 만족하는 장소가 현재 목록에 없어요.", "The catalogue has no places matching all of your requirements and exclusions.")
        response["notices"].append(message)
        response["conflicts"].append(message)
        return response
    if not set(spec.mustVisit) <= set(eligible):
        response["notices"].append(say(lang,"필수 방문 장소가 다른 필수 조건과 충돌해요.", "A required stop conflicts with another hard condition."))
        response["conflicts"] = list(response["notices"])
        return response
    if not free_days or len(spec.mustVisit) > 2 * len(free_days):
        response["notices"].append(say(lang,"고정 일정을 그대로 두면 방문을 추가할 시간이 확인되지 않아요.", "There is no verified space to add these visits around your commitments."))
        return response
    scored = {pid: _score(PLACES[pid], context, mood or {}, spec, history or [], focus, levels.get(pid)) for pid in eligible}
    ranked = sorted(eligible, key=lambda pid: (*(-v for v in scored[pid][0]), pid))
    traces = {pid: scored[pid][1] for pid in ranked}
    if set(spec.interests) - TAGS - activity_match.ACTIVITIES:
        response["notices"].append(say(lang,"목록에 없는 관심사는 순위에 반영하지 못했어요.", "An unrecognised interest could not be scored."))
    anchors = [pid for pid in ranked if pid not in spec.mustVisit]
    if spec.mustVisit and (not anchors or len(spec.mustVisit) == 2 * len(free_days)):
        anchors = [spec.mustVisit[0]]
    if focus:
        anchors = [pid for pid in anchors if pid in levels] or [pid for pid in spec.mustVisit if pid in levels]
    # Diverse options at equal priority, never sacrificing direct requests or mood.
    chosen_anchors = []
    while anchors and len(chosen_anchors) < 3:
        def anchor_key(pid):
            theme = set(PLACES[pid]["tags"]) & {"nature","history","art","food","shopping","night","kpop","performance"}
            overlap = max((len(theme & set(PLACES[other]["tags"])) for other in chosen_anchors), default=0)
            personal = scored[pid][0][:-1]
            return (levels.get(pid) == "area", *(-v for v in personal), overlap, -scored[pid][0][-1], PLACES[pid]["photo"] is None, pid)
        winner = min(anchors,key=anchor_key)
        anchors.remove(winner)
        chosen_anchors.append(winner)
    used = set()
    structures = set()
    for anchor in [*chosen_anchors, *anchors]:
        if len(response["courses"]) == 3:
            break
        assigned = _assemble(anchor, ranked, traces, free_days, spec.mustVisit, set(chosen_anchors)-{anchor}, used, visit_date)
        ids = [pid for group in assigned.values() for pid in group]
        footprint = tuple(tuple(sorted(group)) for group in assigned.values())
        if not ids or footprint in structures:
            continue
        site = PLACES[anchor]
        days, checks, costs = build_days(spec, assigned, PLACES, lang)
        failures, pending = assess_limits(spec, days, costs, lang)
        if focus:
            pending.append(site["accessNote"][lang])
        if any(term not in TAGS and term not in PLACES and term != "alcohol" for term in spec.avoid):
            pending.append(say(lang, "입력한 회피 조건 중 장소 자료로 확인하기 어려운 내용이 있어요.", "Check the exclusion that the catalogue could not verify."))
        if failures:
            for reason in failures:
                if reason not in response["conflicts"]:
                    response["conflicts"].append(reason)
                if reason not in response["notices"]:
                    response["notices"].append(reason)
            continue
        structures.add(footprint)
        used.update(ids)
        payload = {"trip": spec.model_dump(mode="json"), "days":[[s["id"] for s in d["stops"]] for d in days],
                   "rules":RULES["version"], "catalog":RULES["catalogVersion"]}
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
        match, reasons = activity_match.explain(site, focus, levels[anchor], context, spec.avoid, lang) if focus else (None, _reasons(site,traces[anchor],lang))
        response["courses"].append({"id":"seoul-"+digest, "version":RULES["version"], "catalogVersion":RULES["catalogVersion"],
            **({"activityMatch":match} if match else {}),
            "format":"experience" if spec.days is None else "itinerary",
            "personalitySummary":context.get("survey"),
            "moodSummary":{k:mood.get(k) for k in ("action","choices","tags","confirmedAt","reusedFrom","editedFrom")} if mood else None,
            "conditionMatch":{"status":"needs_check" if pending else "matches_known_conditions", "pending":pending},
            "status":"draft-demo", "language":lang, "title":site["name"][lang], "summary":site["theme"][lang],
            "region":site["region"][lang], "photo":site["photo"], "reasons":reasons,
            "checks":pending+checks, "days":days, "costs":costs, "conditions":spec.model_dump(mode="json"),
            "providers":response["providers"], "scoreTrace":{pid:traces[pid] for pid in ids}})
    if focus and 0 < len(response["courses"]) < 3:
        response["notices"].append(say(lang, "요청한 활동을 할 수 있거나 찾아볼 수 있는 후보만 골랐어요. 방문일의 프로그램을 확인해 주세요.", "These are the matching options in our catalogue. Check the programme for your date."))
    elif len(response["courses"]) < 3:
        response["notices"].append(say(lang,"필수 조건을 지키며 구분할 수 있는 코스만 표시했어요.", "Only distinct courses meeting the hard conditions are shown."))
    if response["courses"]:
        response["matchStatus"] = "needs_check" if any(c["conditionMatch"]["pending"] for c in response["courses"]) else "matches_known_conditions"
    return response

