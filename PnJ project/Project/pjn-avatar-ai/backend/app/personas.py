"""Bilingual companion dialogue; presentation only, never a ranking input."""
VOICES = {
    "miho": {
        "name": "Miho (미호)",
        "style": "Bright, warm and lively. Reflect the traveller's priorities clearly and guide them through one practical step at a time.",
        "rest": ("많이 지쳤구나. 오늘은 한 가지만 정하자! 편하게 쉬려면 어떤 조건이 가장 중요해?", "Sounds like you’re tired. Let’s keep it simple! What would help you take a proper break?"),
        "active": ("움직이고 싶은 날이구나! 하고 싶은 활동부터 정하면 나머지는 내가 차근차근 안내할게.", "You feel like getting out and doing something! Pick an activity and I’ll help with the rest."),
        "new": ("기분을 바꿀 계기가 필요하구나! 해 보고 싶은 것부터 하나씩 짚어 보자.", "You’re ready for a change! Let’s start with one thing you’d like to try."),
        "other": ("이야기해 줘서 고마워! 오늘 여행에서 가장 중요한 것부터 같이 정리해 보자.", "Thanks for telling me! Let’s work out what matters most to you today."),
        "invite": ("먼저 {activity}자!", "Here’s where I’d start. {activity}."),
    },
    "min": {
        "name": "Min (민)",
        "style": "Calm, kind and reassuring. Acknowledge the feeling, offer warm encouragement and imagine the outing together.",
        "rest": ("많이 지쳤나 봐. 잠시 발걸음을 멈추고 편안한 풍경을 바라보는 하루를 함께 떠올려 보자.", "It sounds like a tiring day. Imagine finding a comfortable spot together and taking in the view for a while."),
        "active": ("그 기운이 반갑네. 기분 좋은 발걸음으로 함께 나서는 장면이 떠올라.", "It’s nice to hear that energy. I can picture us stepping out with a spring in our stride."),
        "new": ("변화를 바라는 마음이 느껴져. 처음 보는 풍경 앞에 나란히 서 있는 모습을 떠올려 볼까?", "I hear that wish for a change. Shall we imagine coming across a view that’s new to us both?"),
        "other": ("편하게 이야기해 줘서 고마워. 오늘 네 속도로 즐길 만한 하루를 함께 그려 보자.", "Thanks for sharing that with me. Let’s picture a day you can enjoy at your own pace."),
        "invite": ("함께 {activity}는 건 어때? 마음에 들면 조금 더 머물러도 좋아.", "Picture us starting here together. {activity}."),
    },
}


def empathy(avatar, mood, tags, lang):
    cue = next((tag for tag in ("rest","new","active") if tag in tags), "other")
    return f'“{mood}” ' + VOICES[avatar][cue][lang == "en"]
