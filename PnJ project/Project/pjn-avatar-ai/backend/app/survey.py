"""Original PnJ questionnaire. Each option adds one vote to its named tag."""
from collections import Counter
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictInt

VERSION = "pnj-travel-1"
# id, dimension, Korean / English prompt, choices (Korean / English / tag).
ROWS = [
 ("s1", "company", "첫날 저녁은 어떻게 보내고 싶나요?", "How would you like to spend your first evening?", "혼자 산책하고 싶어요.|I'd like to go for a walk on my own.|solo", "누군가와 함께 저녁을 먹고 싶어요.|I'd like to have dinner with someone.|social"),
 ("s2", "novelty", "단골가게가 있는 동네에서 하루의 시간이 생겼다면?", "If you had a day in the neighborhood of your favorite shop, what would you do?", "좋아하는 단골가게에 다시 들를래요.|I'd go back to my favorite shop.|familiar", "아직 가보지 않은 골목을 둘러볼래요.|I'd explore a street I haven't visited yet.|new"),
 ("s3", "pace", "오후에 한 시간이 비었어요. 어떻게 보내고 싶나요?", "You have a free hour in the afternoon. How would you spend it?", "편한 자리에 앉아 풍경을 보고 싶어요.|I'd sit somewhere comfortable and enjoy the view.|rest", "걸어서 동네를 한 바퀴 돌아보고 싶어요.|I'd take a walk around the neighborhood.|active"),
 ("s4", "setting", "여행지에서 창가에 앉는다면 어떤 풍경을 보고 싶나요?", "What would you like to see from a window on your trip?", "나무가 우거진 숲과 흐르는 물|Woods and a stream|nature", "사람들이 오가는 거리와 광장|Streets and squares full of people|city", "독특한 건물과 야외 미술 작품|Distinctive buildings and outdoor art|culture"),
 ("s5", "plan", "여행을 떠나기 전에 어디까지 정해 두는 편인가요?", "How much do you like to plan before a trip?", "처음 갈 곳만 정하고 나머지는 비워 둬요.|I choose the first stop and leave the rest open.|flex", "주요 장소를 어떤 순서로 갈지 정해 둬요.|I plan the order of the main stops.|planned"),
 ("s6", "company", "공방에서 무언가를 배운다면 어떤 수업이 더 끌리나요?", "What kind of class would you prefer at a craft studio?", "내 속도에 맞춰 혼자 만드는 수업|An individual class where I can work at my own pace|solo", "다른 사람들과 함께 만드는 수업|A class where I make things with other people|social"),
 ("s7", "novelty", "여행지 시장에서 점심을 먹는다면 어떤 메뉴를 고를까요?", "What would you order for lunch at a market on your trip?", "평소에 즐겨 먹는 음식|Something I already enjoy eating|familiar", "아직 한 번도 먹어 보지 않은 음식|Something I've never tried before|new"),
 ("s8", "pace", "전망 좋은 곳에 도착했어요. 이제 뭘 하고 싶나요?", "You've reached a scenic viewpoint. What would you like to do next?", "벤치에 앉아 경치를 천천히 즐길래요.|I'd sit on a bench and take in the view.|rest", "근처 둘레길을 따라 조금 더 걸을래요.|I'd walk a little farther along a nearby trail.|active"),
 ("s9", "setting", "여행지에서 사진을 한 장만 찍는다면 무엇을 담고 싶나요?", "If you could take just one travel photo, what would you photograph?", "그 계절에 볼 수 있는 꽃이나 나무|Flowers or trees in season|nature", "동네 사람들의 일상|Everyday life in the neighborhood|city", "오래된 건물의 모습|A historic building|culture"),
 ("s10", "plan", "이동 중에 친구가 다른 곳에도 들르자고 하면 어떻게 할까요?", "On the way, a friend suggests an extra stop. How would you decide?", "그때 가고 싶은 마음이 들면 들러요.|I'd go if I felt like it at the time.|flex", "남은 일정에 여유가 있는지 먼저 살펴봐요.|I'd check how much time was left in our plans.|planned"),
 ("s11", "company", "처음 온 도시의 이야기를 어떤 방식으로 듣고 싶나요?", "How would you like to hear the stories of a city you're visiting for the first time?", "이어폰으로 오디오 가이드를 들으며 혼자 둘러봐요.|I'd explore on my own with an audio guide.|solo", "동네 사람과 이야기를 나누며 알아가요.|I'd get to know the place by talking with a local.|social"),
 ("s12", "novelty", "여행 기념품을 하나 고른다면 어느 쪽에 더 마음이 가나요?", "Which souvenir would you be more drawn to?", "평소 모으던 기념품을 하나 더 고를래요.|I'd add another piece to my usual collection.|familiar", "이곳에서 처음 본 공예품을 고를래요.|I'd choose a local craft I'd never seen before.|new"),
 ("s13", "pace", "여행 둘째 날 아침은 어떻게 시작하고 싶나요?", "How would you like to start the second morning of your trip?", "느긋하게 차 한 잔을 마실래요.|I'd take my time over a cup of tea.|rest", "일찍 나가 자전거를 탈래요.|I'd get out early for a bike ride.|active"),
 ("s14", "setting", "비가 그치고 날이 개면 어디로 가고 싶나요?", "Where would you like to go when the rain clears?", "강변에 있는 정원|A riverside garden|nature", "골목에 들어선 동네 시장|A neighborhood street market|city", "작은 전시장|A small gallery|culture"),
 ("s15", "plan", "여행 전에 인기 있는 체험을 발견하면 어떻게 할까요?", "Before a trip, you spot a popular activity. What would you do?", "현장에 가서 자리가 있으면 참여해요.|I'd decide on the day if there's a spot available.|flex", "원하는 시간에 참여할 수 있게 미리 예약해요.|I'd reserve a time slot in advance.|planned"),
 ("s16", "company", "여행을 마치며 좋았던 순간을 어떻게 돌아보고 싶나요?", "How would you like to look back on the highlights of a trip?", "혼자 여행 기록을 정리하고 싶어요.|I'd write down my memories on my own.|solo", "함께 간 사람과 서로 좋았던 순간을 나누고 싶어요.|I'd share favorite moments with a travel companion.|social"),
 ("s17", "novelty", "다음 여행지를 고른다면 어디로 가고 싶나요?", "Where would you like to go on your next trip?", "좋았던 곳을 다른 계절에 다시 찾고 싶어요.|I'd revisit a place I loved in a different season.|familiar", "아직 가보지 않은 지역을 여행하고 싶어요.|I'd visit somewhere I've never been.|new"),
 ("s18", "pace", "하루 일정을 마치고 기운이 조금 남았어요. 뭘 하고 싶나요?", "You have a little energy left after a day out. What would you like to do?", "숙소에서 편하게 쉴래요.|I'd relax back at my accommodation.|rest", "가볍게 산책하며 야경을 볼래요.|I'd take a short walk to see the night views.|active"),
 ("s19", "setting", "반나절 동안 한 곳을 둘러볼 수 있다면 어디를 고를까요?", "If you had half a day to explore, which outing would you choose?", "수목원에서 나무와 꽃 구경하기|See trees and flowers at an arboretum|nature", "시내를 돌며 거리 풍경 구경하기|Tour the city and take in its street scenes|city", "박물관에서 전시 관람하기|Explore the exhibits at a museum|culture"),
 ("s20", "plan", "집으로 돌아가는 날 오전에는 어떻게 일정을 잡고 싶나요?", "How would you plan the morning of your trip home?", "따로 일정을 잡지 않고 여유롭게 보내요.|I'd leave the morning open.|flex", "출발 전에 마지막으로 들를 곳을 정해 둬요.|I'd choose one final stop before leaving.|planned"),
]
QUESTIONS = [
    dict(id=q, dimension=d, prompt=[ko,en], choices=[x.split("|") for x in options])
    for q,d,ko,en,*options in ROWS
]

class Survey(BaseModel):
    version: str
    answers: dict[str, Annotated[StrictInt, Field(ge=0, le=2)]]

def votes(submission: Survey):
    if submission.version != VERSION or set(submission.answers) != {q["id"] for q in QUESTIONS}:
        raise HTTPException(422, "SURVEY_INCOMPLETE")
    counts = {}
    for q in QUESTIONS:
        index = submission.answers[q["id"]]
        if index >= len(q["choices"]):
            raise HTTPException(422, "INVALID_CHOICE")
        counts.setdefault(q["dimension"], Counter())[q["choices"][index][2]] += 1
    return counts

def strengths(raw):
    if not raw:
        return {}
    try:
        counts = votes(Survey.model_validate(raw))
    except (ValueError, HTTPException):
        return {}
    return {q['dimension']: {c[2]: counts[q['dimension']][c[2]] for c in q['choices']} for q in QUESTIONS}

def score(submission: Survey):
    counts = votes(submission)
    # Retain all joint winners, including balanced preferences.
    return {d: [tag for tag,n in votes.items() if n == max(votes.values())] for d,votes in counts.items()}
