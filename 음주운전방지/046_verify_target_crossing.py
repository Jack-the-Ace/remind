# 046  실제 영상에서 차량 선택·추적·집계를 다시 확인하기
# 정해 둔 영상과 클릭 좌표를 사용해 041과 같은 분석을 반복합니다.
# 원본 YOLO 상자와 ByteTrack 상자를 따로 저장해 어디서 놓치는지 비교합니다.
# --output에는 새 폴더를 지정합니다. 저장 영상과 로그는 프레임 단위 검토에 씁니다.

"""041과 같은 경로로 지정 차량의 실제 추적·집계를 재실행합니다."""

import argparse
from importlib import import_module
import json
from pathlib import Path
from runpy import run_path

import torch

import track_preview

app = import_module("041_redbox_mvp")
ROOT = track_preview.ROOT
DAY = "비접촉_사고유발_영상_낮.mp4"
DAY_LINE = [770, 340, 1140, 637]
DEFAULT_CASES = {
    "01": dict(video="BB_20260111_125520.avi", at=6.2, duration=10,
               point=[520, 805], line=[890, 775, 705, 984]),
    "09": dict(video=DAY, at=184/30, duration=7.1, point=[1408, 503], line=DAY_LINE),
    "10": dict(video=DAY, at=223/30, duration=5.8, point=[1142, 347], line=DAY_LINE),
}
NIGHT = {
    "video": "비접촉_사고유발_영상_밤.mp4", "at": 0, "duration": 23,
    "point": [690, 560], "line": [1080, 620, 1345, 800], "no_ocr": True,
}


def record_detections(output, data, *, cpu=False, reference_target=None):
    model, classes = app.new_tracker()
    raw = []

    def before_tracking(predictor):
        # ByteTrack이 결과를 바꾸기 전에 검출기 출력만 복사합니다.
        boxes = predictor.results[0].boxes.cpu()
        raw[:] = [
            dict(box=xyxy, confidence=confidence, **{"class": model.names[int(category)]})
            for xyxy, confidence, category in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), strict=True)
        ]

    model.add_callback("on_predict_postprocess_end", before_tracking)
    original_new_tracker, original_track, original_target = app.new_tracker, app.track_vehicles, app.Target
    output.parent.mkdir(parents=True, exist_ok=True)
    with (output.with_suffix(".detections.jsonl").open("x", encoding="utf-8") as stream,
          output.with_suffix(".decisions.jsonl").open("x", encoding="utf-8") as decisions):
        seen = 0

        def track(yolo, frame, ids, device):
            nonlocal seen
            detections = original_track(yolo, frame, ids, "cpu" if cpu else device)
            seen += 1
            stream.write(json.dumps(dict(offset=seen-1, raw=raw, tracked=detections))+"\n")
            return detections

        app.new_tracker = lambda: (model, classes)
        app.track_vehicles = track
        def target_with_log():
            return original_target(diagnostic=lambda row: decisions.write(json.dumps(row)+"\n"))

        app.Target = reference_target or target_with_log
        try:
            return app.analyze(dict(data, no_ocr=True), output)
        finally:
            app.new_tracker, app.track_vehicles, app.Target = original_new_tracker, original_track, original_target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", type=Path, help="기본 4개 외에 기존 사례 목록 JSON을 지정합니다.")
    parser.add_argument("--reference-target", type=Path, help="비교에 쓸 이전 track_preview.py 사본입니다.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", default=["01", "09", "10", "night"])
    args = parser.parse_args()
    cases = DEFAULT_CASES.copy()
    if args.specs:
        specs = json.loads(args.specs.read_text(encoding="utf-8"))
        cases.update({f"{index:02}": value for index, value in enumerate(specs, 1)})
    cases["night"] = NIGHT
    if missing := set(args.cases) - cases.keys():
        parser.error(f"알 수 없는 사례: {', '.join(sorted(missing))}")
    args.output.mkdir(parents=True, exist_ok=False)
    reference = run_path(str(args.reference_target))["Target"] if args.reference_target else None
    print("CUDA:", torch.cuda.is_available(), flush=True)
    for name in args.cases:
        result = record_detections(args.output / name, cases[name], cpu=name == "night", reference_target=reference)
        print(name, result["confirmed_frames"], "/", result["analyzed_frames"],
              result["event_total"], "건", flush=True)


if __name__ == "__main__":
    main()
