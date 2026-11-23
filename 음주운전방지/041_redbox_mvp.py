# 041  블랙박스 차량 선택·추적 HUD
# 로컬 영상에서 차량과 경계를 지정하면 006의 타깃과 034의 집계를 연결합니다.
# 실제 판정과 저장 HUD는 같은 프레임 기록을 사용합니다. 결과 폴더는 실행마다 새로 만듭니다.
# 영상·JSON·후보 근거 클립은 로컬 검토와 다음 성능 검증에 사용합니다.

"""RedBox 블랙박스 분석과 검토 화면"""

import argparse
from base64 import b64encode
from collections import Counter
from contextlib import contextmanager
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
from PIL import Image, ImageDraw, ImageFont
import torch
from ultralytics import YOLO

from preview_lane_track_197 import load_lane_model, predict_lane, track_vehicles, verify_video
from redbox_vehicle_info import VehicleInfo
from track_preview import ROOT, VEHICLES, Target


crossing_module = import_module("034_detect_lane_crossing_197")
media_handler = import_module("035_serve_redbox_case").CaseHandler
OUTPUT = ROOT / "output/lane_video_197_mvp"
INPUT = ROOT / "videos"
LABEL = crossing_module.EVENT_LABEL
SIZE = crossing_module.SIZE
FONT = Path("C:/Windows/Fonts/malgunbd.ttf")
STATUS = {
    "tracking_hold": "추적 보류",
    "boundary_unset": "차선 경계 지정 대기",
    "gpu_unavailable": "판정 보류 · 차선 GPU 사용 불가",
    "boundary_missing": "판정 보류 · 경계 미검출",
    "boundary_occluded": "판정 보류 · 경계 가림",
    "boundary_not_supported": "판정 보류 · 차량 근처 경계 근거 부족",
    "near_boundary": "판정 보류 · 경계 근접",
    "crossing_unobserved_during_tracking_gap": "판정 보류 · 추적 공백 중 통과 불명",
    "observed": "추적 중 · 경계 확인",
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
EVENT_FLOAT_SECONDS = 1.2


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


def draw_hud(frame, row, source_kind, *, recording=False):
    height, width = frame.shape[:2]
    size = (960, max(240, round(height*960/width)//2*2))
    image = Image.fromarray(cv2.cvtColor(cv2.resize(frame, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image, "RGBA")
    scale = (size[0]/width, size[1]/height)
    info = row["vehicle_info"]
    phase = row["seconds"]
    clock = f"{int(phase//60):02d}:{phase%60:05.2f}"
    if row["boundary"]:
        draw.line([tuple(round(v*s) for v,s in zip(p, scale)) for p in row["boundary"]],
                  fill=HUD_BLUE, width=2)
    if row["box"]:
        x, y, a, b = (round(v*scale[i%2]) for i,v in enumerate(row["box"]))
        draw.rectangle((x, y, a, b), outline=HUD_RED, width=2)
        center = (x+a)//2
        marker_y = max(10, y-5)
        draw.polygon([(center-7, marker_y-10), (center+7, marker_y-10), (center, marker_y)], fill=HUD_RED)

    hud_text(draw, 18, 17, [("컬러: ", HUD_GREEN), (info["color"] or "-", HUD_WHITE)], 17)
    hud_text(draw, 18, 40, [("차종: ", HUD_GREEN), (info["vehicle_type"] or "-", HUD_WHITE)], 17)
    hud_text(draw, 18, 65, [(info["plate"] or "차량번호: -", HUD_GREEN)], 26)
    detail = {"manual": "직접 입력", "ocr_candidate": "OCR 후보"}.get(info["plate_source"])
    if detail:
        hud_text(draw, 19, 96, [(detail, HUD_WHITE)], 11)
    # 저장 영상은 기본적으로 회색 REC입니다. 실제 녹화 상태만 빨간 REC를 켭니다.
    hud_text(draw, size[0]//2, 16, [("● REC", HUD_RED if recording else REC_INACTIVE)], 25, align="center")
    hud_text(draw, size[0]//2, 47, [(clock, HUD_WHITE)], 16, align="center")
    source = {"recorded": "실제 영상", "synthetic": "합성 영상", "independent_test": "독립 테스트"}[source_kind]
    hud_text(draw, size[0]//2, 68, [(f"{source} · {'녹화 중' if recording else '분석 재생'}", HUD_WHITE)], 11, align="center")
    hud_text(draw, size[0]-18, 18, [(f"판정: {row.get('verdict') or '-'}", HUD_RED),
                                  ("  |  ", HUD_WHITE), (f"예측: {row.get('prediction') or '-'}", HUD_BLUE)],
             19, align="right")
    if row["count"]:
        hud_text(draw, size[0]-18, 49, [("TOTAL", HUD_GREEN), ("  |  ", HUD_WHITE),
                                      (f"{LABEL}: ", HUD_BLUE), (f"{row['count']}회", HUD_RED)],
                 17, align="right")
    # 브라우저의 재생 버튼·타임라인과 겹치지 않도록 하단에서 조금 띄웁니다.
    hud_text(draw, 18, size[1]-69, [(STATUS[row["status"]], HUD_WHITE)], 14)
    return image


def event_position(box, width, height):
    x1, y1, x2, y2 = box
    # 오른쪽 공간이 부족할 때는 상자 왼쪽에 띄워 영상 밖으로 나가지 않게 합니다.
    align = "left" if x2 / width < .72 else "right"
    x = min(.76, x2 / width + .015) if align == "left" else max(.27, x1 / width - .015)
    y = min(.84, max(.27, (y1 + .38*(y2-y1)) / height))
    return dict(x=x, y=y, align=align)


def draw_event_float(image, event, time_s):
    if event is None:
        return
    phase = (time_s - event["time_s"]) / EVENT_FLOAT_SECONDS
    if not 0 <= phase < 1:
        return
    anchor = event["hud_anchor"]
    text = "+ " + event["label"] + " 1"
    face = font(20)
    width = math.ceil(face.getlength(text)) + 6
    fade = round(255 * (1 - phase**2))
    sprite = Image.new("RGBA", (width, 29))
    ImageDraw.Draw(sprite).text((3, 3), text, font=face, anchor="lt", fill=(255, 55, 77, fade),
                               stroke_width=2, stroke_fill=(0, 0, 0, round(fade*.75)))
    x = round(image.width*anchor["x"]) - (width if anchor["align"] == "right" else 0)
    y = round(image.height*anchor["y"] - 26*phase)
    image.paste(sprite, (x, y), sprite)


def analyze(data, output, progress=lambda frame, total: None, *, web=False):
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
    last_event = None
    writers = []
    analyzed = 0
    try:
        with capture(path, camera) as cap, (output/"frames.jsonl").open("x", encoding="utf-8") as log:
            fps = cap.get(cv2.CAP_PROP_FPS)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            start = round(at*fps)+1
            end = min(total, start+round(duration*fps)-1)
            if fps <= 0 or not 1 <= start <= end or not cap.set(cv2.CAP_PROP_POS_FRAMES, start-1):
                raise ValueError("분석 시작 시각을 확인하세요.")
            crossing = crossing_module.Crossing(fps)
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
                vehicles = vehicle_boxes(track_vehicles(yolo, frame, category_ids, 0 if gpu else "cpu"))
                if number == start:
                    vehicle = select_vehicle(vehicles, point)
                    target.select(vehicle, frame, number)
                else:
                    vehicle = target.update(vehicles, frame, number)
                if vehicle:
                    ids[vehicle["id"]] += 1
                    if number - last_sample >= max(1, round(.32*fps)):
                        info.sample(frame, vehicle, number)
                        last_sample = number
                status = ("gpu_unavailable" if data.get("line") and not gpu else "boundary_unset") if vehicle else "tracking_hold"
                side, distance, endpoints = None, None, None
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
                            side, distance, status = boundary.classify(
                                np.array([(x1+x2)/2, y2])*scale, valid_rows, boxes)
                event = crossing.update(number, side, vehicle is None)
                if crossing.recovery_hold:
                    status = "crossing_unobserved_during_tracking_gap"
                seconds = (number-1)/fps
                if event:
                    events.append(dict(event, candidate=len(events)+1, frame=number, time_s=seconds,
                                       label=LABEL, track_id=vehicle["id"], source_video=path.name,
                                       hud_anchor=event_position(vehicle["box"], w, h),
                                       direction=f"{event['from_side']}_to_{event['to_side']}"))
                    last_event = events[-1]
                row = dict(frame=number, seconds=seconds, status=status, side=side, distance_px=distance,
                           boundary=endpoints, box=vehicle["box"] if vehicle else None,
                           track_id=vehicle["id"] if vehicle else None, count=len(events), new_event=event is not None,
                           vehicle_info=info.snapshot())
                statuses[status] += 1
                hud = draw_hud(frame, row, source_kind)
                if number == start:
                    shape = (hud.height, hud.width)
                    media = [("hud.mp4","mp4v"), ("replay.webm","VP80")] if web else [("hud.mp4","mp4v")]
                    for name, codec in media:
                        writer = cv2.VideoWriter(str(output/name), cv2.VideoWriter_fourcc(*codec), fps, shape[::-1])
                        writers.append(writer)
                        if not writer.isOpened():
                            raise RuntimeError(f"{name} 저장을 시작할 수 없습니다.")
                # 웹은 CSS로 움직이고, 저장 MP4는 같은 시점과 위치에 글자를 그립니다.
                if web:
                    writers[1].write(cv2.cvtColor(np.asarray(hud), cv2.COLOR_RGB2BGR))
                draw_event_float(hud, last_event, seconds)
                writers[0].write(cv2.cvtColor(np.asarray(hud), cv2.COLOR_RGB2BGR))
                log.write(json.dumps(row, ensure_ascii=False)+"\n")
                analyzed += 1
                if analyzed == 1 or analyzed % 12 == 0 or number == end:
                    progress(analyzed, end-start+1)
    finally:
        for writer in writers:
            writer.release()
        if info.windows_ocr:
            info.windows_ocr.close()
    verify_video(output/"hud.mp4", shape, fps, analyzed)
    if web:
        verify_video(output/"replay.webm", shape, fps, analyzed)
    if events:
        crossing_module.save_original_clips(path, output, events, fps, (h,w), total,
                                            open_video=lambda file: ClipCapture(file, camera))
    saved = dict(video=path.name, camera=camera, source_kind=source_kind, selection_frame=start,
                 end_frame=end, fps=fps, selection_point=point, seed_line=data.get("line"),
                 analyzed_frames=analyzed, confirmed_frames=sum(ids.values()), track_ids=dict(ids),
                 hold_reasons=dict(statuses), lane_enabled=lane_model is not None,
                 lane_status="active" if lane_model else "gpu_unavailable" if data.get("line") else "boundary_unset",
                 ocr_status=ocr_status, windows_ocr_available=bool(info.windows_ocr and info.windows_ocr.process
                                                                 and info.windows_ocr.available),
                 vehicle_info=info.snapshot(), ocr_frames=info.ocr_frames,
                 event_total=len(events), events=events)
    save_result(output, saved)
    return saved


def save_result(output, data):
    work = output/"target.tmp"
    work.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    work.replace(output/"target.json")


def preview(data):
    path, camera, _, at = spec(data)
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
                job = {"state":"running", "frame":0, "total":0}
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
        def progress(frame, total):
            job.update(frame=frame, total=total)
        try:
            saved = analyze(data, OUTPUT/uid, progress, web=True)
            job.update(result=saved, state="done")
        except Exception as error:
            job.update(state="error", error=str(error))
        finally:
            self.server.model_lock.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
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
        server.model_lock, server.edit_lock = Lock(), Lock()
        print(f"RedBox MVP  http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
