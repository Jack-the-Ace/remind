"""Rank real Seoul places, then build a stable itinerary from eligible places."""
from .seoul_places import PLACES, describe, local
from .trip_intent import interpret
from .trip_memory import affinity

from .travel_copy import profile_reason

# Area preference for a lodging base, never a distance or travel-time estimate.
NAMGURO_AREAS = {"pureun": 2, "boramae": 1, "seonyudo": 1, "botanic": 1}
DRIVING_OPTIONS = {"boramae", "pureun", "botanic", "seonyudo", "forest"}


def area_fit(key, anchor):
    normalized = anchor.lower().replace(" ", "")
    if normalized in {"남구로역", "남구로", "namguro", "namgurostation", "구로구", "guro-gu"}:
        return NAMGURO_AREAS.get(key, 0)
    return int(bool(anchor) and normalized in PLACES[key]["district"].lower().split("|"))


def preferences(mood, wish, avoid):
    intent = interpret(mood, wish, avoid)
    return intent.wish, intent.mood, intent.blocked


# A specific experience should not turn into unrelated filler just to reach three cards.
EXPERIENCES = {"kpop", "art", "performance", "night", "museum", "market", "history", "food", "shopping"}
VARIETY_TAGS = EXPERIENCES | {"nature", "photo", "rest", "walk", "indoor", "culture"}


def distinct_heads(ranked):
    """Break exact ties using experience overlap. Higher personal fit always wins."""
    pool = list(ranked)
    heads = []
    while pool and len(heads) < 3:
        best_rank = pool[0][0]
        peers = [row for row in pool if row[0] == best_rank]
        chosen_tags = [PLACES[key]["tags"] & VARIETY_TAGS for _, key, _ in heads]

        def overlap(row):
            tags = PLACES[row[1]]["tags"] & VARIETY_TAGS
            return max((len(tags & other) / max(1, len(tags | other))
                        for other in chosen_tags), default=0)
        selected = min(peers, key=overlap)
        pool.remove(selected)
        heads.append(selected)
    return heads + pool


def itinerary(places, nights):
    if not nights:
        return [[dict(placeId=p["id"], activities=p["activities"][:1] if len(places)>1 else p["activities"]) for p in places]]
    days = [[dict(placeId=p["id"], activities=list(p["activities"]))] for p in places]
    while len(days) < nights + 1:
        days.append([])  # Free day, without an invented venue or a transfer.
    return days


def candidates(mood, wish, user, lang, *, intent=None, previous_ids=(), memory=None, exclude=None):
    intent = intent or interpret(mood, wish, user["avoid"])
    if intent.wish & intent.blocked:
        return []
    traits = {tag for winners in user["traits"].values() for tag in winners}
    ranked = []
    for key, place in PLACES.items():
        tags = place["tags"]
        if key == exclude or tags & intent.blocked or not intent.required <= (tags | {place["fee"]}) or (intent.car and key not in DRIVING_OPTIONS):
            continue
        wanted = sorted(tags & intent.wish)
        feeling = sorted(tags & intent.mood)
        fit = sorted(tags & traits)
        area = area_fit(key, intent.anchor)
        recent = key in previous_ids
        votes = user.get('strengths', {})
        strength = sum(n for group in votes.values() for tag,n in group.items() if tag in tags) if votes else len(fit)*4
        bonus, note = affinity(key,memory or {},lang)
        visited = bool((memory or {}).get(key, {}).get("visited"))
        novelty = -int(visited and "new" in intent.wish)
        rank = (len(wanted), area, len(feeling), novelty, strength + bonus, -int(recent))
        ranked.append((rank, key, dict(visited=visited, area=area, feedbackWeight=bonus, memoryNote=note, rank=list(rank), surveyVotes=strength, wish=wanted, mood=feeling, survey=fit, recentlySuggested=recent)))
    ranked.sort(key=lambda x: x[0], reverse=True)
    eligible = ranked
    requested = intent.wish & EXPERIENCES
    ranked = distinct_heads([row for row in eligible if not requested or PLACES[row[1]]["tags"] & requested])
    reserved = {key for _, key, _ in ranked[:3]}
    used = set(reserved)
    cards = []
    for _, key, evidence in ranked:
        place = PLACES[key]
        max_stops = intent.nights + 1 if intent.nights else 1 if "short" in intent.wish else 2
        # The top three routes own their stops. Never borrow another card's headline.
        focus = place["tags"] & intent.wish & (EXPERIENCES | {"nature","rest","quiet","culture","indoor","active","budget","photo"})
        specific = focus & (EXPERIENCES | {"photo"})
        if specific:
            focus = specific
        nearby = [(score, other) for score, other, _ in eligible
                  if other != key and other not in used and PLACES[other]["zone"] == place["zone"]
                  and (not focus or focus & PLACES[other]["tags"])
                  and (intent.nights or not requested or requested & PLACES[other]["tags"])
                  and (memory or {}).get(other, {}).get("decision") != "reject"]
        nearby.sort(key=lambda row: (PLACES[row[1]]["district"] == place["district"],
                                     row[0], row[1] in place["partners"]), reverse=True)
        keys = [key] + [other for _, other in nearby[:max_stops-1]]
        if key in reserved:
            used.update(keys)
        places = [describe(k, lang) for k in keys]
        first = places[0]
        days = itinerary(places, intent.nights)
        stops = [a for day in days for step in day for a in step["activities"]]
        profile = profile_reason(evidence["survey"], lang)
        cards.append(dict(id=key, name=first["name"], region=first["region"], photo=first["photo"],
                          description=local(place["theme"], lang), stops=stops, places=places, days=days,
                          reason=stops[0], profileReason=profile, tags=sorted(place["tags"]), fit=evidence["survey"],
                          match=evidence))
    return cards
