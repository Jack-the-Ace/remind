"""Traveller-facing phrases for evidence actually used by the ranker, in display order."""
# Korean infinitives also work as activity labels. English phrases follow "you enjoy".
PHRASES = {
    "kpop": ("K-POP 팬 문화 즐기기", "exploring K-pop fan culture"),
    "night": ("저녁 풍경 감상하기", "taking in the evening skyline"),
    "museum": ("박물관에서 전시 살펴보기", "exploring museum collections"),
    "history": ("옛 건물과 유물 살펴보기", "discovering local history"),
    "art": ("작품을 가까이서 감상하기", "spending time with art"),
    "performance": ("공연 즐기기", "watching performances"),
    "market": ("시장 구경하기", "browsing market stalls"),
    "food": ("현지 먹거리 맛보기", "trying local food"),
    "shopping": ("취향에 맞는 물건 찾아보기", "browsing shops for personal finds"),
    "budget": ("지출을 줄이며 즐기기", "keeping spending low"),
    "quiet": ("차분하게 시간 보내기", "taking things quietly"),
    "rest": ("여유 있게 쉬기", "taking time to unwind"),
    "nature": ("자연 속에 머물기", "spending time in nature"),
    "photo": ("마음에 드는 장면 사진에 담기", "photographing the scenery"),
    "culture": ("지역 문화 만나기", "exploring local culture"),
    "city": ("도심 둘러보기", "exploring city neighbourhoods"),
    "new": ("처음 해 보는 일 즐기기", "trying something new"),
    "active": ("몸을 움직이며 둘러보기", "staying active"),
    "social": ("일행과 함께 즐기기", "sharing activities with others"),
    "solo": ("혼자만의 시간 갖기", "having time to yourself"),
    "busy": ("활기찬 거리 즐기기", "exploring lively places"),
    "indoor": ("실내에서 즐기기", "staying indoors"),
    "outdoor": ("탁 트인 곳에서 보내기", "spending time outdoors"),
    "walk": ("걸으면서 둘러보기", "exploring on foot"),
    "familiar": ("익숙한 분위기 즐기기", "enjoying familiar surroundings"),
    "flex": ("일정을 자유롭게 정하기", "leaving room for spontaneous plans"),
    "planned": ("정한 순서대로 움직이기", "following a plan"),
    "paid": ("유료 관람 즐기기", "visiting ticketed attractions"),
}


def phrases(tags, lang, limit=2):
    parts = [pair[lang == "en"] for tag, pair in PHRASES.items() if tag in tags][:limit]
    if lang == "ko":
        return " · ".join(parts)
    return " and ".join(parts)


def profile_reason(tags, lang):
    if not tags:
        return ""
    interests = phrases(tags, lang)
    if lang == "ko":
        return f"여행 성향 설문에서 골랐던 ‘{interests}’에도 어울리는 코스야."
    return f"In your survey you chose {interests}. This outing gives you room for that."


# Each line is a conditional grounded in a matched cue, not a claim about the visitor.
KOREAN_CUES = {
    "kpop":"K-POP을 가까이서 즐기고 싶다면", "night":"저녁 풍경을 즐기고 싶다면",
    "museum":"전시물을 찬찬히 들여다보고 싶다면", "history":"서울의 옛 모습을 만나고 싶다면", "art":"작품을 찬찬히 보고 싶다면",
    "performance":"공연을 중심으로 하루를 보내려면", "market":"시장 골목이 끌린다면",
    "food":"지역 먹거리를 맛보고 싶다면", "shopping":"가게를 둘러보고 싶다면",
    "budget":"지출 부담을 덜고 싶다면", "quiet":"차분한 시간을 보내고 싶다면",
    "rest":"한숨 돌리고 싶은 날에는", "nature":"자연을 가까이하고 싶다면",
    "photo":"풍경을 사진으로 남기고 싶다면", "culture":"지역 문화를 만나고 싶다면",
    "new":"새로운 경험을 해 보고 싶다면", "active":"가볍게 몸을 움직이고 싶다면",
}


def guidance(evidence, place, activity, voice, lang):
    matched = evidence["wish"] or evidence["mood"]
    cue = phrases(matched, lang, limit=1)
    ko = lang == "ko"
    if cue:
        context = next((clause for tag, clause in KOREAN_CUES.items() if tag in matched), "오늘 이야기한 취향을 생각하면")
        lead = (f"{context} {place} 코스가 어울려. " if ko else
                f"You mentioned {cue}, which makes {place} a good starting point. ")
    else:
        lead = ""
    # Catalogue Korean activities are verb phrases ending in the nominal suffix 기.
    action = activity.removesuffix("기") if ko else activity
    return lead + voice["invite"][lang == "en"].format(activity=action)


def present_history(trip):
    """Localise early Demo reasons on read while keeping the original stored itinerary."""
    if trip.get("mode") != "demo":
        return trip
    lang = trip.get("language", "ko")
    for card in trip.get("courses", []):
        match = card.get("match")
        if not match or "visited" in match:
            continue
        card["profileReason"] = profile_reason(match.get("survey", []), lang)
        if card.get("stops"):
            first = card["stops"][0]
            card["reason"] = f"첫 활동으로는 ‘{first}’를 추천해." if lang == "ko" else f"Here’s a way to start. {first}."
        basis = card.setdefault("basis", {})
        for field in ("wish", "mood", "survey"):
            if match.get(field):
                basis[field] = phrases(match[field], lang)
    return trip
