"""049 · 저장된 차량 추적과 사용자가 확인한 행동 구간으로 로컬 시연을 제작합니다."""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from fractions import Fraction
from importlib import import_module
import json
from pathlib import Path
import re
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw

mvp = import_module("041_redbox_mvp")
STOP = "정지선 위반"
MANUAL_LABELS = {STOP, "차선변경", "차선침범"}


def reasons_for_event(rows, item, fps):
    label, first = item["label"], item["first_frame"]
    last = item.get("last_frame", first)
    if label not in MANUAL_LABELS or not rows[0]["frame"] <= first <= last <= rows[-1]["frame"]:
        raise ValueError("시연 항목명 또는 관찰 프레임 범위를 확인하세요.")
    start = None
    frames = 0
    for row in rows[first-rows[0]["frame"]:last-rows[0]["frame"]+1]:
        if row["box"] is None:
            start = None
            frames = 0
            continue
        if start is None:
            start = row["frame"]
        frames += 1
        # 정차 구간은 원본에서 사람이 확인합니다. 추적 공백이 생기면 2초를 다시 셉니다.
        elapsed = (frames-1)/fps
        if label == STOP and elapsed < 2:
            continue
        if label != STOP and row["frame"] != first:
            break
        return dict(label=label, event_source="manual_demo", frame=row["frame"], time_s=row["seconds"],
                    track_id=row["track_id"], reviewed_start_frame=first, reviewed_end_frame=last,
                    observation_start_frame=start, observation_start_seconds=(start-1)/fps,
                    stationary_seconds=elapsed if label == STOP else None, reason=item["reason"])
    raise ValueError(f"{label} 기록에 필요한 연속 추적 근거가 없습니다.")


@contextmanager
def writer(ffmpeg, path, size, fps):
    rate = Fraction(str(fps))
    process = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-n", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{size[0]}x{size[1]}", "-r", str(rate), "-i", "-", "-an", "-c:v", "libx264",
         "-crf", "17", "-preset", "fast", "-threads", "3", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
    try:
        yield process.stdin.write
    finally:
        process.stdin.close()
        if process.wait():
            raise RuntimeError(f"영상 저장 실패: {path.name}")


def verify(path, size, fps, frames):
    reader = cv2.VideoCapture(str(path))
    try:
        if abs(reader.get(cv2.CAP_PROP_FPS)-fps) > .0009:
            raise ValueError(f"영상 FPS 불일치: {path.name}")
        for _ in range(frames):
            ok, frame = reader.read()
            if not ok or frame.shape[:2] != size[::-1]:
                raise ValueError(f"저장 프레임을 읽을 수 없습니다: {path.name}")
        if reader.read()[0]:
            raise ValueError(f"저장 프레임 수 불일치: {path.name}")
    finally:
        reader.release()


def prepare_events(rows, meta, spec, size):
    if "events" in spec:
        events = [reasons_for_event(rows, item, meta["fps"]) for item in spec["events"]]
        stops = sorted((e["reviewed_start_frame"], e["reviewed_end_frame"]) for e in events if e["label"] == STOP)
        if any(b[0] <= a[1]+1 for a, b in zip(stops, stops[1:])):
            raise ValueError("같은 정차 구간은 한 번만 지정하세요.")
    else:
        # 예전 분석의 경계 관측을 새 규칙으로 다시 읽습니다.
        behavior = mvp.crossing_module.LaneBehavior(meta["fps"])
        events = []
        for row in rows:
            result = behavior.update(row["frame"], row["side"],
                                     row.get("lane_observation", row["status"]), row["distance_px"])
            if result:
                events.append(dict(result, event_source="automatic", frame=row["frame"],
                                   time_s=row["seconds"], track_id=row["track_id"]))
    events.sort(key=lambda event: event["frame"])
    for event in events:
        row = rows[event["frame"]-meta["selection_frame"]]
        event["hud_anchor"] = mvp.event_position(row["box"], *size)
        event["source_video"] = meta["video"]
    return events


def draw_pair(frame, hud, labels):
    height, width = frame.shape[:2]
    pair = np.zeros((height+56,width*2,3), np.uint8)
    pair[:56] = labels
    pair[56:,:width], pair[56:,width:] = frame, hud
    return pair


def build(spec, output, ffmpeg):
    analysis = Path(spec["analysis"])
    out = output/spec["id"]
    if not re.fullmatch(r"[a-z0-9-]+", out.name) or any(c in spec["id"] for c in ("/","\\")):
        raise ValueError("시연 ID는 영문 소문자·숫자·하이픈만 사용하세요.")
    out.mkdir(parents=True)
    meta = json.loads((analysis/"target.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (analysis/"frames.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["frame"] for r in rows] == list(range(meta["selection_frame"], meta["end_frame"]+1))
    fps = meta["fps"]
    source = mvp.source_path(meta["video"])
    counts = Counter()
    with mvp.capture(source, meta["camera"]) as cap, ExitStack() as media:
        assert abs(cap.get(cv2.CAP_PROP_FPS)-fps) < 1e-7
        width, height = (int(cap.get(p)) for p in (cv2.CAP_PROP_FRAME_WIDTH,cv2.CAP_PROP_FRAME_HEIGHT))
        native = (width,height)
        pair_size = (2*width,height+56)
        events = prepare_events(rows,meta,spec,native)
        assert cap.set(cv2.CAP_PROP_POS_FRAMES, meta["selection_frame"]-1)
        label_image = Image.new("RGB",(2*width,56),"#101828")
        draw = ImageDraw.Draw(label_image)
        draw.text((25,8),"BEFORE · 원본", font=mvp.font(29),fill="white")
        draw.text((width+25,8),"AFTER · RedBox",font=mvp.font(29),fill=mvp.HUD_GREEN)
        labels = cv2.cvtColor(np.asarray(label_image),cv2.COLOR_RGB2BGR)
        save_raw = media.enter_context(writer(ffmpeg,out/"original.mp4",native,fps))
        save_hud = media.enter_context(writer(ffmpeg,out/"hud.mp4",native,fps))
        save_pair = media.enter_context(writer(ffmpeg,out/"comparison.mp4",pair_size,fps))
        shown_events = []
        for row in rows:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"원본 읽기 실패: F{row['frame']}")
            assert abs((row["frame"]-1)/fps-row["seconds"]) < 1e-8
            current = [event for event in events if event["frame"] == row["frame"]]
            for event in current:
                counts[event.get("display_label",event["label"])] += 1
                shown_events.append(event)
            shown = dict(row, event_counts=dict(counts), count=sum(counts.values()))
            if "reviewed_stop_line" in spec:
                # 촬영차도 고정된 관찰 구간에서 육안으로 지정한 선을 얹습니다.
                line = spec["reviewed_stop_line"]
                shown["stop_line"] = {"line": [line[:2],line[2:]]}
                shown["status_text"] = "타깃 추적 중" if row["box"] else "추적 보류"
            layer = mvp.draw_hud(frame,shown,meta["source_kind"],overlay_only=True)
            mvp.draw_event_floats(layer,shown_events,row["seconds"])
            original = Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).convert("RGBA")
            original.alpha_composite(layer.resize(native,Image.Resampling.BILINEAR))
            hud = cv2.cvtColor(np.asarray(original),cv2.COLOR_RGBA2BGR)
            save_raw(frame)
            save_hud(hud)
            save_pair(draw_pair(frame,hud,labels))
            row["demo_event_counts"] = shown["event_counts"]
            row["demo_new_event"] = bool(current)
    for filename, size in (("original.mp4",native),("hud.mp4",native),("comparison.mp4",pair_size)):
        verify(out/filename,size,fps,len(rows))
    # 정지선 통과 감지 로그와 수동 지정 시연 이벤트를 둘 다 보관합니다.
    meta["source_events"] = meta["events"]
    meta.update(demo_title=spec["title"], playback_mode="prerendered", event_vocabulary=2, events=events,
                event_total=len(events), event_counts=dict(counts),
                event_float_seconds=mvp.EVENT_FLOAT_SECONDS, reviewed_stop_line=spec.get("reviewed_stop_line"))
    (out/"target.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (out/"frames.jsonl").open("x",encoding="utf-8") as log:
        for row in rows:
            log.write(json.dumps(row,ensure_ascii=False)+"\n")
    print(spec["id"], len(rows), f"{fps:.3f} fps", [(e["frame"],round(e["time_s"],3)) for e in events], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    for item in json.loads(args.spec.read_text(encoding="utf-8-sig")):
        build(item,args.output,args.ffmpeg)


if __name__ == "__main__":
    main()
