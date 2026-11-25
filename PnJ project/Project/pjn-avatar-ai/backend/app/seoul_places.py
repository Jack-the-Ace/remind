"""Editorial experience tags describe the proposed activity, not live conditions."""
import json
from pathlib import Path
from .seoul_collection import ADDITIONS

PARKS = "https://english.seoul.go.kr/service/amusement/parks/"
MARKETS = "https://english.visitseoul.net/hallyu/TraditionalMarketShopping/ENN026629"
PALACE = "https://royal.cha.go.kr/ENG/contents/E104010000.do"
PHOTOS = json.loads(Path(__file__).with_name("place_photos.json").read_text(encoding="utf-8"))


def place(name, district, theme, tags, first, second, partners, source=PARKS):
    return dict(name=name, district=district, theme=theme, tags=set(tags.split()),
                activities=[first, second], partners=partners.split(), source=source)


PLACES = {
    "pureun": place("푸른수목원|Pureun Arboretum", "구로구|Guro-gu",
        "나무 사이에서 생각을 비우는 오후|A slow afternoon among the trees",
        "nature rest quiet solo flex outdoor budget",
        "마음에 드는 나무를 골라 잠시 바라보기|Pause by a tree that catches your eye",
        "잎의 색과 모양을 여행 노트에 남기기|Sketch the colour and shape of a leaf",
        "boramae botanic seonyudo"),
    "boramae": place("보라매공원|Boramae Park", "동작구|Dongjak-gu",
        "연못가에 머무는 작은 소풍|A picnic by the pond",
        "nature rest quiet familiar flex social outdoor budget",
        "연못가에서 물에 비치는 풍경 감상하기|Watch the reflections by the pond",
        "잠시 쉬면서 마음에 든 풍경을 기록하기|Take a break and note a favourite view",
        "pureun seonyudo botanic"),
    "botanic": place("서울식물원|Seoul Botanic Park", "강서구|Gangseo-gu",
        "온실에서 만나는 낯선 식물|A greenhouse full of unfamiliar plants",
        "nature rest quiet new indoor planned solo paid",
        "온실에서 낯선 잎 모양 찾아보기|Look for unfamiliar leaf shapes in the greenhouse",
        "마음에 든 식물 하나를 골라 관찰하기|Spend time observing one favourite plant",
        "pureun boramae seonyudo"),
    "seonyudo": place("선유도공원|Seonyudo Park", "영등포구|Yeongdeungpo-gu",
        "옛 정수장에 자란 수생정원 산책|Walk a water garden in a former filtration plant",
        "nature culture quiet rest walk new solo outdoor",
        "옛 정수 시설을 따라 수생식물 살펴보기|Follow the old waterworks and look for aquatic plants",
        "물과 콘크리트가 만나는 풍경 사진 찍기|Photograph the meeting of water and concrete",
        "boramae pureun botanic",
        "https://english.visitkorea.or.kr/svc/contents/contentsView.do?menuSn=351&vcontsId=175826"),
    "forest": place("서울숲|Seoul Forest", "성동구|Seongdong-gu",
        "숲길을 따라 걷는 초록 산책|A green walking break in Seoul Forest",
        "nature active walk quiet familiar flex outdoor budget",
        "나무 그늘을 따라 산책하기|Walk along a tree-lined path",
        "걸음을 멈추고 숲의 소리 들어보기|Pause and listen to the sounds of the forest",
        "seonyudo boramae pureun"),
    "gwangjang": place("광장시장|Gwangjang Market", "종로구|Jongno-gu",
        "먹거리 골목에서 새로운 맛 찾기|Discover a new flavour in the market",
        "city busy social active food shopping walk new flex",
        "먹거리 골목에서 먹어 보고 싶은 메뉴 고르기|Browse the food stalls and pick a dish",
        "직물 가게의 색과 무늬 구경하기|Look at the colours and patterns in the fabric stalls",
        "namdaemun insadong deoksu", MARKETS),
    "namdaemun": place("남대문시장|Namdaemun Market", "중구|Jung-gu",
        "시장 골목에서 취향에 맞는 물건 찾기|Browse the lanes for a personal find",
        "city busy social active food shopping walk familiar planned",
        "상점가에서 마음에 드는 소품 찾아보기|Browse the shops for a keepsake",
        "골목을 한 곳 골라 간식 구경하기|Explore one lane for a snack",
        "deoksu gwangjang", MARKETS),
    "deoksu": place("덕수궁|Deoksugung Palace", "중구|Jung-gu",
        "궁궐의 건축을 읽는 역사 산책|Read a palace through its architecture",
        "culture history city active walk new planned outdoor paid",
        "중화전 앞에서 지붕과 처마 살펴보기|Look at the roof and eaves of Junghwajeon",
        "석조전 외관과 전통 전각 비교하기|Compare Seokjojeon’s exterior with the traditional halls",
        "namdaemun gwangjang", PALACE),
    "insadong": place("인사동길|Insadong-gil", "종로구|Jongno-gu",
        "공예품을 찾아 걷는 인사동 나들이|A craft-shopping walk in Insa-dong",
        "city culture history shopping walk active busy new flex",
        "쌈지길에서 공예품의 재료와 무늬 살펴보기|Browse craft materials and patterns at Ssamzigil",
        "인사동길에서 마음에 드는 기념품 골라보기|Look for a souvenir along Insadong-gil",
        "gwangjang deoksu namdaemun",
        "https://english.visitkorea.or.kr/svc/contents/contentsView.do?menuSn=&vcontsId=87748"),
}


PLACES.update(ADDITIONS)

DISTRICTS = {
    "도심": "중구 종로구 용산구", "서북": "마포구 은평구 서대문구",
    "서남": "구로구 동작구 강서구 영등포구 관악구 양천구",
    "동북": "성동구 노원구 강북구 광진구", "동남": "송파구 강남구 서초구",
}
ZONES = {district: zone for zone, districts in DISTRICTS.items() for district in districts.split()}
ORIGINAL_ADDRESSES = {
    "pureun":"서해안로 2117", "boramae":"여의대방로20길 33", "botanic":"마곡동로 161",
    "seonyudo":"선유로 343", "forest":"뚝섬로 273", "gwangjang":"창경궁로 88",
    "namdaemun":"남대문시장4길 21", "deoksu":"세종대로 99", "insadong":"인사동길 일대",
}
for key, site in PLACES.items():
    site["zone"] = ZONES[site["district"].split("|")[0]]
    site.setdefault("address", ORIGINAL_ADDRESSES.get(key))
    site.setdefault("fee", "paid" if "paid" in site["tags"] else "unknown")
    if key in {"nationalmuseum", "baekje", "seosomun", "buksema", "namsema"}:
        site["tags"].add("museum")
    if key in {"gwangjang", "namdaemun"}:
        site["tags"].add("market")


def local(value, lang):
    return value.split("|")[lang == "en"]


COORDINATES = json.loads(Path(__file__).with_name("place_coordinates.json").read_text(encoding="utf-8"))


# Additional site-specific pointers corroborated by the linked visitor pages.
ACCESS = {
    "namsema": "사당역에서 접근할 수 있어요. 미술관에는 주차장이 없어 인근 주차장과 계단 이용 방법을 미리 확인하세요.|Use Sadang Station or check a nearby car park. The museum has no on-site parking; check stair access before visiting.",
    "buksema": "하계역과 중계역 중 편한 쪽을 골라 공원에서 미술관 입구로 이어지는 길을 확인하세요.|Compare Hagye and Junggye stations and check the entrance path through the park.",
    "seosomun": "시청역에서 덕수궁길로 이어지는 길을 확인하세요. 미술관 주차 공간은 제한적이에요.|Check the approach from City Hall Station along Deoksugung-gil. The museum has limited parking.",
    "kstar": "압구정로데오역에서 출발할 수 있어요. 거리 자체에는 주차장이 없어요.|Start near Apgujeong Rodeo Station. The street has no dedicated car park.",
    "ktown": "삼성역에서 코엑스 내부로 이어지는 길과 매장 층을 확인하세요.|Check the indoor route from Samseong Station and the shop floor before setting off.",
    "hikr": "종각역에서 청계천 쪽으로 접근할 수 있어요. 차로 간다면 주차장 이용 조건을 확인하세요.|Approach from Jonggak Station towards Cheonggyecheon. Check parking restrictions if driving.",
    "hongdae": "홍대입구역에서 레드로드 R2로 이어지는 보행 구간을 확인하세요.|Check the walking route from Hongik University Station to Red Road R2.",
    "changdeok": "안국역에서 돈화문까지의 길을 확인하세요. 궁에는 관람객 주차장이 없어요.|Check the route from Anguk Station to Donhwamun Gate. The palace has no visitor car park.",
    "naksan": "성곽을 따라 오르막이 있어요. 돌아올 길과 계단 구간을 먼저 살펴보세요.|The wall path climbs. Check the stairs and your return route before setting off.",
    "mangwon": "망원역에서 시장 입구까지 걷는 구간을 확인하세요.|Check the walk from Mangwon Station to the market entrance.",
}
DEFAULT_ACCESS = "입구와 가까운 정류장, 주차 후 걸어야 하는 구간을 확인하세요.|Check the nearest transit stop and the walk from the car park to your chosen entrance."


def describe(key, lang):
    p = PLACES[key]
    return dict(id=key, name=local(p["name"], lang), region=local(p["district"], lang),
                activities=[local(a, lang) for a in p["activities"]], photo=PHOTOS.get(key),
                accessNote=local(ACCESS.get(key, DEFAULT_ACCESS), lang),
                source=p["source"], verification="official-place-and-district",
                checkedOn="2026-11-25", address=p["district"].split("|")[0]+" "+p["address"],
                zone=p["zone"], fee=p["fee"], setting=next((s for s in ("indoor","outdoor") if s in p["tags"]), "mixed"),
                walking="extended" if p["tags"] & {"active","walk"} else "self-paced",
                timeGuide=("programme" if "performance" in p["tags"] else "walk" if "walk" in p["tags"] else "browse"),
                coordinates=COORDINATES.get(key), accessStatus="confirm-parking-transit-and-step-free-route",
                operatingStatus="check-for-visit-date")

