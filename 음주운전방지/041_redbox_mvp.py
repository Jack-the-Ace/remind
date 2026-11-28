# 041  블랙박스 차량 선택·추적 HUD
# 로컬 영상에서 차량과 경계를 지정하면 006의 타깃과 034의 집계를 연결합니다.
# 실제 판정과 저장 HUD는 같은 프레임 기록을 사용합니다. 결과 폴더는 실행마다 새로 만듭니다.
# 영상·JSON·후보 근거 클립은 로컬 검토와 다음 성능 검증에 사용합니다.

"""RedBox 블랙박스 분석과 검토 화면"""

import argparse
from base64 import b64encode
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from functools import lru_cache
from http.server import ThreadingHTTPServer
from importlib import import_module
import io
import json
import math
from pathlib import Path
import re
from threading import Lock, Thread
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont
import torch
from ultralytics import YOLO

from preview_lane_track_197 import load_lane_model, predict_lane, track_vehicles, verify_video
from redbox_stop_line import StopLineMonitor
from redbox_vehicle_info import VehicleInfo
from redbox_lane_geometry import ShortTargetMatch
from track_preview import ROOT, VEHICLES, Target


crossing_module = import_module("034_detect_lane_crossing_197")
media_handler = import_module("035_serve_redbox_case").CaseHandler
OUTPUT = ROOT / "output/lane_video_197_mvp"
INPUT = ROOT / "videos"
SIZE = crossing_module.SIZE
FONT = Path("C:/Windows/Fonts/malgunbd.ttf")
STATUS = {
    "tracking_hold": "추적 보류",
    "boundary_unset": "차선 경계 지정 대기",
    "gpu_unavailable": "판정 보류 · 차선 GPU 사용 불가",
    "boundary_missing": "판정 보류 · 경계 미검출",
    "boundary_occluded": "판정 보류 · 경계 가림",
    "boundary_not_supported": "판정 보류 · 차량 근처 경계 근거 부족",
    "near_boundary": "추적 중 · 경계 근접",
    "crossing_unobserved_during_tracking_gap": "판정 보류 · 추적 공백 중 통과 불명",
    "observed": "추적 중 · 경계 확인",
    "stop_observed": "추적 중 · 정지선 확인",
    "stop_near_line": "판정 보류 · 정지선 근접",
    "stop_motion_hold": "판정 보류 · 도로 움직임 불확실",
    "stop_paint_hold": "판정 보류 · 정지선 도색 불확실",
    "stop_line_lost": "판정 보류 · 지정 정지선 추적 상실",
    "stop_contact_hold": "판정 보류 · 차량 접지점 불확실",
    "stop_gap_hold": "판정 보류 · 공백 중 정지선 통과 불명",
}


class RearStream(io.BufferedReader):
    def __init__(self, path):
        super().__init__(io.FileIO(path, "r"))
        # 이 블랙박스 AVI는 두 시점을 담습니다. 메모리에서만 첫 영상 헤더를
        # 건너뛰게 해 OpenCV가 두 번째 시점을 읽게 합니다. 원본은 수정하지 않습니다.
        header = self.peek(4096).split(b"movi", 1)[0]
        entries = list(re.finditer(b"strh....vids", header, re.DOTALL))
        if len(entries) != 2:
            self.close()
            raise ValueError("후방은 전·후방 영상이 함께 든 블랙박스 AVI에서만 열 수 있습니다.")
        self.offset = entries[0].start() + 8

    def read(self, size=-1):
        at = self.tell()
        data = super().read(size)
        first = max(at, self.offset)
        end = min(at + len(data), self.offset + 4)
        if first < end:
            return data[:first-at] + b"auds"[first-self.offset:end-self.offset] + data[end-at:]
        return data


@contextmanager
def capture(path, camera):
    stream = RearStream(path) if camera == "rear" else None
    cap = cv2.VideoCapture(stream, cv2.CAP_FFMPEG, []) if stream else cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("동영상을 열 수 없습니다.")
        yield cap
    finally:
        cap.release()
        if stream:
            stream.close()


class ClipCapture:
    def __init__(self, path, camera):
        self.context = capture(path, camera)
        self.cap = self.context.__enter__()

    def __getattr__(self, name):
        return getattr(self.cap, name)

    def release(self):
        self.context.__exit__(None, None, None)


def source_path(name):
    if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("videos 폴더의 파일을 선택하세요.")
    path = INPUT / name
    if path.suffix.lower() not in {".avi", ".mp4"} or not path.is_file():
        raise ValueError("동영상을 찾을 수 없습니다.")
    return path


def select_vehicle(vehicles, point):
    x, y = point
    hits = []
    for car in vehicles:
        a, b, c, d = car["box"]
        if car["id"] is not None and a <= x <= c and b <= y <= d:
            hits.append(((c-a)*(d-b), car))
    if not hits:
        raise ValueError("선택 위치에 추적할 차량 상자가 없습니다. 다른 프레임에서 다시 지정하세요.")
    return min(hits, key=lambda item: item[0])[1]


def vehicle_boxes(vehicles):
    # 모델이 같은 차체를 승용차·화물차로 중복 검출하면 한 상자만 사용합니다.
    kept = []
    for vehicle in sorted(vehicles, key=lambda v: (v["id"] is not None, v["confidence"]), reverse=True):
        a = np.asarray(vehicle["box"])
        for other in kept:
            b = np.asarray(other["box"])
            overlap = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])).prod()
            if overlap > .86 * (np.prod(a[2:]-a[:2]) + np.prod(b[2:]-b[:2]) - overlap):
                break
        else:
            kept.append(vehicle)
    return kept


def spec(data):
    path = source_path(data["video"])
    camera = data.get("camera", "front")
    source_kind = data.get("source_kind", "recorded")
    if camera not in {"front", "rear"} or (camera == "rear" and path.suffix.lower() != ".avi"):
        raise ValueError("영상의 카메라 시점을 확인하세요.")
    if source_kind not in {"recorded", "synthetic", "independent_test"}:
        raise ValueError("영상 자료 유형을 확인하세요.")
    at = float(data.get("at", 0))
    if not math.isfinite(at) or at < 0:
        raise ValueError("영상 시각을 확인하세요.")
    return path, camera, source_kind, at


def coordinates(values, count, width, height):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError("차량 또는 차선 좌표를 확인하세요.")
    xy = [float(value) for value in values]
    if any(not 0 <= v < (width if i % 2 == 0 else height) for i, v in enumerate(xy)):
        raise ValueError("선택 좌표가 영상 범위를 벗어났습니다.")
    return xy


def manual_plate(value):
    value = re.sub(r"\s+", "", value or "")
    if value and (len(value) > 16 or not re.fullmatch("[0-9가-힣-]+", value)):
        raise ValueError("차량번호는 숫자·한글·하이픈으로 입력하세요.")
    return value or None


def new_tracker():
    yolo = YOLO(str(ROOT / "yolo26n.pt"))
    return yolo, [i for i, label in yolo.names.items() if label in VEHICLES]


@lru_cache(maxsize=1)
def lane():
    return load_lane_model(crossing_module.DEFAULT_MODEL, torch.device("cuda:0"))


@lru_cache(maxsize=1)
def ocr():
    try:
        import easyocr
        reader = easyocr.Reader(["ko", "en"], gpu=torch.cuda.is_available(),
                                model_storage_directory=str(Path.home() / ".EasyOCR/model"),
                                download_enabled=False, verbose=False)
        return reader, "enabled"
    except (ImportError, OSError, RuntimeError) as error:
        return None, f"unavailable: {type(error).__name__}"


@lru_cache(maxsize=8)
def font(size):
    return ImageFont.truetype(str(FONT), size)


HUD_RED = "#ff374d"
HUD_GREEN = "#46ff78"
HUD_BLUE = "#50b7ff"
HUD_WHITE = "#ffffff"
REC_INACTIVE = "#b5b5b5"
HUD_PANEL_RGBA = (128, 128, 128, 128)
HUD_PANEL_PADDING = 2
EVENT_FLOAT_SECONDS = 2.0
EVENT_COLORS = {"차선변경": HUD_GREEN, "차선침범": HUD_RED, "정지선 위반": HUD_RED, "정지선위반": HUD_RED}


def hud_text(draw, x, y, parts, size, *, align="left"):
    face = font(size)
    widths = [face.getlength(text) for text, _ in parts]
    width = sum(widths)
    x -= width if align == "right" else width / 2 if align == "center" else 0
    for (text, color), length in zip(parts, widths):
        # 옅은 외곽선만 깔아 밝은 하늘 위에서도 도로를 가리지 않고 읽을 수 있게 합니다.
        draw.text((round(x), y), text, fill=color, font=face, anchor="lt",
                  stroke_width=2, stroke_fill=(0, 0, 0, 179))
        x += length


@lru_cache(maxsize=96)
def panel_sprite(rows, align, padding):
    # 글자와 외곽선을 먼저 투명 레이어에 그립니다. 실제로 칠해진 범위에만 여백을 더합니다.
    margin = max(size for _, _, size in rows) + 2
    width = math.ceil(max(sum(font(size).getlength(t) for t, _ in parts) for _, parts, size in rows))
    height = max(y + size * 2 for y, _, size in rows)
    ink = Image.new("RGBA", (width + 2*margin, height + 2*margin))
    anchor = width + margin if align == "right" else margin
    draw = ImageDraw.Draw(ink)
    for y, parts, size in rows:
        hud_text(draw, anchor, margin+y, parts, size, align=align)
    bounds = ink.getbbox()
    x, y, right, bottom = bounds
    sprite = Image.new("RGBA", (right-x+2*padding, bottom-y+2*padding), HUD_PANEL_RGBA)
    sprite.alpha_composite(ink.crop(bounds), (padding, padding))
    return sprite, (x-padding-anchor, y-padding-margin)


def hud_panel(image, x, y, rows, *, align="left"):
    if not rows:
        return
    lines = tuple((dy, tuple(parts), size) for dy, parts, size in rows)
    sprite, offset = panel_sprite(lines, align, HUD_PANEL_PADDING)
    position = (x + offset[0], y + offset[1])
    if image.mode == "RGBA":
        image.alpha_composite(sprite, position)
    else:
        image.paste(sprite, position, sprite)


def count_parts(label, count):
    return [(f"{label}: {count}회", EVENT_COLORS.get(label, HUD_BLUE))]


LANE_MESSAGES = {
    "small": "선택 차량이 작게 보여 분석이 어렵습니다.",
    "unclear": "선택 차량과 차선이 선명하게 보이지 않습니다.",
}


def draw_lane_notice(draw, size, notice, x=19):
    # 차량과 차선이 있는 화면 중앙을 비워 두고 왼쪽 아래에 두 줄만 표시합니다.
    y = size[1]-109
    if notice in LANE_MESSAGES:
        points=[(x+10,y),(x+21,y+19),(x,y+19),(x+10,y)]
        draw.line(points,fill=HUD_RED,width=2)
        hud_text(draw,x+10,y+6,[("!",HUD_WHITE)],12,align="center")
        hud_text(draw,x+30,y,[("차선 판독 불가",HUD_RED)],19)
        hud_text(draw,x+30,y+27,[(LANE_MESSAGES[notice],HUD_WHITE)],15)
    elif notice=="search":
        hud_text(draw,x,y+24,[("선택 차량을 찾는 중",HUD_WHITE)],18)


def draw_top_panels(image, row):
    info = row["vehicle_info"]
    left_rows = [
        (0, [("컬러: ", HUD_GREEN), (info["color"] or "-", HUD_WHITE)], 17),
        (23, [("차종: ", HUD_GREEN), (info["vehicle_type"] or "-", HUD_WHITE)], 17),
        (48, [(info["plate"] or "차량번호: -", HUD_GREEN)], 26),
    ]
    if "brand" in info or info.get("model_name"):
        left_rows.append((79, [("브랜드 · 모델  ", HUD_GREEN),
                               ((info.get("brand") or "-")+" / "+(info.get("model_name") or "-"), HUD_WHITE)], 14))
    hud_panel(image, 18, 17, left_rows)
    right_rows = [(0, [(f"판정: {row.get('verdict') or '-'}", HUD_RED), ("  |  ", HUD_WHITE),
                       (f"예측: {row.get('prediction') or '-'}", HUD_BLUE)], 19)]
    visible = [(label, count) for label, count in row["event_counts"].items() if count]
    for index, (label, count) in enumerate(visible):
        heading = [("TOTAL", HUD_GREEN), ("  |  ", HUD_WHITE)] if index == 0 else []
        right_rows.append((31 + index*22, heading + count_parts(label, count), 17))
    hud_panel(image, image.width-18, 18, right_rows, align="right")


def draw_hud(frame, row, source_kind, *, recording=False, overlay_only=False, top_panels=True):
    height, width = frame.shape[:2]
    size = (960, max(240, round(height*960/width)//2*2))
    if overlay_only:
        image = Image.new("RGBA", size)
    else:
        image = Image.fromarray(cv2.cvtColor(cv2.resize(frame, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image, "RGBA")
    scale = (size[0]/width, size[1]/height)
    phase = row["seconds"]
    clock = f"{int(phase//60):02d}:{phase%60:05.2f}"
    reading=row.get("lane_readability") or {}
    notice=reading.get("notice")
    if not reading and row.get("status")=="tracking_hold" and not row["box"]:
        notice="search"
    if reading.get("mode")=="remote":
        lines=[edge["points"] for edge in reading["geometry"]["edges"].values() if edge.get("position")]
    else:
        lines=[row["boundary"]] if row["boundary"] and (not reading or reading["counting"]) else []
    for points in lines:
        draw.line([tuple(round(v*s) for v,s in zip(p, scale)) for p in points],
                  fill=HUD_BLUE, width=2)
    if (stop_line := (row.get("stop_line") or {}).get("line")):
        draw.line([tuple(round(v*s) for v,s in zip(p, scale)) for p in stop_line],
                  fill=HUD_BLUE, width=2)
    if row["box"] and notice!="search" and reading.get("raw")!="search":
        x, y, a, b = (round(v*scale[i%2]) for i,v in enumerate(row["box"]))
        draw.rectangle((x, y, a, b), outline=HUD_RED, width=2)
        center = (x+a)//2
        marker_y = max(10, y-5)
        draw.polygon([(center-7, marker_y-10), (center+7, marker_y-10), (center, marker_y)], fill=HUD_RED)

    # 저장 영상은 기본적으로 회색 REC입니다. 실제 녹화 상태만 빨간 REC를 켭니다.
    hud_text(draw, size[0]//2, 16, [("● REC", HUD_RED if recording else REC_INACTIVE)], 25, align="center")
    hud_text(draw, size[0]//2, 47, [(clock, HUD_WHITE)], 16, align="center")
    source = {"recorded": "실제 영상", "synthetic": "합성 영상", "independent_test": "독립 테스트"}[source_kind]
    hud_text(draw, size[0]//2, 68, [(f"{source} · {'녹화 중' if recording else '분석 재생'}", HUD_WHITE)], 11, align="center")
    if top_panels:
        draw_top_panels(image, row)
    text_x=18
    if "contact_seconds" in row and row["box"]:
        left,top,right,bottom=row["box"]
        if left*scale[0]<270 and bottom*scale[1]>size[1]-116:
            text_x=size[0]-300
    if "contact_seconds" in row:
        duration=row["contact_seconds"]
        value="—" if duration is None else f"{duration:.2f}초"
        suffix=" · 정지 화면" if row.get("freeze") else ""
        hud_text(draw,text_x,size[1]-44,[("차선 접촉  ",HUD_GREEN),(value+suffix,HUD_WHITE)],15)
    # 브라우저의 재생 버튼·타임라인과 겹치지 않도록 하단에서 조금 띄웁니다.
    if notice in LANE_MESSAGES or notice=="search":
        draw_lane_notice(draw,size,notice,text_x+1)
    else:
        if notice=="checking":
            text="차선 재관측 중"
        elif notice=="ready":
            positions=reading.get("positions")
            if positions:
                text=("양쪽 차선 판독 중" if len(positions)==2 else
                      ("왼쪽 경계 판독 · 오른쪽 보류" if "left" in positions else "오른쪽 경계 판독 · 왼쪽 보류"))
            else:
                text=row.get("status_text") or "선택 차량 관찰 중"
        else:
            text=row.get("status_text") or STATUS[row["status"]]
        hud_text(draw,text_x,size[1]-69,[(text,HUD_WHITE)],14)
    return image


def event_position(box, width, height):
    x1, y1, x2, y2 = box
    # 오른쪽 공간이 부족할 때는 상자 왼쪽에 띄워 영상 밖으로 나가지 않게 합니다.
    align = "left" if x2 / width < .72 else "right"
    x = min(.76, x2 / width + .015) if align == "left" else max(.27, x1 / width - .015)
    y = min(.84, max(.27, (y1 + .38*(y2-y1)) / height))
    return dict(x=x, y=y, align=align)


def draw_event_float(image, event, time_s, *, stack=0):
    if event is None:
        return False
    elapsed = round(time_s - event["time_s"], 9)
    if not 0 <= elapsed < EVENT_FLOAT_SECONDS:
        return False
    anchor = event["hud_anchor"]
    label = event.get("display_label", event["label"])
    text = "+" + label + ("1" if label in ("차선침범", "정지선위반") else " 1")
    face = font(20)
    width = math.ceil(face.getlength(text)) + 6
    fade = round(255 * min(1, EVENT_FLOAT_SECONDS - elapsed))
    sprite = Image.new("RGBA", (width, 29))
    ImageDraw.Draw(sprite).text((3, 3), text, font=face, anchor="lt", fill=(*ImageColor.getrgb(EVENT_COLORS.get(label, HUD_RED)), fade),
                               stroke_width=2, stroke_fill=(0, 0, 0, round(fade*.75)))
    x = round(image.width*anchor["x"]) - (width if anchor["align"] == "right" else 0)
    y = round(image.height*anchor["y"] - 13*elapsed - stack*55)
    if image.mode == "RGBA":
        image.alpha_composite(sprite, (x, y))
    else:
        image.paste(sprite, (x, y), sprite)
    return True


def draw_event_floats(image, events, time_s):
    for event in reversed(events):
        if time_s - event["time_s"] >= EVENT_FLOAT_SECONDS:
            break
        if event["time_s"] <= time_s:
            draw_event_float(image, event, time_s, stack=event.get("float_slot", 0))


def set_float_slot(event, prior):
    # 같은 사건은 끝날 때까지 같은 줄을 사용합니다. 이전 글자가 사라지면 그 줄을 재사용합니다.
    used = {e.get("float_slot", 0) for e in prior if 0 <= event["time_s"]-e["time_s"] < EVENT_FLOAT_SECONDS}
    event["float_slot"] = next(n for n in range(len(used)+1) if n not in used)
    return event


@contextmanager
def encode_hud(output, shape, fps, web):
    writers = []
    try:
        formats = [("hud.mp4", "mp4v"), ("replay.webm", "VP80")] if web else [("hud.mp4", "mp4v")]
        for name, codec in formats:
            writer = cv2.VideoWriter(str(output/name), cv2.VideoWriter_fourcc(*codec), fps, shape[::-1])
            writers.append(writer)
            if not writer.isOpened():
                raise RuntimeError(f"{name} 저장을 시작할 수 없습니다.")
        pending = deque()
        with ThreadPoolExecutor(max_workers=1) as encoder:
            def write(mp4_frame, replay_frame):
                if replay_frame is not None:
                    writers[1].write(replay_frame)
                writers[0].write(mp4_frame)

            def enqueue(mp4_frame, replay_frame):
                # 저장 중에도 다음 프레임을 분석합니다. 밀린 프레임은 6장까지만 보관합니다.
                if len(pending) >= 6:
                    pending.popleft().result()
                pending.append(encoder.submit(write, mp4_frame, replay_frame))

            yield enqueue
            for task in pending:
                task.result()
    finally:
        for writer in writers:
            writer.release()


def add_event(events, output, event, frame, seconds, vehicle, video, frame_size):
    candidate = len(events)+1
    entry = dict(event, candidate=candidate, frame=frame, time_s=event.get("time_s", seconds),
                 track_id=vehicle["id"], source_video=video, hud_anchor=event_position(vehicle["box"], *frame_size),
                 direction=f"{event['from_side']}_to_{event['to_side']}",
                 event_source="automatic", incident_id=f"{output.name}-{candidate:03d}")
    events.append(set_float_slot(entry, events))


def analyze(data, output, progress=lambda frame, total: None, *, web=False, stage=lambda name: None):
    stage("preparing")
    path, camera, source_kind, at = spec(data)
    duration = float(data.get("duration", 15))
    if not 1 <= duration <= 180:
        raise ValueError("분석 길이는 1~180초로 지정하세요.")
    output.mkdir(parents=True, exist_ok=False)
    reader, ocr_status = (None, "disabled") if data.get("no_ocr") else ocr()
    info = VehicleInfo(reader, manual_plate(data.get("plate")))
    yolo, category_ids = new_tracker()
    gpu = torch.cuda.is_available()
    can_detect_boundary = data.get("line") is not None and gpu
    lane_model = lane() if can_detect_boundary else None
    times = tuple(torch.cuda.Event(enable_timing=True) for _ in range(2)) if lane_model else None
    target = Target()
    events, statuses, ids = [], Counter(), Counter()
    event_counts = Counter()
    stop_statuses = Counter()
    stop_passages = []
    analyzed = 0
    source_times = []
    hud_changes = []
    try:
        with (capture(path, camera) as cap, (output/"frames.jsonl").open("x", encoding="utf-8") as log,
              ExitStack() as media):
            fps = cap.get(cv2.CAP_PROP_FPS)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            start = round(at*fps)+1
            end = min(total, start+round(duration*fps)-1)
            if fps <= 0 or not 1 <= start <= end or not cap.set(cv2.CAP_PROP_POS_FRAMES, start-1):
                raise ValueError("분석 시작 시각을 확인하세요.")
            progress(0, end-start+1)
            stage("analyzing")
            assessor = None
            from redbox_lane_geometry import recording_clock, PaintCurve
            curves={k:PaintCurve(v) for k,v in data.get("lane_curves",{}).items() if k in ("left","right")}
            video_clock=recording_clock(cap,start,end,crossing_module.source_seconds) if can_detect_boundary else None
            continuity = ShortTargetMatch()
            def local_mask(crop):
                return predict_lane(lane_model,crop,torch.device("cuda:0"),(384,240),times)[0]
            stop_monitor = None
            last_sample = -math.inf
            for number in range(start, end+1):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError(f"원본 프레임 {number}를 읽을 수 없습니다.")
                h, w = frame.shape[:2]
                scale = np.array([SIZE[0]/w, SIZE[1]/h])
                if number == start:
                    point = coordinates(data.get("point"), 2, w, h)
                    boundary = None
                    if data.get("line") is not None:
                        line = np.array(coordinates(data["line"], 4, w, h)).reshape(2, 2)
                        if abs(line[0, 1] - line[1, 1]) < 10 or abs(line[0, 0]-line[1, 0]) < 8:
                            raise ValueError("보이는 경사진 경계의 위와 아래에서 두 점을 선택하세요.")
                        if lane_model is not None:
                            boundary = crossing_module.Boundary((line*scale).flatten())
                            assessor = crossing_module.SceneLaneAnalysis(fps,line)
                    if data.get("stop_line") is not None:
                        stop_seed = coordinates(data["stop_line"], 4, w, h)
                        stop_monitor = StopLineMonitor(stop_seed, frame.shape, camera, crossing_module.Crossing(fps))
                vehicles = vehicle_boxes(track_vehicles(yolo, frame, category_ids, 0 if gpu else "cpu"))
                if number == start:
                    vehicle = select_vehicle(vehicles, point)
                    target.select(vehicle, frame, number)
                else:
                    vehicle = target.update(vehicles, frame, number)
                seconds = crossing_module.source_seconds(cap,number,fps)
                track_source = "detector" if vehicle else "missing"
                if assessor is not None:
                    vehicle,track_source = continuity.update(frame,vehicle,vehicles,seconds)
                if vehicle:
                    ids[vehicle["id"]] += 1
                    if (not video_clock or not video_clock[number-start]['duplicate']) and number - last_sample >= max(1, round(.32*fps)):
                        reading_plate = reader is not None and not info.plate_candidate()
                        if reading_plate:
                            stage("ocr")
                        info.sample(frame, vehicle, number)
                        if reading_plate:
                            stage("analyzing")
                        last_sample = number
                status = ("gpu_unavailable" if data.get("line") and not gpu else "boundary_unset") if vehicle else "tracking_hold"
                side, distance, endpoints = None, None, None
                support_gap = None
                if boundary is not None:
                    mask, _ = predict_lane(lane_model, frame, torch.device("cuda:0"), SIZE, times)
                    boxes = [np.asarray(v["box"])*np.tile(scale, 2) for v in vehicles]
                    valid_rows = boundary.detect(mask, boxes)
                    if valid_rows is not None:
                        endpoints = [(float(np.polyval(boundary.line, y)/scale[0]), float(y/scale[1]))
                                     for y in (valid_rows.min(), valid_rows.max())]
                    if vehicle:
                        status = "boundary_missing"
                        if valid_rows is not None:
                            x1, _, x2, y2 = vehicle["box"]
                            support_gap = float(np.min(np.abs(valid_rows-y2*scale[1]))/scale[1])
                            side, distance, status = boundary.classify(
                                np.array([(x1+x2)/2, y2])*scale, valid_rows, boxes)
                lane_observation = status
                source_times.append(seconds)
                reading = None
                detected = []
                if boundary is not None:
                    box=vehicle["box"] if vehicle else None
                    if curves:
                        top=round(h*float(data.get("lane_roi_top",0)))
                        if not 0<=top<h: raise ValueError("차선 분석 영역 확인 필요")
                        local=mask if top==0 else predict_lane(lane_model,frame[top:],torch.device("cuda:0"),SIZE,times)[0]
                        full=np.zeros((h,w),np.uint8)
                        full[top:]=cv2.dilate(cv2.resize(local,(w,h-top),interpolation=cv2.INTER_NEAREST),np.ones((5,5),np.uint8))
                        detected,reading=assessor.evaluate_curves(number,seconds,frame,box,vehicles,full,curves,video_clock[number-start])
                    else:
                        detected,reading=assessor.evaluate(number,seconds,frame,box,endpoints,status,support_gap,vehicles,local_mask,video_clock[number-start])
                stop_row = None
                if stop_monitor:
                    stop_row, passage = stop_monitor.update(number, frame, vehicles, vehicle)
                    stop_statuses[stop_row["status"]] += 1
                    if passage:
                        # 통과 관찰은 2초 정차가 확인된 사건과 별개로 보존합니다.
                        stop_passages.append(dict(passage, frame=number, time_s=seconds,
                                                  track_id=vehicle["id"], event_source="automatic"))
                    if data.get("line") is None:
                        status = stop_row["status"]
                for event in detected:
                    add_event(events, output, event, number, seconds, vehicle, path.name, (w, h))
                    event_counts[event["label"]] += 1
                row = dict(frame=number, seconds=seconds, status=status, side=side, distance_px=distance,
                           lane_observation=lane_observation, lane_readability=reading,
                           track_source=track_source,
                           footprint_position=(reading.get("positions",{}).get(assessor.geometry.primary) if reading and reading.get("mode")=="remote"
                                               else assessor.legacy.behavior.last_position if assessor else None),
                           contact_start_s=(assessor.clocks[assessor.geometry.primary].first_contact if reading and reading.get("mode")=="remote"
                                            else assessor.legacy.behavior.start if assessor else None), boundary=endpoints,
                           box=vehicle["box"] if vehicle else None, track_id=vehicle["id"] if vehicle else None,
                           count=len(events), new_event=bool(detected), event_counts=dict(event_counts),
                           vehicle_info=info.snapshot())
                if video_clock:
                    row.update(video_clock[number-start],contact_seconds=reading.get('contact_seconds') if reading else None)
                if stop_monitor:
                    row["stop_line"] = stop_row
                statuses[status] += 1
                hud = draw_hud(frame, row, source_kind, top_panels=not web)
                if web:
                    # 웹은 CSS 패널을 영상 시각에 맞춰 표시합니다. 독립 MP4에는 같은 값을 직접 합성합니다.
                    fields = dict(vehicle_info=row["vehicle_info"], verdict=row.get("verdict"), prediction=row.get("prediction"))
                    if not hud_changes or fields != hud_changes[-1]["fields"]:
                        hud_changes.append(dict(frame=number, fields=fields))
                    web_hud = hud.copy()
                    draw_top_panels(hud, row)
                if number == start:
                    shape = (hud.height, hud.width)
                    enqueue = media.enter_context(encode_hud(output, shape, fps, web))
                # 한 프레임에 그린 글자를 두 파일에 함께 저장해 재생·탐색 시 동작을 맞춥니다.
                draw_event_floats(hud, events, seconds)
                mp4_frame = cv2.cvtColor(np.asarray(hud), cv2.COLOR_RGB2BGR)
                replay_frame = None
                if web:
                    draw_event_floats(web_hud, events, seconds)
                    replay_frame = cv2.cvtColor(np.asarray(web_hud), cv2.COLOR_RGB2BGR)
                enqueue(mp4_frame, replay_frame)
                log.write(json.dumps(row, ensure_ascii=False)+"\n")
                analyzed += 1
                if analyzed == 1 or analyzed % 12 == 0 or number == end:
                    progress(analyzed, end-start+1)
            stage("encoding")
    finally:
        if info.windows_ocr:
            info.windows_ocr.close()
    stage("verifying")
    verify_video(output/"hud.mp4", shape, fps, analyzed)
    if web:
        verify_video(output/"replay.webm", shape, fps, analyzed)
    if events:
        stage("clips")
        crossing_module.save_original_clips(path, output, events, fps, (h,w), total,
                                            open_video=lambda file: ClipCapture(file, camera))
    saved = dict(video=path.name, camera=camera, source_kind=source_kind, selection_frame=start,
                 end_frame=end, fps=fps, selection_point=point, seed_line=data.get("line"),
                 analyzed_frames=analyzed, confirmed_frames=sum(ids.values()), track_ids=dict(ids),
                 hold_reasons=dict(statuses), lane_enabled=lane_model is not None,
                 lane_status="active" if lane_model else "gpu_unavailable" if data.get("line") else "boundary_unset",
                 ocr_status=ocr_status, windows_ocr_available=bool(info.windows_ocr and info.windows_ocr.process
                                                                 and info.windows_ocr.available),
                 vehicle_info=info.snapshot(), ocr_frames=info.ocr_frames, event_counts=dict(event_counts),
                 lane_rule_version=crossing_module.LANE_RULE_VERSION, event_total=len(events), events=events)
    if web:
        saved["hud_changes"] = hud_changes
    if any(abs(t-(start+i-1)/fps) > .001 for i,t in enumerate(source_times)):
        saved["source_times"] = source_times
    if stop_monitor:
        saved.update(stop_seed=data["stop_line"], stop_statuses=dict(stop_statuses), stop_passages=stop_passages,
                     signal_state="확인 불가")
    stage("saving")
    save_result(output, saved)
    return saved


def save_result(output, data):
    work = output/"target.tmp"
    work.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    work.replace(output/"target.json")


def preview(data):
    path, camera, _, at = spec(data)
    source = path.stat()
    # 같은 시각의 미리보기를 다시 요청하면 영상 읽기와 YOLO 실행을 건너뜁니다.
    return preview_frame(path, camera, at, source.st_mtime_ns, source.st_size)


@lru_cache(maxsize=8)
def preview_frame(path, camera, at, modified_ns, file_size):
    with capture(path, camera) as cap:
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        index = round(at*fps)
        if fps <= 0 or index >= total or not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
            raise ValueError("미리 볼 영상 시각을 확인하세요.")
        ok, frame = cap.read()
        if not ok:
            raise ValueError("미리보기 프레임을 읽을 수 없습니다.")
    h, w = frame.shape[:2]
    detector, ids = new_tracker()
    cars = vehicle_boxes(track_vehicles(detector, frame, ids, 0 if torch.cuda.is_available() else "cpu"))
    cars = [car["box"] for car in cars if car["id"] is not None]
    small = cv2.resize(frame, (min(w, 1120), round(h*min(w, 1120)/w)))
    ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("미리보기 이미지를 만들 수 없습니다.")
    return dict(image=b64encode(jpg.tobytes()).decode("ascii"), frame=index+1,
                at=index/fps, duration=total/fps, width=w, height=h, boxes=cars)


APP_FILES = {
    "/": ("042_index.html", "text/html; charset=utf-8"),
    "/mvp.css": ("043_mvp.css", "text/css; charset=utf-8"),
    "/mvp.js": ("044_mvp.js", "text/javascript; charset=utf-8"),
}
DEMO_FILES = {"hud.mp4": "video/mp4", "target.json": "application/json; charset=utf-8",
              "original.mp4": "video/mp4"}


def load_demos(directory):
    demos = {}
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if not re.fullmatch(r"[a-z0-9-]+", path.name) or not all((path/f).is_file() for f in DEMO_FILES):
                continue
            data = json.loads((path/"target.json").read_text(encoding="utf-8"))
            if data.get("event_vocabulary") == 2 and data.get("lane_rule_version") == crossing_module.LANE_RULE_VERSION:
                demos[path.name] = (path, data)
    return demos


RUN_FILES = {"replay.webm": "video/webm", "hud.mp4": "video/mp4", "target.json": "application/json; charset=utf-8"}


class Handler(media_handler):
    def allowed_host(self):
        port = self.server.server_port
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def reply(self, payload, code=200, head=False):
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(response)

    def serve(self, head_only):
        if not self.allowed_host():
            self.send_error(403)
            return
        route = urlsplit(self.path).path
        if route == "/api/hud-style":
            self.reply(dict(panel_rgb=HUD_PANEL_RGBA[:3], opacity=0.5, padding=HUD_PANEL_PADDING,
                            event_colors=EVENT_COLORS, default_event_color=HUD_BLUE), head=head_only)
            return
        if route == "/api/demos":
            self.reply([{"id": key, "title": data["demo_title"]}
                        for key, (_, data) in self.server.demos.items()], head=head_only)
            return
        if match := re.fullmatch(r"/api/demos/([a-z0-9-]+)", route):
            demo = self.server.demos.get(match[1])
            self.reply(demo[1] if demo else {"error": "시연을 찾을 수 없습니다."},
                       200 if demo else 404, head=head_only)
            return
        if match := re.fullmatch(r"/demo-media/([a-z0-9-]+)/([a-z.0-9]+)", route):
            demo, kind = self.server.demos.get(match[1]), match[2]
            if not demo or kind not in DEMO_FILES:
                self.send_error(404)
                return
            self.server.files[route] = (demo[0]/kind, DEMO_FILES[kind])
            super().serve(head_only)
            return
        if route == "/api/videos":
            names = sorted(p.name for p in INPUT.iterdir() if p.suffix.lower() in {".avi", ".mp4"} and p.is_file())
            self.reply(sorted(names, key=lambda name: not name.startswith("BB_")), head=head_only)
            return
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{12})", route)
        if match:
            job = self.server.jobs.get(match[1])
            self.reply(job or {"error":"분석 기록을 찾을 수 없습니다."}, 200 if job else 404, head_only)
            return
        entry = APP_FILES.get(route)
        if entry:
            path = ROOT/"redbox_mvp"/entry[0]
            mime = entry[1]
        else:
            match = re.fullmatch(r"/media/([0-9a-f]{12})/([a-z.0-9]+)", route)
            if not match or match[2] not in RUN_FILES or match[1] not in self.server.jobs:
                self.send_error(404)
                return
            path = OUTPUT/match[1]/match[2]
            mime = RUN_FILES[match[2]]
            if self.server.jobs[match[1]]["state"] != "done" or not path.is_file():
                self.send_error(404)
                return
        # 035의 응답 방식은 범위 요청을 처리하므로 브라우저에서 영상을 탐색할 수 있습니다.
        self.server.files[route] = (path, mime)
        super().serve(head_only)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self.allowed_host() or (origin and origin != f"http://{self.headers['Host']}"):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError("분석 요청 크기가 올바르지 않습니다.")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("분석 요청은 JSON이어야 합니다.")
            data = json.loads(self.rfile.read(length))
            route = urlsplit(self.path).path
            if route == "/api/preview":
                with self.server.model_lock:
                    result = preview(data)
                self.reply(result)
            elif route == "/api/analyze":
                spec(data)
                manual_plate(data.get("plate"))
                if not self.server.model_lock.acquire(blocking=False):
                    self.reply({"error":"현재 분석이 끝난 뒤 다시 실행하세요."}, 409)
                    return
                uid = uuid4().hex[:12]
                job = {"state":"running", "frame":0, "total":0, "percent":0, "stage":"preparing"}
                self.server.jobs[uid] = job
                Thread(target=self.run_job, args=(data, uid, job), daemon=True).start()
                self.reply({"job":uid}, 202)
            elif match := re.fullmatch(r"/api/jobs/([0-9a-f]{12})/plate", route):
                # 수동 번호 입력은 차량 선택과 독립적입니다. 나중에 음성 입력도 이 경로를 사용할 수 있습니다.
                job = self.server.jobs.get(match[1])
                if not job or job["state"] != "done":
                    self.reply({"error":"완료된 분석을 선택하세요."}, 404)
                    return
                with self.server.edit_lock:
                    saved = job["result"]
                    info = saved["vehicle_info"]
                    plate = manual_plate(data.get("plate"))
                    edited = dict(info, plate=plate or info["ocr_candidate"],
                                  plate_source="manual" if plate else "ocr_candidate" if info["ocr_candidate"] else None)
                    updated = dict(saved, vehicle_info=edited)
                    save_result(OUTPUT/match[1], updated)
                    job["result"] = updated
                self.reply(edited)
            else:
                self.send_error(404)
        except (ValueError, TypeError, KeyError) as error:
            self.reply({"error":str(error)}, 400)
        except (OSError, RuntimeError, cv2.error) as error:
            self.reply({"error":str(error)}, 500)

    def run_job(self, data, uid, job):
        milestones = {"preparing": 0, "analyzing": 5, "ocr": 5, "encoding": 90,
                      "verifying": 93, "clips": 96, "saving": 99}

        def progress(frame, total):
            job.update(frame=frame, total=total, percent=5+int(84*frame/total))

        def stage(name):
            # 마지막 프레임 뒤에도 인코딩, 검증, 저장이 남으므로 100%는 완료 때만 보냅니다.
            job.update(stage=name, percent=max(job["percent"], milestones[name]))
        try:
            saved = analyze(data, OUTPUT/uid, progress, web=True, stage=stage)
            job.update(result=saved, state="done", stage="done", percent=100)
        except Exception as error:
            job.update(state="error", error=str(error))
        finally:
            self.server.model_lock.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--demo-dir", type=Path, default=OUTPUT/"demo_contact_v1")
    parser.add_argument("--spec", type=Path, help="차량 선택 좌표가 있는 분석 JSON. 목록으로 여러 영상을 시험할 수 있습니다.")
    parser.add_argument("--output", type=Path, help="--spec의 결과를 담을 새 폴더")
    parser.add_argument("--web-media", action="store_true", help="일괄 검증에서도 브라우저 재생용 WebM 저장")
    args = parser.parse_args()
    cv2.setNumThreads(2)
    torch.set_num_threads(min(4, torch.get_num_threads()))
    if args.spec:
        if not args.output or not args.output.resolve().is_relative_to(OUTPUT.resolve()):
            parser.error("--output은 output/lane_video_197_mvp 아래 새 폴더를 지정하세요.")
        values = json.loads(args.spec.read_text(encoding="utf-8-sig"))
        args.output.mkdir(parents=True, exist_ok=False)
        for i, data in enumerate(values if isinstance(values, list) else [values], 1):
            try:
                result = analyze(data, args.output/f"{i:02}", web=args.web_media)
                print(data["video"], result["confirmed_frames"], result["analyzed_frames"],
                      result["event_total"], result["vehicle_info"]["plate_source"], flush=True)
            except (ValueError, RuntimeError, OSError) as error:
                print(data.get("video"), type(error).__name__, str(error), flush=True)
        return
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.files, server.jobs = {}, {}
        server.demos = load_demos(args.demo_dir)
        server.model_lock, server.edit_lock = Lock(), Lock()
        print(f"RedBox MVP  http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
