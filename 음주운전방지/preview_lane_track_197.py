# 031  차선 마스크와 차량 ID를 영상에 겹치기
# 모델이 보는 작은 사진의 마스크를 원본 좌표로 되돌려 차량과 함께 봅니다.
# --video, --lane-model, --output을 씁니다. 기본 입력 크기는 384x240입니다.
# 오버레이 영상과 frames.jsonl을 남겨 해상도 비교와 경계 통과 판정에 씁니다.

"""원본 영상에 차량 추적 박스·ID와 차선 마스크를 함께 저장합니다."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from track_preview import ROOT, VEHICLES
from train_lane_smoke_197 import IMAGE_SIZE, THRESHOLD, new_model


DEFAULT_VIDEO = ROOT / "videos" / "비접촉_사고유발_영상_낮.mp4"
DEFAULT_LANE = ROOT / "output" / "lane_transfer_197_run" / "imagenet_v1_recalibrated.pt"


def load_lane_model(path, device):
    # 학습 스크립트와 같은 구조를 만들고 가중치와 BatchNorm 통계를 함께 읽습니다.
    state = torch.load(path, map_location=device, weights_only=True)
    if (tuple(state["image_size"]) not in (IMAGE_SIZE, (640, 400)) or state["normalization"] != "RGB / 127.5 - 1"
            or state["threshold"] != THRESHOLD):
        raise ValueError("체크포인트의 입력 크기·정규화·임계값을 확인하세요.")
    model = new_model(device)
    model.load_state_dict(state["model_state_dict"])
    return model.eval()


@torch.inference_mode()
def predict_lane(model, frame, device, size, timing):
    # 입력 크기를 비교할 때도 BGR→RGB와 [-1, 1] 정규화 순서는 그대로입니다.
    small = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    image = torch.from_numpy(rgb).permute(2, 0, 1).float() / 127.5 - 1
    image = image.unsqueeze(0).to(device)
    start, end = timing
    start.record()
    logits = model(image)["out"]
    end.record()
    mask = (logits[0, 0].sigmoid() >= THRESHOLD).cpu().numpy().astype(np.uint8)
    # CPU로 마스크를 가져온 뒤이므로 GPU의 모델 forward가 끝난 시각을 읽을 수 있습니다.
    return mask, start.elapsed_time(end)


def track_vehicles(model, frame, vehicle_ids, device):
    # 미리보기와 같은 차량 클래스·ByteTrack·신뢰도 설정으로 프레임 사이 ID를 이어갑니다.
    boxes = model.track(source=frame, tracker="bytetrack.yaml", persist=True, conf=.1,
                        classes=vehicle_ids, device=device, verbose=False)[0].boxes.cpu()
    ids = boxes.id.tolist() if boxes.id is not None else [None] * len(boxes)
    return [
        {"id": int(track_id) if track_id is not None else None, "box": xyxy,
         "class": model.names[int(category)], "confidence": confidence}
        for track_id, xyxy, category, confidence in zip(
            ids, boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist(), strict=True
        )
    ]


def draw_overlay(frame, mask, detections, number, seconds, lane_size=IMAGE_SIZE):
    height, width = frame.shape[:2]
    # 이진 마스크를 최근접 보간으로 원본 영상 크기에 되돌린 뒤 초록색으로 표시합니다.
    selected = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST).astype(bool)
    canvas = frame.copy()
    color = np.array([40, 240, 60], dtype=np.float32)
    canvas[selected] = (frame[selected] * .62 + color * .38).astype(np.uint8)
    for entry in detections:
        x1, y1, x2, y2 = map(int, entry["box"])
        track_id = entry["id"]
        box_color = (0, 224, 255) if track_id is not None else (160, 160, 160)
        caption = f"{entry['class']} ID {track_id if track_id is not None else '--'}"
        cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2)
        cv2.putText(canvas, caption, (x1, max(23, y1 - 5)), 0, .57, (20, 20, 20), 3, cv2.LINE_AA)
        cv2.putText(canvas, caption, (x1, max(23, y1 - 5)), 0, .57, box_color, 1, cv2.LINE_AA)
    cv2.rectangle(canvas, (10, 10), (550, 43), (22, 22, 22), -1)
    cv2.putText(canvas, f"F{number:04d} | {seconds:05.2f}s  {lane_size[0]}x{lane_size[1]}  LANE + BYTETRACK",
                (19, 33), 0, .63, (125, 240, 145), 2, cv2.LINE_AA)
    return canvas


def verify_video(path, shape, fps, expected_count):
    capture = cv2.VideoCapture(str(path))
    count = 0
    try:
        if not capture.isOpened() or abs(capture.get(cv2.CAP_PROP_FPS) - fps) > .01:
            raise RuntimeError("저장한 MP4의 FPS를 확인할 수 없습니다.")
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame.shape[:2] != shape:
                raise RuntimeError("저장한 MP4의 해상도가 원본과 다릅니다.")
            count += 1
    finally:
        capture.release()
    if count != expected_count:
        raise RuntimeError(f"저장한 MP4의 프레임 수가 다릅니다: {count} / {expected_count}")


def read_track_replay(path, video, count, fps, width, height):
    # 같은 원본의 차량 기록만 읽어서 두 차선 모델에 똑같이 표시합니다.
    summary = json.loads((path.parent / "summary.json").read_text(encoding="utf-8"))
    if (Path(summary["source"]).resolve() != video.resolve() or summary["frames"] != count
            or summary["source_fps"] != fps or summary["resolution"] != [width, height]):
        raise ValueError("차량 추적 기록이 이 원본 영상과 다릅니다.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["frame"] for row in rows] != list(range(1, count + 1)):
        raise ValueError("차량 추적 기록의 프레임 번호가 맞지 않습니다.")
    return [row["vehicles"] for row in rows]


def render(args, output, log):
    if not torch.cuda.is_available():
        raise RuntimeError("차선 모델에 사용할 CUDA GPU가 없습니다.")
    device = torch.device("cuda:0")
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    cv2.setNumThreads(2)
    lane = load_lane_model(args.lane_model, device)
    timing = (torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True))
    if args.track_replay is None:
        yolo = YOLO(str(args.yolo))
        vehicle_ids = [i for i, name in yolo.names.items() if name in VEHICLES]
    capture = cv2.VideoCapture(str(args.video.resolve()))
    writer = cv2.VideoWriter()
    number = 0
    previous = None
    blank_frames = []
    forward_times = []
    time_counts = dict(decode=0.0, lane=0.0, tracking=0.0, overlay_and_encode=0.0)
    temporary = output / "redbox_overlay_work.mp4"
    final = output / "redbox_overlay.mp4"
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        width, height = (int(capture.get(prop)) for prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
        source_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not capture.isOpened() or min(fps, width, height) <= 0:
            raise RuntimeError(f"원본 영상을 열 수 없습니다: {args.video}")
        replay = None
        if args.track_replay is not None:
            replay = read_track_replay(args.track_replay, args.video, source_count, fps, width, height)
        if not writer.open(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)):
            raise RuntimeError(f"출력 MP4를 열 수 없습니다: {temporary}")
        start = perf_counter()
        while True:
            tick = perf_counter()
            ok, frame = capture.read()
            time_counts["decode"] += perf_counter() - tick
            if not ok:
                break
            number += 1
            seconds = (number - 1) / fps
            tick = perf_counter()
            mask, forward_ms = predict_lane(lane, frame, device, args.lane_size, timing)
            time_counts["lane"] += perf_counter() - tick
            forward_times.append(forward_ms)
            tick = perf_counter()
            vehicles = replay[number - 1] if replay is not None else track_vehicles(
                yolo, frame, vehicle_ids, args.tracker_device
            )
            time_counts["tracking"] += perf_counter() - tick
            tick = perf_counter()
            writer.write(draw_overlay(frame, mask, vehicles, number, seconds, args.lane_size))
            time_counts["overlay_and_encode"] += perf_counter() - tick
            # 전후 프레임의 마스크 겹침은 급변 구간을 찾는 용도로 기록합니다.
            iou = None
            if previous is not None:
                union = np.count_nonzero(previous | mask)
                iou = np.count_nonzero(previous & mask) / union if union else 1.0
            previous = mask
            pixels = int(mask.sum())
            if pixels == 0:
                blank_frames.append(number)
            entry = {
                "frame": number, "time_s": seconds, "lane_pixels": pixels,
                "lane_fraction": pixels / mask.size, "lane_forward_ms": forward_ms,
                "adjacent_lane_iou": iou, "vehicles": vehicles,
            }
            if args.lane_size == IMAGE_SIZE:
                entry["lane_pixels_384x240"] = pixels
            log.write(json.dumps(entry) + "\n")
        writer.release()
        elapsed = perf_counter() - start
    finally:
        capture.release()
        writer.release()
    if number < 1 or (source_count > 0 and number != source_count):
        raise RuntimeError(f"원본 처리 프레임 수가 일치하지 않습니다: {number} / {source_count}")
    verify_video(temporary, (height, width), fps, number)
    temporary.replace(final)
    summary = {
        "source": str(args.video.resolve()), "video": str(final), "frames": number,
        "source_fps": fps, "resolution": [width, height], "processing_seconds": elapsed,
        "processing_fps": number / elapsed, "stage_seconds": time_counts,
        "gpu": torch.cuda.get_device_name(device),
        "tracker_device": "replay" if replay is not None else args.tracker_device,
        "track_replay": str(args.track_replay.resolve()) if replay is not None else None,
        "lane_checkpoint": str(args.lane_model.resolve()), "lane_threshold": THRESHOLD,
        "lane_input_size": args.lane_size, "blank_frames": blank_frames,
        "lane_forward_mean_ms": float(np.mean(forward_times)),
        "lane_forward_median_ms": float(np.median(forward_times)),
        "lane_pipeline_mean_ms": 1000 * time_counts["lane"] / number,
        "frame_time_basis": "(frame - 1) / source_fps", "audio": "none",
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    (output / "summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--lane-model", type=Path, default=DEFAULT_LANE)
    parser.add_argument("--yolo", type=Path, default=ROOT / "yolo26n.pt")
    parser.add_argument("--tracker-device", choices=("0", "cpu"), default="0")
    parser.add_argument("--track-replay", type=Path, help="기존 frames.jsonl의 차량 기록을 재사용합니다.")
    parser.add_argument("--lane-size", choices=("384x240", "640x400"), default="384x240")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.lane_size = tuple(map(int, args.lane_size.split("x")))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "frames.jsonl").open("x", encoding="utf-8") as log:
        render(args, output, log)


if __name__ == "__main__":
    main()
