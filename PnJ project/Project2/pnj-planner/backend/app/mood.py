"""Small bilingual vocabulary for the offline demo. Free text is used only in memory."""
import re

FEELINGS = {
    "tired": r"지쳤|지쳐|지친|피곤|힘들|tired|exhausted|worn out",
    "happy": r"기분\s*좋|즐거|신나|happy|excited|great mood",
    "restless": r"답답|무료해|지루|restless|bored",
    "calm": r"평온|마음이 편안|calm today",
    "low": r"우울|울적|슬프|슬퍼|기운이 없|feeling low|feeling down|\bsad\b",
    "curious": r"궁금|호기심|curious",
}
EXPERIENCES = {
    "rest": r"쉬고|쉴|쉬는|편하게|여유|휴식|힐링|relax|unwind|\brest\b|take it easy",
    "quiet": r"조용|한적|quiet|peaceful",
    "market": r"시장|market",
    "new": r"재밌|재미있|색다|새로|새로운|something fun|new experience|discover",
    "active": r"활동적|몸을 움직|활기차게|많이\s*걷|active|energetic|walk a lot",
    "walk": r"산책|걷고|stroll|walk",
    "nature": r"자연|숲|nature|forest", "culture": r"문화|culture|cultural",
    "art": r"전시|미술|art museum|galler|exhibiti", "history": r"역사|고궁|history|palace",
    "indoor": r"실내|indoor", "outdoor": r"야외|outdoor", "shopping": r"쇼핑|shopping",
    "busy": r"활기찬|활기\s*있는|혼잡|붐비|북적|crowd|bustling|lively", "food": r"맛집|음식 체험|food tour",
    "solo": r"혼자|\balone\b|\bsolo\b",
    "social": r"교류|어울리고|socialise|socialize", "photo": r"사진|photograph",
    "night": r"야경|night view", "kpop": r"케이팝|k[ -]?pop",
    "club": r"\b(?:night[ -]?clubs?|clubs?|clubbing)\b|나이트\s*클럽|클럽|클러빙",
    "dance": r"\b(?:dance|dances|dancing)\b|춤|댄스",
    "nightlife": r"\bnight[ -]?life\b|밤\s*문화|나이트라이프",
    "music": r"\bmusic\b|음악",
    "bookclub": r"\bbook[ -]?clubs?\b|북\s*클럽|독서\s*모임",
    "fanclub": r"\bfan[ -]?clubs?\b|팬\s*클럽",
}
NEGATIVE = re.compile(r"\b(?:no|not|avoid|skip|without|don't|never)\b|싫|피하|피했|피할|제외|말고|원치|않|안\s*(?:마시|갈|가고|추고)")
# Remove other senses before checking the bare English/Korean word for a nightclub.
OTHER_CLUB = re.compile(r"\b(?:book|fan|sports?|golf|chess|football|running|tennis|youth|social)[ -]?clubs?\b|"
                        r"\bclub (?:soda|sandwich|membership|teams?)\b|(?:북|팬|골프|독서|스포츠)\s*클럽")
NO_ALCOHOL = re.compile(r"\b(?:non[- ]?alcoholic|alcohol[- ]free|sober)\b|무알코올|논알코올")
DRINK = re.compile(r"\b(?:drink(?:ing)?(?: alcohol)?|alcohol|booze)\b|음주|술")


def interpret(text, places=None):
    choices, interests, avoid = {}, [], []
    only_indoor = False
    must, avoid_sites = [], []
    clauses = re.split(r"[,.;!?\n]|지만|대신|싶고|그리고|(?<=않고)|(?<=않아도)|(?<=않아서)|"
                       r"\bbut\b|\b(?:and|yet)\s+(?=i\b|want\b|don't\b|no\b|not\b)|(?=\bwithout\s+(?:drinking|alcohol))|\bjust want\b",
                       text.casefold().replace("’", "'"))
    for clause in clauses:
        negative = NEGATIVE.search(clause)
        activity_text = clause
        for pid, place in (places or {}).items():
            if any(name.casefold() in clause for name in place["name"].values()):
                for name in place["name"].values():
                    activity_text = activity_text.replace(name.casefold(), "")
                if negative:
                    avoid_sites.append(pid)
                elif re.search(r"꼭|필수|must",clause):
                    must.append(pid)
        for key, pattern in FEELINGS.items():
            if re.search(pattern, clause) and not negative:
                choices.setdefault("mood", key)
        for key, pattern in EXPERIENCES.items():
            subject = OTHER_CLUB.sub("", activity_text) if key == "club" else activity_text
            if re.search(pattern, subject):
                (avoid if negative else interests).append(key)
        if not negative and re.search(r"(?:danc(?:e|ing) (?:with|together)|사람들과|함께\s*춤)", activity_text):
            interests.append("social")
        if NO_ALCOHOL.search(clause) or (negative and DRINK.search(clause)):
            avoid.append("alcohol")
        if not negative and re.search(r"실내\s*(?:활동|장소)?\s*만|only indoors?|indoors? only", clause):
            only_indoor = True
    if "club" in interests and "club" not in avoid:
        interests.extend(("nightlife", "music"))
    limits = {}
    if avoid or avoid_sites:
        limits["avoid"] = sorted(set(avoid+avoid_sites))
    if must:
        limits["mustVisit"] = sorted(set(must))
    if re.search(r"알레르기|allerg(?:y|ies|ic)",text,re.I) and not re.search(r"no (?:food )?allerg|알레르기(?:가|는)?\s*없",text,re.I):
        allergens = {"peanut":"땅콩|peanut","shellfish":"갑각류|조개|shellfish","milk":"우유|milk|dairy","egg":"달걀|계란|egg","nut":"견과|tree nut","wheat":"밀가루|wheat","sesame":"참깨|sesame"}
        names = [label for label, pattern in allergens.items() if re.search(pattern,text,re.I)]
        limits["diet"] = "allergy: " + (", ".join(names) or "confirm ingredients")
    if re.search(r"무단차|휠체어|step[- ]free|wheelchair",text,re.I):
        limits["walking"]="stepFree"
    if only_indoor:
        limits["indoor"] = "only"
    return choices, sorted(set(interests) - set(avoid)), limits
