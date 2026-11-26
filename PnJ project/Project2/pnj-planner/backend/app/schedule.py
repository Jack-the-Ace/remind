"""Construct one conservative draft shared by P, PnJ, J and the Mia export."""
from datetime import timedelta

from .opening_calendar import opening_metadata


def local(lang, ko, en):
    return en if lang == "en" else ko


def lock_problems(trip, lang):
    for day in range(1, trip.slots + 1):
        spans = sorted((x.start, x.end) for x in trip.locked if x.day == day and x.start and x.end)
        overlaps = any(start >= end for start, end in spans) or any(
            previous[1] > following[0] for previous, following in zip(spans, spans[1:]))
        if overlaps:
            return [local(lang, f"{day}일차 고정 일정의 시각이 겹치거나 종료가 시작보다 빨라요.",
                          f"Fixed commitments on day {day} overlap or have an inconsistent end time.")]
        # No route provider can certify a zero-minute transfer between different
        # commitments. Leave a positive but unverified gap marked as such.
        locks = [x for x in trip.locked if x.day == day and x.start and x.end]
        for first in locks:
            for second in locks:
                if first != second and first.end == second.start and first.place != second.place:
                    return [local(lang, f"{day}일차 약속 사이에 이동할 시간이 없어요.", f"Day {day} has no transfer time between different appointments.")]
    return []


def _stop(site, lang, sequence):
    admission = site["basicAdmissionKrw"]
    return {
        "id":site["id"], "sequence":sequence, "name":site["name"][lang], "region":site["region"][lang],
        "address":site["address"], "coordinates":site["coordinates"], "activities":site["activities"][lang],
        "isMarket": "market" in site["tags"], "eveningActivity": "night" in site["tags"],
        "timeBand":site.get("timeBand"),
        "visitAllocation":({"minutes":None, "source":"programme-unverified"} if site.get("offer") else {"minutes":[30,45],"source":"illustrative-planning-target"}),
        "setting":site["setting"], "walking":site["walking"], "accessNote":site["accessNote"][lang],
        "photo":site["photo"], "source":site["source"], "checkedOn":site["checkedOn"],
        "informationType":"inherited-static", "openingHours":opening_metadata(site["id"]) or site["hours"], "typicalStayMinutes":site["typicalStayMinutes"],
        "timeRange":{"start":None, "end":None}, "admission":{"basicKrw":admission, "category":site["fee"], "source":site["source"]},
        "verify":["opening-hours", "entrance-access", "transport", "optional-purchases"] +
                    ([] if admission is not None else ["admission-price"]) + ([] if site["coordinates"] else ["coordinates"]),
    }


def _edge(a, b, lang):
    return {"from":a, "to":b, "minutes":None, "status":"unverified",
        "note":local(lang, "경로와 이동 시간을 확인해 주세요.", "Check the route and travel time.")}


def _day_notes(day, lang, diet):
    p, mid, j = [], [], []
    if day["locked"]:
        for item in day["locked"]:
            start = item["start"] or local(lang, "시작 미정", "start TBD")
            end = item["end"] or local(lang, "종료 미정", "end TBD")
            origin = local(lang, "예시 일정 · ", "Example commitment · ") if item["source"] == "example" else ""
            p.append(f'{origin}{item["label"]} · {start} – {end}')
        mid.append(local(lang, "약속 전후의 이동을 확인하기 전까지 이날의 빈 시간은 비워둘게요.",
                          "Keep the rest of this day open until travel around your commitments is confirmed."))
        j.append(local(lang,"장소와 앞뒤 이동 경로를 확인하세요. 입력하지 않은 약속 시각은 미정이에요.",
                       "Check the locations and transfers on both sides. Unspecified appointment times are open."))
        return {"P":p, "PnJ":p+mid, "J":p+mid+j}
    if not day["stops"]:
        note = local(lang,"추가로 확인된 후보가 없어 자유 일정으로 남겨 두었어요.", "Free day. No additional matching stops were available.")
        return {"P":[note], "PnJ":[note], "J":[note]}

    for i, stop in enumerate(day["stops"]):
        if stop.get("timeBand"):
            p.append(f'{stop["name"]} · {stop["activities"][0]}')
            mid.extend([p[-1], stop["accessNote"]])
            j.extend([p[-1], stop["accessNote"], local(lang, "프로그램의 시작·종료 시각을 확인한 뒤 앞뒤 이동을 계획하세요.", "Use the published start and end times to plan your journey there and back.")])
            continue
        if stop["eveningActivity"]:
            band = local(lang, "저녁에 시작하는 예시", "Example evening visit")
        elif i:
            band = local(lang, "이후 여유 있는 시간", "Later in the same outing")
        else:
            band = local(lang, "오전 또는 이른 오후 예시", "Example morning or early-afternoon visit")
        p.append(f'{stop["name"]} · {stop["activities"][0]}')
        mid.append(local(lang, f'{band} · {stop["name"]}에서 30–45분 정도 머무는 예시예요.',
                         f'{band} · allow roughly 30–45 minutes at {stop["name"]} as a planning guide.'))
        j.append(local(lang, f'{i+1}. {stop["name"]} 도착 후 시간을 기준으로 한 예시예요. 처음 15분은 주변을 둘러보고, 이어지는 15–30분에는 다음 활동을 즐겨 보세요. {stop["activities"][0]}.',
                       f'{i+1}. {stop["name"]} · relative to arrival here, allow an illustrative first 15 minutes to find your bearings, then another 15–30 minutes for this activity: {stop["activities"][0]}.'))
        j.append(stop["accessNote"])
        fee = stop["admission"]["basicKrw"]
        if fee is not None:
            j.append(local(lang, f'자료에 기록된 기본 관람료는 {fee:,}원이에요. 특별전·구매 비용은 별도 확인이 필요해요.',
                           f'The catalogue lists basic admission at KRW {fee:,}. Check any special exhibitions or purchases separately.'))
        else:
            j.append(local(lang, '정확한 입장 비용은 미확인이에요.', 'The exact admission cost is unknown.'))
        if i < len(day["stops"])-1:
            j.append(local(lang, "이동 전에 15분 쉬는 예시예요. 교통편과 실제 소요 시간은 따로 확인해 주세요.",
                           "Allow a 15-minute break as a planning example. Check the next connection and journey time separately."))
    mid.append(local(lang, "다음 장소로 이동하기 전에 잠시 쉬어도 좋아요.", "Leave a little free time before continuing."))
    market = next((s["name"] for s in day["stops"] if s["isMarket"]), None)
    if diet:
        meal = local(lang, "식사는 직접 준비하거나 재료를 확인한 뒤 선택하세요. 확인된 식당·메뉴는 없어요.",
                     "Bring your own meal or confirm ingredients first. No verified menu is available.")
    elif market:
        meal = local(lang, f"식사 후보로 이 코스에 있는 {market} 안의 가게를 살펴볼 수 있어요. 메뉴·가격·영업 여부는 현장에서 확인하세요.",
                     f"For a possible meal, browse the stalls at {market} on this course. Check today's opening, ingredients and prices before ordering.")
    else:
        meal = local(lang, "원하는 때 식사 시간을 비워 두세요. 식당과 메뉴는 아직 정하지 않았어요.",
                     "Leave a break for a meal. A restaurant and menu have yet to be chosen.")
    mid.append(meal)
    j.extend([meal, local(lang, "입장 가능 시간과 비용을 확인하세요. 늦어지면 다음 활동을 줄이고 고정 약속과 복귀를 우선하세요.",
                         "Check admission times and fees. If delayed, shorten an optional activity and prioritise commitments and your return.")])
    return {"P":p, "PnJ":mid, "J":j}


def build_days(trip, assigned, places, lang):
    days = []
    locks_by_day = {d:[lock.model_dump() for lock in trip.locked if lock.day == d] for d in trip.groups}
    seq = 0
    for d, locked in locks_by_day.items():
        date = (trip.startDate + timedelta(days=(d or 1)-1)).isoformat() if trip.startDate and (d is not None or not trip.locked) else None
        day = {"day":d,"date":date,"locked":locked,"stops":[],"transfers":[]}
        if not locked:
            for pid in assigned.get(d, []):
                seq += 1
                day["stops"].append(_stop(places[pid], lang, seq))
        day["notes"] = _day_notes(day, lang, trip.diet)
        days.append(day)

    # Include both boundaries of each free segment, even when the previous or
    # next day is locked. Unknown user anchors stay unknown rather than geocoded.
    unknown = local(lang, "장소 미정", "Location TBD")
    for i, day in enumerate(days):
        def locations(entry):
            locked = entry["locked"]
            if len(locked) > 1 and any(not item.get("start") for item in locked):
                return [local(lang, "약속 간 이동 순서 미정", "Commitment order unconfirmed")]
            return [item.get("place") or unknown for item in sorted(locked, key=lambda item: item.get("start") or "")] or [p["name"] for p in entry["stops"]]
        own = locations(day)
        if not own:
            continue
        prior = (trip.startPoint if i == 0 else trip.lodging) or unknown
        after = (trip.returnPoint if i == len(days)-1 else trip.lodging) or unknown
        pairs = list(zip([prior, *own], [*own, after]))
        day["transfers"] = [_edge(a,b,lang) for a,b in pairs if a != b or a == unknown]
        if i and days[i-1]["locked"] and not trip.lodging:
            prev = locations(days[i-1])[-1]
            day["transfers"][0:0] = [_edge(prev,own[0],lang)]
        if i+1<len(days) and days[i+1]["locked"] and not trip.lodging:
            following = locations(days[i+1])[0]
            day["transfers"].append(_edge(own[-1],following,lang))
    stops = [s for day in days for s in day["stops"]]
    known = [s for s in stops if s["admission"]["basicKrw"] is not None]
    costs = {"currency":"KRW", "basis":"one_visitor_whole_itinerary",
             "knownBasicAdmissionSubtotal":sum(s["admission"]["basicKrw"] for s in known) if known else None,
             "confirmedBasicAdmissionPlaceIds":[s["id"] for s in known],
             "unknownAdmissionPlaceIds":[s["id"] for s in stops if s["admission"]["basicKrw"] is None],
             "unknownCategories":["transport","meals","extras"] + (["lodging"] if trip.days is None or trip.days > 1 else []), "total":None}
    checks = [local(lang,"운영 시간과 이동 경로는 방문일에 확인해 주세요.", "Verify opening hours and transfers for your visit."),
              local(lang,"교통·식사 등을 포함한 전체 비용은 미확인이에요.", "The total including transport and meals is unknown.")]
    if not trip.startDate:
        checks.append(local(lang,"날짜를 정한 뒤 휴관일을 확인하세요.", "Choose your dates and check for closures."))
    if trip.diet:
        checks.append(local(lang,"재료와 조리 환경이 확인된 식당 정보가 없어 음식 체험을 제외했어요.", "Food activities were excluded because ingredients and preparation cannot be verified."))
    if trip.lodging or trip.startPoint or trip.returnPoint or trip.locked:
        checks.append(local(lang,"숙소·약속을 기준으로 앞뒤 이동 경로와 소요 시간을 확인해야 해요.",
                            "Check inbound and outbound travel around your lodging and commitments."))
    if trip.walking == "low":
        checks.append(local(lang, "스스로 걷는 양을 조절하는 활동이에요. 입구에서의 거리와 계단은 확인해야 해요.",
                            "These activities allow you to set your pace. Verify walking distances and steps at the entrance."))
    if trip.transport:
        checks.append(local(lang, f"희망 이동 수단({trip.transport})의 이용 가능 여부와 이동 시간을 확인하세요.",
                            f"Check availability and travel times for your chosen transport ({trip.transport})."))
    if trip.lodging and trip.lodgingSource == "example":
        checks.append(local(lang, "예시로 입력한 숙소가 있어요. 실제 출발 전에 숙소를 확인하세요.", "Your lodging is an example entry. Confirm the actual lodging before travelling."))
    if trip.weather != "unknown":
        checks.append(local(lang, "날씨는 검증용 시나리오예요.", "Weather is a test scenario."))
    return days, checks, costs


def assess_limits(trip, days, costs, lang):
    """Classify known violations separately from checks that need better data."""
    conflicts, pending = [], []
    if trip.budgetKrw is not None:
        known = [costs.get("knownBasicAdmissionSubtotal"), costs.get("total")]
        comparable = costs.get("currency") == "KRW" and costs.get("basis") == "one_visitor_whole_itinerary"
        if comparable and any(value is not None and value > trip.budgetKrw for value in known):
            conflicts.append(local(lang, "확인된 비용만으로 예산 상한을 넘어요.", "Known costs already exceed your budget."))
        elif not comparable or costs.get("total") is None or costs.get("unknownCategories") or costs.get("unknownAdmissionPlaceIds"):
            pending.append(local(lang, "전체 비용이 예산 안인지 추가 확인이 필요해요.", "The full trip cost still needs checking against your budget."))
    if trip.availableMinutes is not None:
        stops = [s for day in days for s in day["stops"]]
        durations = [s.get("typicalStayMinutes") for s in stops] + [e["minutes"] for day in days for e in day["transfers"]]
        known = [m for m in durations if isinstance(m,(int,float)) and m >= 0]
        if sum(known) > trip.availableMinutes:
            conflicts.append(local(lang, "확인된 체류·이동 시간이 가용 시간을 넘어요.", "Known visits and transfers exceed your available time."))
        elif len(known) < len(durations) or not all(s.get("timeRangeVerified") for s in stops):
            pending.append(local(lang, "가용 시간 안에 다녀올 수 있는지 확인해 주세요.", "Check whether the visits and travel fit your time limit."))
    if trip.walking == "stepFree" or trip.avoidHeights:
        pending.append(local(lang,"계단·높은 곳을 피할 수 있는 경로를 방문 전에 확인해 주세요.", "Check the route for steps or elevated sections before deciding."))
    return conflicts, pending


def handoff(course, language=None):
    """An explicit allowlist keeps identity, raw survey and mood out of the export."""
    cond = course["conditions"]
    providers = dict(course["providers"])
    statistics = providers.get("statistics", {})
    aggregate = statistics.get("aggregate")
    if aggregate:
        # Mia can cite the dataset without inferring the traveller's residence.
        providers["statistics"] = {"status":statistics["status"],
                                 "aggregate":{k:aggregate[k] for k in ("id","surveyYear","source","publishedAt")}}
    alternatives = [local(course["language"], "늦어지면 선택 활동을 줄이고 약속을 지키세요.", "Shorten an optional activity if delayed and keep commitments.")]
    return {
        "schemaVersion":"mia.itinerary/2", "personalitySummary":course.get("personalitySummary"),
        "planId":course["id"], "courseId":course.get("courseId",course["id"]), "planVersion":course["version"],
        "language":course["language"], "timeZone":"Asia/Seoul", "startDate":cond["startDate"], "durationDays":cond["days"],
        "mode":"rules-demo", "validation":{"status":"draft-demo","includesExampleInputs":cond.get("lodgingSource") == "example" or any(lock.get("source")=="example" for lock in cond["locked"]),"routeVerified":False,"openHoursVerified":False,"totalBudgetVerified":False},
        "experienceFormat":course.get("format","itinerary"), "moodSummary":course.get("moodSummary"),
        "unconfirmedConditions":[key for key in ("days","startDate","lodging","startPoint","returnPoint","budgetKrw","availableMinutes","transport","companions","diet") if not cond.get(key) and cond.get(key) != 0],
        **({"activityMatch":course["activityMatch"]} if course.get("activityMatch") else {}),
        "recommendationReasons":course.get("reasons",[]), "conditionMatch":course.get("conditionMatch"),
        "catalogVersion":course["catalogVersion"], "checks":course["checks"], "alternatives":alternatives,
        "travelConditions":{k:cond.get(k) for k in ("lodging","lodgingSource","startPoint","returnPoint","transport","walking","avoidHeights","diet","budgetKrw","availableMinutes","mustVisit","avoid","indoor","interests","companions","weather")},
        "providers":providers, "costs":course["costs"],
        "days":[{"day":d["day"],"date":d["date"],"locked":d["locked"],"transfers":d["transfers"],
                 "stops":[{k:s.get(k) for k in ("id","name","sequence","coordinates","timeRange","visitAllocation","activities","admission","openingHours","source","checkedOn","verify")} for s in d["stops"]]}
                for d in course["days"]],
    }

