"""선택한 차량과 차선 경계를 따라 차선 경계 통과 후보를 기록합니다."""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from preview_lane_track_197 import (
    DEFAULT_VIDEO, ROOT, draw_overlay, load_lane_model, predict_lane, read_track_replay, verify_video,
)


SIZE = (640, 400)
DEFAULT_MODEL = ROOT / "output/lane_transfer_197_highres/imagenet_v1_640x400_recalibrated.pt"
DEFAULT_TRACK = ROOT / "output/lane_video_197_retrained_compare/640x400/frames.jsonl"
SIDE_MARGIN = 9
HOLD_SECONDS = 0.20
MAX_UNCERTAIN_SECONDS = 1.35
EVENT_LABEL = "차선 경계 통과 후보"


class Boundary:
    def __init__(self, seed):
        x1, y1, x2, y2 = seed
        self.line = np.polyfit([y1, y2], [x1, x2], 1)
        self.direction = np.sign(self.line[0])

    def detect(self, mask, boxes, *, row_limits=(143, SIZE[1] - 2), min_points=12, min_span=53, corridor=None):
        # 이전에 선택한 선 주변만 살펴 다른 차선으로 바뀌는 것을 막습니다.
        points = []
        for y in range(*row_limits, 4):
            center = np.polyval(self.line, y)
            span = corridor if corridor is not None else 18 + (y - 143) * .044
            left, right = max(0, round(center - span)), min(SIZE[0], round(center + span) + 1)
            if right <= left:
                continue
            xs = np.flatnonzero(mask[y, left:right]) + left
            for x1, y1, x2, y2 in boxes:
                if y1 - 1 <= y <= y2 + 1:
                    xs = xs[(xs < x1 - 1) | (xs > x2 + 1)]
            parts = np.split(xs, np.flatnonzero(np.diff(xs) > 1) + 1)
            candidates = [float(np.mean(p)) for p in parts if 2 <= len(p) <= 24]
            if candidates:
                points.append((y, min(candidates, key=lambda x: abs(x - center))))
        if len(points) < min_points:
            return None
        y, x = np.array(points).T
        fit = np.polyfit(y, x, 1)
        keep = np.abs(x - np.polyval(fit, y)) <= 9
        if keep.sum() < min_points or np.ptp(y[keep]) < min_span:
            return None
        fit = np.polyfit(y[keep], x[keep], 1)
        check_rows = [180, 280, 370]
        if not .50 <= self.direction * fit[0] <= 2.45 or np.max(np.abs(np.polyval(fit - self.line, check_rows))) > 21:
            return None
        # 이동 평균은 선을 안정화하고, 유효 지점은 이번 프레임의 마스크에서만 가져옵니다.
        self.line = .62 * self.line + .38 * fit
        return y[keep]

    def classify(self, point, rows, boxes, *, paint_support=False):
        px, py = point
        x_on_lane = float(np.polyval(self.line, py))
        distance = (px - x_on_lane) / math.sqrt(1 + self.line[0] ** 2)
        # 가까운 지지점이 없는 긴 외삽과 차량에 가린 지점의 판정을 보류합니다.
        near = np.min(np.abs(rows - py))
        if near > 38 or py > rows.max() + 26 or py < rows.min() - 30:
            return None, distance, "boundary_not_supported"
        # 박스가 선을 덮는 모양이면 바퀴 바로 아래에 보이는 선 근거가 필요합니다.
        # 선택한 노란 도색을 좁게 확인한 경우에만 허용 거리를 12에서 18픽셀로 늘립니다.
        support_depth = 18 if paint_support else 12
        probe_y = py + 4
        probe_x = np.polyval(self.line, probe_y)
        covered = any(y1 <= probe_y <= y2 and x1 <= probe_x <= x2 for x1, y1, x2, y2 in boxes)
        overlaps_vehicle = any(y1 <= py - 3 <= y2 and x1 <= np.polyval(self.line, py - 3) <= x2
                               for x1, y1, x2, y2 in boxes)
        if covered or (overlaps_vehicle and not np.any((py + 1 <= rows) & (rows <= py + support_depth))):
            return None, distance, "boundary_occluded"
        if abs(distance) < SIDE_MARGIN:
            return None, distance, "near_boundary"
        return ("right" if distance > 0 else "left"), distance, "observed"


class Crossing:
    def __init__(self, fps):
        self.required = math.ceil(HOLD_SECONDS * fps)
        self.gap_limit = math.ceil(MAX_UNCERTAIN_SECONDS * fps)
        self.stable = None
        self.stable_frame = None
        self.pending = None
        self.pending_frame = None

    def update(self, frame, side, lost_id):
        if lost_id or (self.stable is not None and frame - self.stable_frame > self.gap_limit):
            self.stable = self.stable_frame = None
            self.pending = self.pending_frame = None
        if side is None:
            self.pending = self.pending_frame = None
            return None
        if side == self.stable:
            self.stable_frame = frame
            self.pending = self.pending_frame = None
            return None
        if side != self.pending:
            self.pending, self.pending_frame = side, frame
        if frame - self.pending_frame + 1 < self.required:
            return None
        previous, previous_frame = self.stable, self.stable_frame
        self.stable, self.stable_frame = side, frame
        event = dict(from_side=previous, to_side=side, last_origin_frame=previous_frame,
                     first_confirmable_opposite_frame=self.pending_frame) if previous is not None else None
        self.pending = self.pending_frame = None
        return event


def draw_hud(canvas, font, number, fps, count, track_id, status):
    panel = Image.new("RGB", (560, 68), (18, 24, 28))
    draw = ImageDraw.Draw(panel)
    draw.text((12, 4), f"{EVENT_LABEL}  {count}건", font=font, fill=(218, 255, 228))
    draw.text((12, 34), f"ID {track_id}   F{number:04d}  {(number-1)/fps:.2f}초   {status}",
              font=font, fill=(245, 224, 140))
    canvas[8:76, 8:568] = cv2.cvtColor(np.asarray(panel), cv2.COLOR_RGB2BGR)


def save_original_clips(video, output, events, fps, shape, count):
    if not events:
        return
    folder = output / "original_clips"
    folder.mkdir()
    height, width = shape
    radius = round(fps * 3)
    capture = cv2.VideoCapture(str(video.resolve()))
    try:
        if not capture.isOpened():
            raise RuntimeError("후보 클립을 만들 원본을 열 수 없습니다.")
        for event in events:
            number = event["frame"]
            # 프레임은 1부터 셉니다. 끝 시각은 마지막 프레임의 재생이 끝나는 시각입니다.
            first = max(1, number - radius)
            last = min(count, number + radius - 1)
            clip = folder / f"candidate_{event['candidate']:03d}_ID{event['track_id']}_F{number:04d}.mp4"
            temporary = clip.with_suffix(".part.mp4")
            writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            try:
                if not capture.set(cv2.CAP_PROP_POS_FRAMES, first - 1) or not writer.isOpened():
                    raise RuntimeError(f"후보 클립을 열 수 없습니다: {clip}")
                for frame_no in range(first, last + 1):
                    ok, frame = capture.read()
                    if not ok or frame.shape[:2] != shape:
                        raise RuntimeError(f"후보 클립의 원본 프레임을 읽지 못했습니다: F{frame_no}")
                    writer.write(frame)
            finally:
                writer.release()
            verify_video(temporary, shape, fps, last - first + 1)
            temporary.replace(clip)
            event.update(clip_path=str(clip), clip_start_frame=first, clip_last_frame=last,
                         clip_start_s=(first - 1) / fps, clip_end_s_exclusive=last / fps,
                         clip_frames=last - first + 1, clip_duration_s=(last - first + 1) / fps,
                         clip_start_truncated=(first > number - radius), clip_end_truncated=(last < number + radius - 1),
                         clip_verified=True, clip_audio="none")
    finally:
        capture.release()


def render(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "lane_crossing_candidates.mp4"
    if path.exists():
        raise FileExistsError(path)
    cap = cv2.VideoCapture(str(args.video.resolve()))
    writer = cv2.VideoWriter()
    font = ImageFont.truetype(str(args.font), 23)
    model = load_lane_model(args.model, torch.device("cuda:0"))
    device = torch.device("cuda:0")
    timing = (torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True))
    cv2.setNumThreads(2)
    torch.set_num_threads(4)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height, count = (int(cap.get(k)) for k in (
        cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT, cv2.CAP_PROP_FRAME_COUNT
    ))
    track = read_track_replay(args.tracks, args.video, count, fps, width, height)
    end_frame = args.end_frame if args.end_frame is not None else count
    if not args.start_frame <= end_frame <= count:
        raise ValueError("검증 프레임 범위가 원본 영상 밖입니다.")
    selected_categories = {car["class"] for detections in track[args.start_frame - 1:end_frame]
                           for car in detections if car["id"] == args.track_id}
    if args.target_class not in selected_categories:
        raise ValueError(f"선택 구간에서 ID {args.track_id}의 {args.target_class} 추적 기록을 찾지 못했습니다.")
    scale = np.array([SIZE[0] / width, SIZE[1] / height])
    seed = (np.array(args.seed_line).reshape(2, 2) * scale).flatten()
    boundary = Boundary(seed)
    paint_rows = (max(143, int(min(seed[1], seed[3])) - 13), min(SIZE[1] - 2, int(max(seed[1], seed[3])) - 3))
    crossing = Crossing(fps)
    events = []
    actual_count = 0
    hold_labels = {
        "before_selection": "선택 대기", "after_selection": "검증 구간 종료",
        "track_id_missing": "판정 보류 · ID 없음",
        "track_class_changed": "판정 보류 · 차량 상자 불확실",
        "boundary_missing": "판정 보류 · 경계 미검출",
        "boundary_not_supported": "판정 보류 · 경계 근거 부족",
        "boundary_occluded": "판정 보류 · 경계 가림",
        "near_boundary": "판정 보류 · 경계에 근접",
    }
    try:
        if not cap.isOpened() or not writer.open(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)):
            raise RuntimeError("MP4를 열 수 없습니다.")
        with (output / "frames.jsonl").open("x", encoding="utf-8") as stream:
            for number, detections in enumerate(track, 1):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError(f"원본 프레임 {number}를 읽을 수 없습니다.")
                actual_count = number
                mask, _ = predict_lane(model, frame, device, SIZE, timing)
                seconds = (number - 1) / fps
                canvas = draw_overlay(frame, mask, detections, number, seconds, SIZE)
                vehicle = next((car for car in detections if car["id"] == args.track_id), None)
                boxes = [np.asarray(car["box"]) * np.tile(scale, 2) for car in detections]
                active = args.start_frame <= number <= end_frame
                rows = boundary.detect(mask, boxes) if active else None
                boundary_source = "model" if rows is not None else None
                if active and rows is None and args.yellow_support:
                    # 모델 근거가 부족할 때만 같은 경계 주변의 눈에 보이는 노란 도색을 확인합니다.
                    small = cv2.resize(frame, SIZE, interpolation=cv2.INTER_AREA)
                    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                    yellow = cv2.inRange(hsv, (12, 80, 100), (42, 255, 255))
                    # 이중선의 옆 줄과 차체 색을 피하려고 처음 지정한 선 가까이만 확인합니다.
                    rows = boundary.detect(yellow, boxes, row_limits=paint_rows, min_points=5, min_span=16, corridor=10)
                    if rows is not None:
                        boundary_source = "yellow_paint"
                point = None
                side = distance = None
                reason = "before_selection" if number < args.start_frame else "after_selection"
                if active:
                    if vehicle is None:
                        reason = "track_id_missing"
                    elif vehicle["class"] != args.target_class:
                        reason = "track_class_changed"
                    else:
                        x1, y1, x2, y2 = map(round, vehicle["box"])
                        point = ((x1 + x2) / 2, y2)
                        cv2.rectangle(canvas, (x1, y1), (x2, y2), (250, 100, 235), 3)
                        cv2.drawMarker(canvas, (round(point[0]), y2), (250, 100, 235), cv2.MARKER_CROSS, 23, 3)
                        if rows is None:
                            reason = "boundary_missing"
                        else:
                            side, distance, reason = boundary.classify(
                                np.array(point) * scale, rows, boxes, paint_support=boundary_source == "yellow_paint"
                            )
                if rows is not None:
                    endpoints = [tuple(np.rint(np.array([np.polyval(boundary.line, y), y]) / scale).astype(int))
                                 for y in (rows.min(), rows.max())]
                    cv2.line(canvas, *endpoints, (250, 215, 55), 3, cv2.LINE_AA)
                event = crossing.update(number, side, reason in {"track_id_missing", "track_class_changed"})
                if event is not None:
                    events.append(dict(label=EVENT_LABEL, source_video=args.video.name, candidate=len(events)+1,
                                       frame=number, time_s=seconds, track_id=args.track_id,
                                       direction=f"{event['from_side']}_to_{event['to_side']}",
                                       confirmation_boundary_source=boundary_source, **event))
                status = ("경계 왼쪽" if side == "left" else "경계 오른쪽") if side else hold_labels[reason]
                draw_hud(canvas, font, number, fps, len(events), args.track_id, status)
                writer.write(canvas)
                stream.write(json.dumps(dict(frame=number, time_s=seconds, target_id=args.track_id,
                                             target_point=point, side=side, distance_px=distance, status=reason,
                                             boundary_source=boundary_source,
                                             boundary_fit=boundary.line.tolist() if rows is not None else None,
                                             boundary_rows=rows.tolist() if rows is not None else None,
                                             stable_side=crossing.stable, count=len(events))) + "\n")
    finally:
        writer.release()
        cap.release()
    verify_video(path, (height, width), fps, actual_count)
    save_original_clips(args.video, output, events, fps, (height, width), count)
    (output / "candidates.json").write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(events, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--tracks", type=Path, default=DEFAULT_TRACK)
    parser.add_argument("--track-id", type=int, default=72)
    parser.add_argument("--target-class", default="car")
    parser.add_argument("--start-frame", type=int, default=170)
    parser.add_argument("--end-frame", type=int, help="마지막으로 판정할 프레임")
    parser.add_argument("--yellow-support", action="store_true", help="노란 경계에서 보이는 도색을 보조 근거로 사용합니다.")
    parser.add_argument("--seed-line", nargs=4, type=float, default=(770, 340, 1140, 637))
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/malgunbd.ttf"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.start_frame < 1 or args.seed_line[1] == args.seed_line[3] or args.seed_line[0] == args.seed_line[2]:
        parser.error("시작 프레임과 차선의 시작 좌표를 확인하세요.")
    render(args)


if __name__ == "__main__":
    main()
