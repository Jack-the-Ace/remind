# 048  RedBox 분석 시간 비교
# 같은 AVI와 시작 위치로 5초·15초 분석을 반복해 단계별 시간과 GPU 장치를 기록합니다.
# --baseline에는 개선 전 041 사본을, --output에는 Git에서 제외되는 새 폴더를 지정합니다.
# 이미지와 이벤트 로그도 남겨 처리 속도와 기존 결과를 함께 대조합니다.

import argparse
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from importlib import import_module
import json
from pathlib import Path
from runpy import run_path
from time import perf_counter

import cv2
import torch
from ultralytics.trackers import track as ultralytics_track

from track_preview import ROOT


SPEC = dict(video="BB_20261123_133631.avi", at=37, point=[1030, 790],
            line=[1349, 847, 1465, 940], stop_line=[565, 915, 1380, 895])


class Profile:
    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.seconds = Counter()
        self.calls = Counter()
        self.devices = {}
        self.inside_clip = False

    @contextmanager
    def measure(self, name):
        started = perf_counter()
        try:
            yield
        finally:
            self.seconds[name] += perf_counter()-started
            self.calls[name] += 1

    def wrap(self, name, original):
        @wraps(original)
        def measured(*args, **kwargs):
            with self.measure(name):
                return original(*args, **kwargs)
        return measured

    def install(self):
        app = self.app
        original_capture = app["capture"]
        original_writer = cv2.VideoWriter
        original_track = app["track_vehicles"]
        original_lane = app["predict_lane"]
        original_ocr = app["ocr"]
        original_save_clips = app["crossing_module"].save_original_clips
        original_verify = app["verify_video"]
        original_sample = app["VehicleInfo"].sample
        original_tracker_end = ultralytics_track.on_predict_postprocess_end

        @contextmanager
        def capture(*args, **kwargs):
            with original_capture(*args, **kwargs) as cap:
                if self.inside_clip:
                    yield cap
                else:
                    class Source:
                        def __getattr__(inner, name):
                            if name == "read":
                                return self.wrap("source_read", cap.read)
                            return getattr(cap, name)
                    yield Source()

        def writer(path, *args, **kwargs):
            out = original_writer(path, *args, **kwargs)
            name = Path(path).name
            if name not in {"hud.mp4", "replay.webm"}:
                return out
            stage = "mp4_write" if name == "hud.mp4" else "webm_write"
            class Writer:
                def __getattr__(inner, key):
                    value = getattr(out, key)
                    return self.wrap(stage, value) if key in {"write", "release"} else value
            return Writer()

        def track(yolo, *args, **kwargs):
            byte_started = self.seconds["bytetrack"]
            with self.measure("yolo_and_tracking"):
                result = original_track(yolo, *args, **kwargs)
            self.devices["yolo"] = str(yolo.predictor.device)
            if self.seconds["bytetrack"] == byte_started:
                self.calls["without_tracker_callback"] += 1
            return result

        def lane(model, frame, device, size, timing):
            with self.measure("lane_model"):
                mask, ms = original_lane(model, frame, device, size, timing)
            self.seconds["lane_cuda_forward"] += ms/1000
            self.devices["lane"] = str(next(model.parameters()).device)
            return mask, ms

        def ocr():
            with self.measure("ocr_load"):
                reader, status = original_ocr()
            self.devices["easyocr"] = str(reader.device) if reader else status
            return reader, status

        def sample(info, *args, **kwargs):
            if info.reader is None or len(info.ocr_frames) >= 12:
                return original_sample(info, *args, **kwargs)
            with self.measure("ocr_sample"):
                return original_sample(info, *args, **kwargs)

        def save_clips(*args, **kwargs):
            self.inside_clip = True
            try:
                with self.measure("evidence_clips"):
                    return original_save_clips(*args, **kwargs)
            finally:
                self.inside_clip = False

        app.update(capture=capture, track_vehicles=track, predict_lane=lane, ocr=ocr,
                   verify_video=self.wrap("media_verify", original_verify))
        for key in ("new_tracker", "draw_hud", "draw_event_float"):
            app[key] = self.wrap(key, app[key])
        app["VehicleInfo"].sample = sample
        app["crossing_module"].save_original_clips = save_clips
        ultralytics_track.on_predict_postprocess_end = self.wrap("bytetrack", original_tracker_end)
        cv2.VideoWriter = writer

    def run(self, duration, output, name):
        self.reset()
        begin = perf_counter()
        result = self.app["analyze"](dict(SPEC, duration=duration), output/name, web=True)
        elapsed = perf_counter()-begin
        self.seconds["yolo"] = self.seconds["yolo_and_tracking"]-self.seconds["bytetrack"]
        self.seconds["hud_render"] = self.seconds["draw_hud"]+self.seconds["draw_event_float"]
        frames = result["analyzed_frames"]
        return dict(name=name, duration=duration, frames=frames, seconds=elapsed, fps=frames/elapsed,
                    phases=dict(self.seconds), calls=dict(self.calls), devices=self.devices,
                    events=[dict(frame=e["frame"], label=e["label"]) for e in result["events"]],
                    ocr_samples=len(result["ocr_frames"]))


def main():
    parser = argparse.ArgumentParser(description="RedBox 5초·15초 분석 시간 측정")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--durations", nargs="+", type=int, default=[5, 15, 5, 15])
    args = parser.parse_args()
    cv2.setNumThreads(2)
    torch.set_num_threads(min(4, torch.get_num_threads()))
    app = (run_path(str(args.baseline))["analyze"].__globals__ if args.baseline
           else vars(import_module("041_redbox_mvp")))
    args.output.mkdir(parents=True, exist_ok=False)
    profile = Profile(app)
    profile.install()
    with (args.output/"timings.jsonl").open("x", encoding="utf-8") as stream:
        for i, duration in enumerate(args.durations, 1):
            row = profile.run(duration, args.output, f"{i:02}_{duration}s")
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
            stream.flush()
            print(row["name"], f"{row['seconds']:.2f}s / {row['fps']:.2f} FPS",
                  row["devices"], f"{row['ocr_samples']} OCR", flush=True)


if __name__ == "__main__":
    main()
