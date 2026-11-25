"""Explainable feedback from the signed-in account's saved recommendations."""
from .seoul_places import PLACES, local

EXPERIENCE = {"quiet","walk","nature","culture","rest","active","city","shopping","history","food","indoor","new"}


def memories(trips):
    entries = []
    for trip in trips:
        for course, response in trip.get("feedback", {}).items():
            if course in PLACES:
                entries.append((response.get("updated",0), course, response))
    latest = {}
    for _,course,response in sorted(entries,key=lambda entry:entry[0],reverse=True):
        facts = latest.setdefault(course,{})
        if "decision" not in facts and response.get("decision"):
            facts.update(decision=response["decision"],reason=response.get("reason"))
        if "visited" not in facts and response.get("visited"):
            facts.update(visited=True,rating=response.get("rating"))
    return latest


def affinity(key, memory, lang):
    total = 0
    evidence = []
    tags = PLACES[key]["tags"]
    for source, response in memory.items():
        shared = EXPERIENCE & tags & PLACES[source]["tags"]
        exact = key == source
        reason = response.get("reason")
        decision = response.get("decision")
        weight = 0
        if decision == "like":
            weight = 3 if exact else min(2,len(shared))
        elif decision == "reject":
            targeted = {"crowds":"busy","walking":"walk","new":"familiar"}.get(reason)
            weight = -4 if exact else -2 if targeted in tags else 0
        if weight:
            evidence.append((weight,source,decision))
        rating = response.get("rating") if response.get("visited") else None
        visit = (rating-3) if rating and (exact or len(shared)>=2) else 0
        if visit:
            evidence.append((visit,source,str(rating)+"/5"))
        total += weight + visit
    if not total:
        return 0, ""
    aligned = [entry for entry in evidence if entry[0]*total > 0]
    _,source,kind = max(aligned,key=lambda e:abs(e[0]))
    name = local(PLACES[source]["name"],lang)
    if lang=="ko":
        text = {"like":f"전에 추천한 {name} 코스가 마음에 든다고 했지.", "reject":f"전에 추천한 {name} 코스를 거절한 기록을 고려했어."}.get(kind,f"{name} 방문 후 남긴 {kind} 평가를 참고했어.")
    else:
        text = {"like":f"You liked the suggested {name} outing.", "reject":f"You declined the earlier {name} suggestion."}.get(kind,f"You rated your visit to {name} {kind}.")
    return max(-5,min(5,total)),text
