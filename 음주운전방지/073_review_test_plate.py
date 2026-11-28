# 073 · 테스트용1의 타깃 번호판과 좌우 상단 HUD를 다시 검수합니다.
# 원본에서 지정한 번호판 테두리를 따라가 글자 줄을 펴고 한국어 OCR 결과를 비교합니다.
# 서로 다른 원본 화면만 합의에 사용합니다. 결과 JSON과 두 MP4를 새 폴더에 저장합니다.
import argparse
from collections import Counter
from importlib import import_module
from pathlib import Path
import re

import cv2
import numpy as np

from redbox_vehicle_info import PLATE, PLATE_CHARACTERS, VehicleInfo, WindowsOCR

review = import_module("072_review_target_videos")
ROOT = review.ROOT
NAME = "테스트용1"
VIDEO = ROOT / "videos" / (NAME + ".mp4")
START = 886
# F886에서 원본을 열어 지정한 네 모서리입니다. 글자나 번호를 입력값으로 사용하지 않습니다.
SEED = [[250, 542], [287.5, 542.4], [286.5, 560.6], [249, 560.4]]
PLANE = np.float32([[0, 0], [224, 0], [224, 76], [0, 76]])


def save_image(path, image):
    cv2.imencode(path.suffix, image)[1].tofile(path)


def sample_plates(tracks, clock):
    capture = cv2.VideoCapture(str(VIDEO))
    capture.set(cv2.CAP_PROP_POS_FRAMES, START - 1)
    quad = np.float32(SEED)
    previous = None
    try:
        for number in range(START, len(tracks)+1):
            row = tracks[number-1]
            if row["seconds"] > 32.5:
                break
            ok, frame = capture.read()
            if not ok:
                raise OSError(number)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if previous is not None:
                points = quad.reshape(-1, 1, 2)
                options = dict(winSize=(19,19), maxLevel=3)
                next_points, valid, _ = cv2.calcOpticalFlowPyrLK(previous, gray, points, None, **options)
                back, returned, _ = cv2.calcOpticalFlowPyrLK(gray, previous, next_points, None, **options)
                if not (valid.all() and returned.all()) or np.max(np.linalg.norm(back-points,axis=2)) >= 2:
                    raise ValueError(f"F{number} 번호판 테두리 재지정 필요")
                quad = next_points[:,0,:]
            previous = gray
            car = row["car"]
            if not car or car["id"] != tracks[START-1]["car"]["id"]:
                raise ValueError(f"F{number} 추적 공백")
            x,y,X,Y = car["box"]
            if not np.all((quad >= [x,y]) & (quad <= [X,Y])):
                raise ValueError(f"F{number} 선택 차량 밖 번호판")
            if clock[number-1]["duplicate"]:
                continue
            transform = cv2.getPerspectiveTransform(quad, PLANE)
            plane = cv2.warpPerspective(gray, transform, (225,77), flags=cv2.INTER_CUBIC)
            corner = quad.min(0).astype(int)
            right, bottom = np.ceil(quad.max(0)).astype(int)
            native = frame[corner[1]:bottom+1,corner[0]:right+1].copy()
            yield number, row, quad.copy(), plane, native
    finally:
        capture.release()


def stretch(image):
    lo, hi = np.percentile(image, [3,91])
    return np.clip((image.astype(float)-lo)*215/max(1,hi-lo)+25,0,255).astype(np.uint8)


def read_field(reader, windows, image, allow, method):
    normalized = stretch(image)
    if method == "wide_sharp":
        normalized = cv2.addWeighted(normalized,1.8,cv2.GaussianBlur(normalized,(0,0),2),-.8,0)
        normalized = cv2.resize(normalized,None,fx=1.65,fy=1,interpolation=cv2.INTER_CUBIC)
    padded = cv2.copyMakeBorder(normalized,4,4,5,5,cv2.BORDER_CONSTANT,value=240)
    words = reader.recognize(padded, allowlist=allow)
    small = cv2.resize(padded,None,fx=.5,fy=.5,interpolation=cv2.INTER_AREA)
    return dict(method=method,size=list(padded.shape[::-1]),windows=windows.read(small),
                easy=[dict(text=t,confidence=round(float(conf),4)) for _,t,conf in words])


def strings(result):
    return [result["windows"]] + [word["text"] for word in result["easy"] if word["confidence"]>=.24]


def valid_plate(text):
    match = PLATE.fullmatch(re.sub(r"\s+","",text))
    if match and all(c in PLATE_CHARACTERS for c in match[0]):
        return match[0]
    return None


def summarize(observations):
    # 같은 원본을 두 가지 전처리로 읽어도 한 후보에는 최대 한 표만 줍니다.
    patterns = {"prefix": r"[0-9]{2,3}", "hangul": f"[{PLATE_CHARACTERS[10:]}]", "suffix": r"[0-9]{4}"}
    counts = {key: Counter() for key in (*patterns, "full")}
    for observation in observations:
        parts = {}
        for key, pattern in patterns.items():
            candidates = {
                text.strip() for variant in observation["reads"][key] for text in strings(variant)
                if re.fullmatch(pattern, text.strip())
            }
            parts[key] = sorted(candidates)
            counts[key].update(parts[key])
        observation["part_candidates"] = parts
        counts["full"].update(observation["full_matches"])
    return counts


def inspect(out, baseline):
    if review.video_digest(VIDEO)!=review.SOURCE_SHA[1]:
        raise ValueError("번호판을 지정한 원본과 다릅니다.")
    reader, status = review.app.ocr()
    if reader is None:
        raise RuntimeError(status)
    windows = WindowsOCR()
    consensus = VehicleInfo()
    tracks = review.read(baseline/(NAME+"_추적.json"))
    clock = review.read(baseline/(NAME+"_시계.json"))
    old = {r["frame"]:r for r in review.read(baseline/(NAME+"_번호판영역.json"))}
    timeline = review.read(baseline/(NAME+"_분석.json"))
    observed, panels, aligned = [], [], []
    confirmed = first = None
    previous_baseline = -10
    best_score = -1
    try:
        for f,row,quad,plane,native in sample_plates(tracks,clock):
            # 기존 실험의 2프레임 간격 표본도 구분해서 같은 17장을 따로 대조할 수 있게 합니다.
            baseline_sample = f - previous_baseline >= 2
            if baseline_sample:
                previous_baseline = f
            # 같은 차종이라도 번호판 배치가 다릅니다. 분할 영역은 이 원본에서 확인한 글자 사이입니다.
            fields = {"line": (plane[14:64,2:216], PLATE_CHARACTERS),
                      "prefix": (plane[16:64,:62], "0123456789"),
                      "hangul": (plane[23:66,61:96], PLATE_CHARACTERS[10:]),
                      "suffix": (plane[13:64,94:217], "0123456789")}
            reads = {key:[read_field(reader, windows, img, allow, method)
                          for method in ("contrast","wide_sharp")] for key,(img,allow) in fields.items()}
            # 작은 한글을 숫자 높이에 맞춰 붙인 줄도 독립 OCR로 읽습니다. 글자를 합성하지 않습니다.
            glyph = cv2.resize(plane[28:65,62:95],(46,48),interpolation=cv2.INTER_CUBIC)
            gap = np.full((48,4),int(np.percentile(plane,85)),np.uint8)
            equalized = np.hstack([plane[17:65,2:63],gap,glyph,gap,plane[17:65,96:217]])
            reads["equal_height"] = [read_field(reader,windows,equalized,PLATE_CHARACTERS,"contrast")]
            unrestricted = reader.recognize(stretch(fields["hangul"][0]))
            matches = {plate:True for key in ("line","equal_height") for variant in reads[key]
                       for token in strings(variant) if (plate:=valid_plate(token))}
            consensus.ocr_frames = (consensus.ocr_frames+[dict(frame=f,matches=matches)])[-12:]
            if not confirmed:
                confirmed = consensus.plate_candidate()
                if confirmed: first = f
            a = np.array(native.shape[:2][::-1])
            contrast = stretch(plane[18:62,4:215])
            sharpness = float(cv2.Laplacian(contrast,cv2.CV_32F).var())
            score = sharpness*float(np.linalg.norm(quad[1]-quad[0]))
            if score>best_score:
                best_score = score
                best = f
                save_image(out/"선명한_원본_번호판.png",native)
                save_image(out/"선명한_번호판_확대.png",cv2.resize(native,None,fx=6,fy=6,interpolation=cv2.INTER_NEAREST))
            aligned.append(plane)
            tile = cv2.cvtColor(plane,cv2.COLOR_GRAY2BGR)
            tile = cv2.copyMakeBorder(tile,21,1,1,1,cv2.BORDER_CONSTANT)
            cv2.putText(tile,f"F{f}   {row['seconds']:.2f}s",(3,15),0,.48,(255,255,255),1)
            panels.append(tile)
            observed.append(dict(frame=f,seconds=row["seconds"],baseline_sample=baseline_sample,
                                 track_id=row["car"]["id"],quad=quad.tolist(),
                                 width_px=round(float(np.linalg.norm(quad[1]-quad[0])),2),
                                 height_px=round(float(np.linalg.norm(quad[3]-quad[0])),2),
                                 top_angle_deg=round(float(np.degrees(np.arctan2(*(quad[1]-quad[0])[::-1]))),2),
                                 native_crop=a.tolist(),original_detail=old.get(f),reads=reads,
                                 hangul_unrestricted=[(t,round(float(c),4)) for _,t,c in unrestricted],
                                 full_matches=list(matches),confirmed=confirmed))
        # 정렬 평균은 읽기 보조용 한 장입니다. 원본 프레임별 합의 횟수에 더하지 않습니다.
        ref = aligned[-1][15:65,4:215].astype(np.float32)
        stack = []
        for img in aligned:
            part = img[15:65,4:215]
            try:
                score, affine = cv2.findTransformECC(ref,part.astype(np.float32),np.eye(2,3,dtype=np.float32),
                    cv2.MOTION_AFFINE,(cv2.TERM_CRITERIA_COUNT|cv2.TERM_CRITERIA_EPS,60,.00001))
            except cv2.error:
                continue
            if score>.85:
                stack.append(cv2.warpAffine(part,affine,(ref.shape[1],ref.shape[0]),flags=cv2.INTER_CUBIC|cv2.WARP_INVERSE_MAP))
        combined = []
        if stack:
            median=np.median(stack,axis=0).astype(np.uint8)
            save_image(out/"다중프레임_정렬중앙값.png",stretch(median))
            combined=[read_field(reader,windows,median,PLATE_CHARACTERS,m) for m in ("contrast","wide_sharp")]
    finally:
        windows.close()
    while len(panels)%3: panels.append(np.zeros_like(panels[0]))
    save_image(out/"독립표본_번호판.png",np.vstack([np.hstack(panels[i:i+3]) for i in range(0,len(panels),3)]))
    counts = summarize(observed)
    evidence = dict(video=VIDEO.name,source_sha256=timeline["source_sha256"],track_id=tracks[START-1]["car"]["id"],
                    baseline_frames=[o["frame"] for o in observed if o["baseline_sample"]],
                    roi_source="manual_plate_corners_at_F886_then_forward_backward_optical_flow",
                    votes="한 프레임당 같은 번호 1표, 최근 최대 12개 중 최소 8개 관측, 같은 전체 번호 최소 4표 및 차점 2배",
                    confirmed=confirmed,first_display_frame=first,
                    first_display_s=timeline["frames"][first-1]["seconds"] if first else None,
                    sharpest_frame=best,counts=counts,aligned_frames=len(stack),combined_diagnostic=combined,observations=observed)
    review.save(out/"번호판_재판독.json", evidence)
    for row in timeline["frames"]:
        info=row["vehicle_info"]
        value=confirmed if first and row["frame"]>=first else None
        info.update(plate=value,ocr_candidate=value,plate_source="ocr_candidate" if value else None)
    timeline["plate_review"]={key:evidence[key] for key in ("confirmed","first_display_frame","first_display_s","track_id")}
    review.save(out/(NAME+"_분석.json"),timeline)
    print("독립 표본",len(observed),"최초 확정",first,"후보",counts,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--baseline",type=Path,default=review.OUT)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    inspect(args.out,args.baseline)
    review.render(1,args.out)

