"""Match a stated activity to a documented facility or search area, before ranking."""
CLUB_OFFERS = {"nightclub", "nightlife_area"}
GROUPS = {"bookclub", "fanclub"}
ACTIVITIES = {"club", "nightlife", "dance", "music"} | GROUPS


def focus_for(trip, mood):
    wanted = set(trip.interests) | set((mood or {}).get("tags", []))
    # A club with dancing is a more specific outing than a dance lesson.
    for key in ("club", "nightlife", "dance", "bookclub", "fanclub", "music"):
        if key in wanted and key not in trip.avoid:
            return key
    return None


def match_level(site, focus, avoid):
    offer = site.get("offer")
    if not offer or focus in GROUPS:
        return None
    if focus in {"club", "nightlife"} and offer not in CLUB_OFFERS:
        return None
    if focus == "music" and offer == "dance_class":
        return None
    if focus == "dance" and "alcohol" in avoid and offer != "dance_class":
        return None
    if focus not in {"club", "nightlife", "dance", "music"}:
        return None
    return "area" if offer == "nightlife_area" else "direct"


def explain(site, focus, level, context, avoid, lang):
    reasons = [site["reason"][lang]]
    pref = (context.get("preferences") or {}).get("structure", {})
    structured = pref.get("source") in {"direct", "personality"} and (pref.get("value") or 0) > 3
    if structured:
        reasons.append(site["planningTip"][lang])
    if "alcohol" in avoid:
        if site["offer"] == "dance_class":
            reasons.append({"ko":"술을 마시지 않는다고 해서 안무 수업으로 골랐어요.", "en":"You said you don’t drink, so the activity here is a dance lesson."}[lang])
        else:
            reasons.append({"ko":"음주를 원하지 않으니, 예약 전에 음료 구매 조건을 확인해 보세요.", "en":"Since you don’t drink, check any drink-purchase policy before booking."}[lang])
    match = {"requested": focus, "level": level, "offer": site["offer"], "source": site["source"],
             "verification": "documented-activity-date-unverified"}
    if structured:
        match["guidance"] = {"axis":"structure", "source":pref["source"]}
    return match, reasons
