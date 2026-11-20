# 032  두 입력 크기의 같은 프레임 비교하기
# 영상과 추적 조건을 맞춰야 선 굵기나 깜빡임의 차이를 비교할 수 있습니다.
# --output 아래 384x240, 640x400 두 실행의 영상·summary.json·frames.jsonl이 필요합니다.
# side_by_side.mp4와 comparison.json을 저장해 재학습 전후를 확인합니다.

"""두 입력 크기의 오버레이를 같은 프레임끼리 나란히 저장합니다."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from convert_lane_masks_197 import encode
from preview_lane_track_197 import verify_video


SAMPLES = (1, 36, 54, 260, 261, 360, 364, 368, 372, 373, 377, 378, 393, 396)


def read_run(path):
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    frames = [json.loads(line) for line in (path / "frames.jsonl").read_text(encoding="utf-8").splitlines()]
    if [frame["frame"] for frame in frames] != list(range(1, summary["frames"] + 1)):
        raise ValueError(f"프레임 번호 또는 개수가 맞지 않습니다: {path}")
    return summary, frames


def compose(output, summaries):
    fps = summaries[0]["source_fps"]
    count = summaries[0]["frames"]
    width, height = summaries[0]["resolution"]
    path = output / "side_by_side.mp4"
    stills = output / "matched_frames"
    stills.mkdir(exist_ok=True)
    # 각 패널을 원본 해상도 그대로 붙여 하나의 프레임을 만듭니다.
    captures = [cv2.VideoCapture(summary["video"]) for summary in summaries]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width * 2, height))
    try:
        if not writer.isOpened() or not all(cap.isOpened() for cap in captures):
            raise RuntimeError("비교용 MP4 입출력을 열 수 없습니다.")
        for number in range(1, count + 1):
            pair = [cap.read() for cap in captures]
            if not all(ok and frame.shape[:2] == (height, width) for ok, frame in pair):
                raise RuntimeError(f"짝이 맞는 프레임을 읽을 수 없습니다: F{number}")
            joined = np.hstack([frame for _, frame in pair])
            writer.write(joined)
            if number in SAMPLES:
                still = stills / f"frame_{number:04d}.jpg"
                still.write_bytes(encode(still, joined))
    finally:
        writer.release()
        for cap in captures:
            cap.release()
    verify_video(path, (height, width * 2), fps, count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="384x240과 640x400 결과가 들어 있는 폴더")
    parser.add_argument("--compare-checkpoints", action="store_true", help="서로 다른 두 체크포인트를 비교합니다.")
    args = parser.parse_args()
    output = args.output.resolve()
    names = ("384x240", "640x400")
    runs = [read_run(output / name) for name in names]
    summaries, logs = zip(*runs, strict=True)
    for key in ("source", "frames", "source_fps", "resolution", "lane_threshold", "tracker_device"):
        if summaries[0][key] != summaries[1][key]:
            raise ValueError(f"비교 조건 불일치: {key}")
    if (summaries[0]["lane_checkpoint"] != summaries[1]["lane_checkpoint"]) != args.compare_checkpoints:
        raise ValueError("두 체크포인트의 일치 여부가 비교 옵션과 맞지 않습니다.")
    if [s["lane_input_size"] for s in summaries] != [[384, 240], [640, 400]]:
        raise ValueError("두 결과의 차선 입력 크기가 맞지 않습니다.")
    identical = sum(left["vehicles"] == right["vehicles"] for left, right in zip(*logs, strict=True))
    if args.compare_checkpoints and identical != summaries[0]["frames"]:
        raise ValueError("체크포인트 비교에는 동일한 차량 추적 기록이 필요합니다.")
    compose(output, summaries)
    comparison = {
        "identical_vehicle_records": identical,
        "compared_frames": summaries[0]["frames"],
        "runs": {
            name: {
                "blank_frames": summary["blank_frames"],
                "processing_fps": summary["processing_fps"],
                "lane_forward_mean_ms": summary["lane_forward_mean_ms"],
                "lane_forward_median_ms": summary["lane_forward_median_ms"],
                "lane_pipeline_mean_ms": summary["lane_pipeline_mean_ms"],
            }
            for name, summary in zip(names, summaries, strict=True)
        },
        "selected_frames": list(SAMPLES),
    }
    text = json.dumps(comparison, ensure_ascii=False, indent=2)
    (output / "comparison.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
