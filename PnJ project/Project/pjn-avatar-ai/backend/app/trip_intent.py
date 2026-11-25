"""Recognise trip constraints independently of experience preferences, in both languages."""
import re
from dataclasses import dataclass

PATTERNS = {
    "rest": r"힐링|쉬고|쉴|쉬는|휴식|생각\s*정리|피곤|지[쳐친쳤]|힘들|여유롭|healing|unwind|relax|rest\b|tired|drained|clear my head",
    "quiet": r"조용|한적|고요|quiet|peaceful",
    "active": r"신나|신난|활동|운동|활력|에너지|energetic|active|excited",
    "busy": r"혼잡|북적|붐비|붐벼|활기|유명|사람(?:들이?|이)?\s*많|crowd\w*|lively|bustling|famous",
    "solo": r"혼자|홀로|alone|solo", "social": r"함께|친구|가족|단체|friends|family|together|group",
    "budget": r"가성비|저예산|아끼|저렴|절약|무료|budget|cheap|free\b", "paid": r"유료|비싼|expensive|paid",
    "nature": r"자연|숲|정원|수목원|강변|nature|forest|garden",
    "walk": r"걷|걸어|걸을|도보|산책|walk\w*", "city": r"도심|시내|도시|urban|city",
    "culture": r"문화|전시|미술|박물관|gallery|museum|culture|art\b",
    "museum": r"박물관|museums?\b",
    "history": r"역사|고궁|궁궐|history|historic|palace", "shopping": r"쇼핑|기념품|shopping|souvenir",
    "kpop": r"케이\s*팝|케이팝|아이돌|한류|k[\s-]?pop|idol",
    "art": r"미술|전시|조각|갤러리|gallery|exhibition|art\b", "performance": r"공연|버스킹|concert|performance|busking",
    "night": r"야경|밤\s*풍경|night\s*(?:view|scape)|after dark|skyline at night", "photo": r"사진|촬영|photograph|photos?",
    "market": r"전통\s*시장|수산\s*시장|traditional market|fish market",
    "food": r"맛집|먹거리|음식|시장|food|market", "new": r"지루|색다른|새로|새로운|낯선|bored|novel|new\b",
    "indoor": r"실내|우천|비가\s*(?:와|오)|indoor|rainy", "outdoor": r"야외|실외|outdoor", "queue": r"대기열|줄\s*서|queu\w*",
    "short": r"반\s*나절|짧게|half[ -]?day|short\b",
    "car": r"자\s*차|내\s*차|자동차|주차|차로|드라이브|차량|driv(?:e|ing)|parking|\bcar\b",
}
LOW_TRAFFIC = r"(?:차(?:가|량이)?|길이?)\s*(?:안\s*막히|막히지\s*않)|교통\s*체증(?:이|을|은)?\s*(?:적|없|피|덜)|체증\s*없|정체(?:가|를)?\s*(?:적|없|피)|(?:light|less|avoid|low|off.peak)\s*traffic|avoid\s*traffic\s*jams"
LOW_CROWD = r"(?:사람(?:들)?이?|인파가?)\s*(?:적|없|덜)|(?:붐비|북적이|혼잡하|복잡하)지\s*않|안\s*붐비|덜\s*붐비|uncrowded|less crowded|few(?:er)? people|not (?:too )?crowded"
MOBILITY = r"적은\s*활동량|활동량[이은]?\s*적|많이\s*걷지|적게\s*(?:걷|걸)|덜\s*(?:걷|걸)|많이\s*걷고\s*싶지|little walking|minimal walking|low[ -]activity|휠체어|거동|무릎|못\s*(?:걸|걷)|(?:걷기|걷는\s*게)\s*(?:힘|어렵|어려)|wheelchair|mobility|can.?t walk"
NO_CAR = r"(?:자동차|자차|차)\s*없이|대중\s*교통\s*만|public transit only|no car|without (?:a |my )?car"
OVERNIGHT = r"1\s*박\s*2\s*일|하룻밤|overnight|(?:two|2)[ -]?days?.{0,12}(?:one|1)[ -]?night|(?:one|1)[ -]?night"
TWO_NIGHTS = r"2\s*박\s*3\s*일|(?:two|2)[ -]?nights?\b|(?:three|3)[ -]?days?\b"
NEG_AFTER = r"^(?:[가-힣]{0,3}\s*)?(?:(?:곳|장소|시간대|길|것|여행)(?:은|는|을|이)?\s*)?(?:말고|피하|피해|피할|싫|제외|어렵|어려|없이|않|원하지\s*않|하지\s*않|지\s*않|힘들)"
NEG_BEFORE = r"(?:avoid(?:ing)?|without|no|not|hate|can't|cannot|don't want)(?:\s+(?:a|the|to))?\s*$"


def has(pattern, text):
    return bool(re.search(pattern, text, re.I))


def parse(text):
    want, avoid = set(), set()
    if has(LOW_CROWD, text):
        want.add("quiet")
        avoid.add("busy")
    if has(MOBILITY, text):
        avoid.update(("walk", "active"))
    if has(NO_CAR, text):
        avoid.add("car")
    clean = re.sub("|".join((LOW_CROWD, LOW_TRAFFIC, NO_CAR, MOBILITY)), " ", text, flags=re.I)
    for tag, regex in PATTERNS.items():
        for m in re.finditer(regex, clean, re.I):
            after = clean[m.end():m.end()+20]
            before = clean[max(0,m.start()-22):m.start()]
            negative = has(NEG_AFTER, after) or has(NEG_BEFORE, before)
            (avoid if negative else want).add(tag)
    return want, avoid


def lodging(text):
    for clause in re.split(r"[,.;!?\n]|말고|대신", text):
        if not has(r"숙소|숙박|호텔|hotel|lodging|stay(?:ing)?|accommodation", clause):
            continue
        ko = re.search(r"([가-힣0-9]+)\s*(?:근처|주변|인근|부근|가까[운이])", clause)
        en = re.search(r"(?:near|around|close to)\s+([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,3}?\s+(?:Station|Park|Market|district)\b|[A-Za-z0-9-]+)", clause, re.I)
        match = ko or en
        if match:
            anchor = re.sub(r"^(?:숙소|호텔|숙박)(?:는|은)", "", match[1])
            if anchor in {"숙소","호텔","역","여기","그곳"}:
                continue
            # A rejected base must not receive an area bonus or become a night stop.
            after = text[text.find(clause)+match.end():]
            if not has(r"^(?:에|의|인)?\s*(?:숙소|숙박|호텔)?(?:는|은|가|이)?\s*(?:말고|싫|피하|제외)", after):
                return anchor
    return ""


@dataclass
class Intent:
    wish: set
    mood: set
    blocked: set
    car: bool
    light_traffic: bool
    low_crowd: bool
    nights: int
    anchor: str
    required: set
    review: list

    def checks(self, lang):
        ko = lang == "ko"
        checks = []
        if self.car:
            checks.append("자차 이동 · 각 목적지의 주차장 위치, 이용 가능 여부, 주차 후 도보 구간을 확인하세요." if ko else "Driving · check parking access, availability and the walk from the car.")
        if self.light_traffic:
            checks.append("교통체증 회피 · 출발·복귀 시각은 당일 교통을 보고 정하세요." if ko else "Low traffic · choose departure and return times using current traffic.")
        if self.low_crowd or "busy" in self.blocked:
            checks.append("혼잡 회피 · 방문일 행사와 예상 방문객을 확인하고 붐비면 쉬는 시간을 조정하세요." if ko else "Crowd avoidance · check events and expected crowds for your visit.")
        if self.anchor:
            checks.append((f"{self.anchor} 근처 숙소 · 위치, 공실, 야간 주차와 관광지까지의 이동을 예약 전에 확인하세요." if ko else f"Lodging near {self.anchor} · verify location, availability, overnight parking and transfers."))
        if "walk" in self.blocked:
            checks.append("걷는 활동을 제외했어요. 입구에서 쉴 곳까지의 거리와 무장애 접근은 현장에 확인하세요." if ko else "Walking activities excluded. Verify accessible entrances, distances and seating.")
        checks.extend(("추가 검토 · " if ko else "Further review · ") + text for text in self.review)
        checks.append("방문일 운영·입장 조건을 확인하세요." if ko else "Verify opening and admission arrangements for your dates.")
        return checks


def interpret(mood, wish, saved_avoid=""):
    w, wb = parse(wish)
    m, mb = parse(mood)
    saved, sb = parse(saved_avoid)
    blocked = wb | mb | saved | sb
    if has(LOW_CROWD, saved_avoid):
        blocked.discard("quiet")
        blocked.add("busy")
    if "quiet" in w or "queue" in blocked:
        blocked.add("busy")
    if "walk" in blocked:
        blocked.add("active")
    text = wish + " " + mood
    required = {tag for tag in ("indoor","outdoor","food","nature","shopping","culture","kpop","history","night","art","museum","market","performance") if
                has("(?:"+PATTERNS[tag]+r")\s*(?:(?:활동|장소|여행지|코스)\s*)?(?:만(?:\s|$|으로|가|하)|only\b)", text)}
    if has(r"무료\s*만|돈\s*(?:안\s*드는|들지\s*않)|free only", text):
        blocked.add("paid")
        required.add("free-basic")
    # Preserve original clauses whenever the finite vocabulary cannot account for
    # their full wording, including unsupported details beside a recognised cue.
    review = []
    for clause in re.split(r"[,.;!?\n]|그리고| but | and ", ". ".join((wish, saved_avoid, mood)), flags=re.I):
        clause = clause.strip()
        if not clause:
            continue
        residual = clause
        for expr in (LOW_TRAFFIC, LOW_CROWD, NO_CAR, MOBILITY, TWO_NIGHTS, OVERNIGHT, *PATTERNS.values()):
            residual = re.sub(expr, " ", residual, flags=re.I)
        residual = re.sub(r"오늘은?|기분이?|동안|많이|담고\s*싶[어다]|아직\s*모르겠어|가고\s*싶[어다]|하고\s*싶[어다]|여행|시간대|근처|숙소|장소|추천|(?:i would like|i want|a trip|please|not sure)", " ", residual, flags=re.I)
        if re.search(r"[가-힣]{2,}|[a-z]{3,}|\d", residual, re.I):
            review.append(clause)
    overnight = has(OVERNIGHT, text) and not has(r"(?:1\s*박\s*2\s*일|숙박)(?:은|이)?\s*(?:말고|아니|싫)|no overnight", text)
    two_nights = has(TWO_NIGHTS, text) and not has(r"(?:" + TWO_NIGHTS + r")\s*(?:말고|싫|아니)", text)
    return Intent(w, m, blocked, "car" in (w | m) and "car" not in blocked,
                  has(LOW_TRAFFIC,text), has(LOW_CROWD,text), 2 if two_nights else int(overnight),
                  lodging(wish) or lodging(mood), required, list(dict.fromkeys(review)))

