# 068  회색 승용차를 추적하며 사용자가 지정한 예측을 영상 시각에 맞춰 보여줍니다.
# 입력은 원본 영상, 006의 추적 좌표, 원본을 보고 작성한 관찰 기록입니다.
# 041의 HUD를 원본 크기에 합성하고 067로 H.264를 저장한 뒤 모든 프레임을 다시 읽습니다.
# 다음 단계에서는 MP4만 열어 재생하거나 JSON에서 시연 근거와 자동 추적을 확인합니다.
import argparse
import hashlib
import json
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image


review = import_module("067_render_driving_review")
mvp = review.mvp
ROOT = Path(__file__).resolve().parent
WORK = ROOT / "output" / "mvp_review_drowsy"
SOURCE = ROOT / "videos" / "졸음운전2.mp4"
SOURCE_HASH = "2a34d5d7b3aa585398dd3744039f40846a0f1503d13fd64dce1dab78476b755c"
NAME = "07_졸음운전_예측.mp4"
INFO = {"color": "회색 계열", "vehicle_type": "승용차", "plate": None, "brand": None}


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def measure_boundary(cap, rows):
    # 첫 프레임에서 차량 바로 오른쪽의 흰 도색을 두 점으로 지정했습니다.
    # 같은 도색을 매 프레임 다시 찾습니다. 분홍 유도선과 앞차 차체는 탐색에서 제외합니다.
    ox, oy = 375, 292
    seed = [657-ox, 604-oy, 733-ox, 677-oy]
    lane = mvp.crossing_module
    boundary = lane.Boundary(seed)
    for row in rows:
        ok, image = cap.read()
        if not ok:
            raise ValueError("경계 관측용 원본 프레임 누락")
        row["seconds"] = lane.source_seconds(cap, row["frame"], cap.get(cv2.CAP_PROP_FPS))
        row["boundary"] = None
        row["lane_observation"] = "tracking_hold" if not row["box"] else "boundary_missing"
        if not row["box"]:
            continue
        x, _, X, Y = row["box"]
        bottom = round(Y-oy)
        road = image[oy:oy+400, ox:ox+640].astype(np.int16)
        green = road[:, :, 1]
        # 흰 도색은 양옆의 아스팔트보다 밝습니다. 원본 화소에서 도색의 양쪽 끝도 측정합니다.
        contrast = green - np.maximum(np.roll(green, 16, axis=1), np.roll(green, -16, axis=1))
        mask = ((contrast >= 13) & (road[:, :, 2]-green < 12)).astype(np.uint8)
        support = boundary.detect(mask, [], row_limits=(bottom+3, min(bottom+88,398)),
                                  min_points=4, min_span=12, corridor=17)
        if support is None:
            continue
        side, distance, status = boundary.classify([(x+X)/2-ox, Y-oy], support, [])
        row["lane_observation"] = status
        row["boundary"] = [[float(np.polyval(boundary.line, y)+ox), float(y+oy)]
                           for y in (support.min(), support.max())]
        # 바닥에 가장 가까운 지지점에서 도색 폭을 구합니다. 도로 원근 때문에 먼 지점은 제외합니다.
        widths = []
        for y in support[support <= support.min()+12]:
            col = round(np.polyval(boundary.line, y))
            white = np.flatnonzero(mask[int(y)])
            for part in np.split(white, np.flatnonzero(np.diff(white)>1)+1):
                if len(part) and 2 <= len(part) <= 24 and part[0]-2 <= col <= part[-1]+2:
                    widths.append(len(part))
        row["paint_half_width"] = float(np.median(widths)/2) if widths else 0.
        row["distance_px"] = distance
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)


def hud(image, row, prediction, events, *, counts=None):
    # 예측은 차량 상태이고, TOTAL과 플로팅은 공통 집계기가 만든 사건 목록에서 읽습니다.
    state = "선택 차량 추적 중" if row["box"] else "추적 보류"
    data = dict(seconds=row["time"], box=row["box"], vehicle_info=INFO, boundary=None,
                prediction=prediction, event_counts=counts if counts is not None else dict(review.Counter(e["label"] for e in events)),
                status_text=state + " · 수동 예측 시연")
    if row.get("lane_readability"):
        data["lane_readability"]=row["lane_readability"]
    layer = mvp.draw_hud(image, data, "recorded", overlay_only=True)
    mvp.draw_event_floats(layer, events, row["seconds"])
    # 도로 영상은 그대로 두고, 투명한 HUD만 원본 해상도로 키웁니다.
    height, width = image.shape[:2]
    overlay = np.asarray(layer.resize((width, height), Image.Resampling.BILINEAR))
    y, x = np.nonzero(overlay[:, :, 3])
    alpha = overlay[y, x, 3, None].astype(np.uint16)
    rgb = overlay[y, x, 2::-1].astype(np.uint16)
    image[y, x] = (rgb * alpha + image[y, x].astype(np.uint16) * (255 - alpha) + 127) // 255
    return image


def verify_prediction(path, reference, region):
    # 저장된 글자 부분을 두 문구의 렌더링과 비교해 전환이 한 프레임 밀려도 잡아냅니다.
    cap = cv2.VideoCapture(str(path))
    results = []
    try:
        for frame, (wanted, other) in reference.items():
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame - 1)
            ok, image = cap.read()
            if not ok:
                raise ValueError(f"F{frame} 탐색 실패")
            actual = image[region].astype(np.int16)
            mask = np.max(np.abs(wanted - other), axis=2) > 60
            correct = float(np.abs(actual[mask] - wanted[mask]).mean())
            opposite = float(np.abs(actual[mask] - other[mask]).mean())
            if not correct + 10 < opposite:
                raise ValueError(f"F{frame} 예측 문구 확인 실패")
            results.append(dict(frame=frame, expected_mae=round(correct, 2),
                                opposite_mae=round(opposite, 2)))
    finally:
        cap.release()
    return results


def verify_event_hud(video, rows, events, onset, fps):
    # 각 사건 직전·직후와 겹침·소멸을 저장 MP4에서 탐색합니다.
    cap, source = cv2.VideoCapture(str(video)), cv2.VideoCapture(str(SOURCE))
    checks = []
    frames = {1, len(rows)}
    for event in events:
        frames.update(event["frame"]+d for d in (-1, 0, 1, round(fps), round(1.5*fps), round(2*fps)-1, round(2*fps)))
    try:
        for f in sorted(n for n in frames if 1 <= n <= len(rows)):
            cap.set(1, f-1)
            source.set(1, f-1)
            ok, actual = cap.read()
            src_ok, raw = source.read()
            if not ok or not src_ok:
                raise ValueError(f"F{f} 탐색 실패")
            row = rows[f-1]
            arrived = [e for e in events if e["frame"] <= f]
            visible = [e for e in arrived if round(row["seconds"]-e["time_s"],9)<2]
            assert [e["incident_id"] for e in visible]==row["floating_ids"]
            counts = dict(review.Counter(e["label"] for e in arrived))
            assert counts==row["event_counts"]
            pred = "졸음운전" if f >= onset else None
            wanted = hud(raw.copy(),row,pred,arrived)
            # TOTAL 숫자를 하나 바꾼 화면과 비교하면 7회와 8회도 구분할 수 있습니다.
            wrong = dict(counts)
            wrong["차선침범"] = counts.get("차선침범",0)-1 if counts else 1
            opposite = hud(raw.copy(),row,pred,arrived,counts=wrong)
            def check_difference(alternate, region):
                target = wanted[region].astype(np.int16)
                alt = alternate[region].astype(np.int16)
                pixel = np.max(np.abs(target-alt),axis=2)>38
                if not pixel.any():
                    return None
                saved = actual[region].astype(np.int16)
                a, b = (float(np.abs(saved[pixel]-ref[pixel]).mean()) for ref in (target,alt))
                if a+5 >= b:
                    raise ValueError(f"F{f} HUD 비교 실패 {a:.1f}/{b:.1f}")
                return round(b-a,2)
            total_margin = check_difference(opposite,np.s_[:145,raw.shape[1]//2:])
            if total_margin is None:
                raise ValueError(f"F{f} TOTAL 비교 화소 없음")
            margins=[]
            area=np.s_[raw.shape[0]//3:,:]
            for event in visible:
                # 나머지 줄은 그대로 두고 이 글자 하나만 뺀 화면과 대조합니다.
                alt = hud(raw.copy(),row,pred,[e for e in arrived if e is not event],counts=counts)
                margins.append(check_difference(alt,area))
            checks.append(dict(frame=f,counts=counts,float_ids=row["floating_ids"],
                               total_pixel_margin=total_margin,float_pixel_margins=margins,
                               lower_frame_mae=round(float(cv2.absdiff(actual[area],wanted[area]).mean()),3)))
    finally:
        cap.release()
        source.release()
    return checks


def render(tracks, observation, out):
    if (digest(SOURCE) != SOURCE_HASH or tracks["source_sha256"] != SOURCE_HASH
            or observation["video"] != SOURCE.name or tracks["video"] != SOURCE.name):
        raise ValueError("시연 설정과 원본이 다릅니다.")
    mark = observation["manual_prediction"]
    if mark["source"] != "manual_demo":
        raise ValueError("이 설정은 검토한 회색 승용차의 수동 예측 시연용입니다.")
    rows = tracks["rows"]
    pick = tracks["selection"]
    px, py = pick["point_xy"]
    x1, y1, x2, y2 = rows[0]["box"]
    if pick["frame"] != 1 or not (x1 <= px <= x2 and y1 <= py <= y2):
        raise ValueError("첫 프레임에서 지정한 차량과 상자가 다릅니다.")
    proof = out / "검증기록"
    settings = proof / "07_졸음운전_시연설정.json"
    report = proof / "07_졸음운전_검증.json"
    video = out / NAME
    for path in (video, settings, report):
        if path.exists():
            raise FileExistsError(path)
    proof.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(SOURCE))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        size = tuple(int(cap.get(p)) for p in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
        onset = mark["frame"]
        if (not cap.isOpened() or fps != tracks["fps"] or count != len(rows)
                or not 1 < onset <= count or abs(mark["seconds"] - (onset-1)/fps) > 1e-6):
            raise ValueError("영상 시각과 추적 기록을 맞출 수 없습니다.")
        measure_boundary(cap, rows)
        events = mvp.crossing_module.analyze_contact_rows(rows, fps)
        for i, event in enumerate(events):
            event.update(incident_id=f"drowsy-2-{event['frame']}-{i+1}", source_video=SOURCE.name,
                         hud_anchor=mvp.event_position(rows[event["frame"]-1]["box"], *size))
            mvp.set_float_slot(event, events[:i])
        cues = {1, onset-1, onset, 441, 449, count}
        region = np.s_[:round(size[1]*.11), round(size[0]*.67):]
        signatures, reference = [], {}
        # 완성된 MP4를 전부 확인한 뒤에만 최종 이름으로 옮깁니다.
        with TemporaryDirectory(dir=out) as directory:
            draft = Path(directory) / "review.mp4"
            enc = review.writer(draft, fps, size)
            try:
                for frame, row in enumerate(rows, 1):
                    ok, image = cap.read()
                    if not ok or row["frame"] != frame or abs(row["time"] - (frame-1)/fps) > .0001:
                        raise ValueError(f"F{frame} 추적 기록의 시각이 다릅니다.")
                    arrived = [e for e in events if e["frame"] <= frame]
                    row["event_counts"] = dict(review.Counter(e["label"] for e in arrived))
                    row["floating_ids"] = [e["incident_id"] for e in arrived if row["seconds"]-e["time_s"] < 2-1e-8]
                    prediction = "졸음운전" if frame >= onset else None
                    if frame in cues:
                        other = hud(image.copy(), row, None if prediction else "졸음운전", arrived)
                    composite = hud(image, row, prediction, arrived)
                    if frame in cues:
                        reference[frame] = (composite[region].astype(np.int16),
                                            other[region].astype(np.int16))
                    enc.write(composite)
                    signatures.append(review.signature(composite))
                if cap.read()[0]:
                    raise ValueError("추적 기록 뒤에 원본 프레임이 더 있습니다.")
            finally:
                enc.release()
            check = review.verify(draft, signatures, size, fps)
            samples = verify_prediction(draft, reference, region)
            event_checks = verify_event_hud(draft,rows,events,onset,fps)
            draft.rename(video)
    finally:
        cap.release()
    save(settings, dict(source="manual_demo", video=SOURCE.name, original_path=str(SOURCE),
                        source_sha256=SOURCE_HASH, frame_time="(frame - 1) / fps",
                        selection=pick, manual_prediction=mark, prediction_text="예측: 졸음운전",
                        last_frame=count, vehicle_info=INFO, info_source="원본 외관 육안 확인",
                        events=events, counts=rows[-1]["event_counts"], lane_rule_version=mvp.crossing_module.LANE_RULE_VERSION,
                        boundary_source="첫 장에서 선택한 흰 도색을 프레임별로 추적 · 원본 하단 도색 폭 측정",
                        observations={k:v for k,v in observation.items() if k!="count"}, automatic_tracking=tracks["tracking"]))
    save(report, dict(mp4=video.name, mp4_sha256=digest(video), encoded_video=check,
                      prediction_roi_checks=samples, event_pixel_checks=event_checks, frame_base=1, event_count=len(events), events=events,
                      prediction_intervals=[dict(first=1,last=onset-1,text="예측: -"),
                                            dict(first=onset,last=count,text="예측: 졸음운전")],
                      target_verification=tracks["verification"], automatic_track_rows=rows))
    print(f"{video}  |  {count} frames  |  {count/fps:.2f}s  |  F{onset} ({(onset-1)/fps:.2f}s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="검토한 회색 차량 추적과 수동 예측 상태를 MP4에 저장합니다.")
    parser.add_argument("--tracking", type=Path, default=WORK / "tracking" / "track.json")
    parser.add_argument("--observations", type=Path, default=WORK / "visual" / "관찰근거.json")
    parser.add_argument("--out", type=Path, default=ROOT / "output/mvp_review_contact/drowsy")
    args = parser.parse_args()
    render(load(args.tracking), load(args.observations), args.out)
