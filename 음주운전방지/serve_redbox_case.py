"""RedBox 사건 화면을 현재 PC에서 실행합니다."""

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import cv2


ROOT = Path(__file__).resolve().parent
APP = ROOT / "redbox_case"
DEFAULT_CASE = ROOT / "output/lane_video_197_other_sources/uturn_paint_verified/candidates.json"
ASSETS = ROOT / "output/lane_video_197_case_preview"


def build_preview(source, expected_frames):
    # 원본 MP4의 MPEG-4 영상은 브라우저 호환성이 낮아 재생용 WebM을 따로 만듭니다.
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
    ASSETS.mkdir(parents=True, exist_ok=True)
    preview = ASSETS / f"{digest}.webm"
    poster = ASSETS / f"{digest}.jpg"
    if preview.is_file() and poster.is_file():
        return preview, poster
    with tempfile.TemporaryDirectory(dir=ASSETS) as folder:
        staged = Path(folder) / "preview.webm"
        capture = cv2.VideoCapture(str(source))
        writer = cv2.VideoWriter()
        count = 0
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            width, height = (int(capture.get(prop)) for prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
            if not capture.isOpened() or fps <= 0 or min(width, height) <= 0:
                raise ValueError("원본 클립을 열 수 없습니다.")
            if not writer.open(str(staged), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"VP80"), fps, (width, height)):
                raise RuntimeError("재생용 WebM을 생성할 수 없습니다.")
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if count == 0:
                    ok, image = cv2.imencode(".jpg", frame)
                    if not ok:
                        raise RuntimeError("첫 프레임 이미지를 저장할 수 없습니다.")
                    (Path(folder) / "poster.jpg").write_bytes(image.tobytes())
                writer.write(frame)
                count += 1
        finally:
            capture.release()
            writer.release()
        if count != expected_frames:
            raise ValueError("후보 로그와 원본 클립의 프레임 수가 다릅니다.")
        staged.replace(preview)
        (Path(folder) / "poster.jpg").replace(poster)
    return preview, poster


def load_case(path):
    events = json.loads(path.read_text(encoding="utf-8-sig"))
    event = next((entry for entry in events if entry["candidate"] == 1), None)
    if event is None:
        raise ValueError("후보 1번을 찾을 수 없습니다.")
    # 저장된 절대 경로가 달라져도 JSON 옆 original_clips에서 원본을 찾습니다.
    source = path.parent / "original_clips" / Path(event["clip_path"]).name
    if not source.is_file():
        raise FileNotFoundError(source)
    relative = event["time_s"] - event["clip_start_s"]
    if not all(math.isfinite(v) for v in (relative, event["clip_duration_s"])) or not 0 <= relative < event["clip_duration_s"]:
        raise ValueError("후보 시각이 클립 범위를 벗어납니다.")
    data = {
        "label": event["label"],
        "id": event["candidate"],
        "trackId": event["track_id"],
        "sourceVideo": event["source_video"],
        "originalTime": event["time_s"],
        "clipTime": round(relative, 6),
        "clipDuration": event["clip_duration_s"],
        "downloadName": source.name,
        "sizeBytes": source.stat().st_size,
        "draft": {
            "report-type": "자동차·교통위반",
            "location": "확인 필요",
            "description": "첨부 영상에서 전방의 검은색 차량이 왼쪽으로 방향을 틀어 노란색 이중선이 표시된 경계를 오른쪽에서 왼쪽으로 가로지르는 모습이 보입니다.",
            "plate": "확인 필요",
            "incident-date": "확인 필요",
            "incident-time": "확인 필요",
        },
    }
    return source, data, build_preview(source, int(event["clip_frames"]))


class CaseHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.serve(False)

    def do_HEAD(self):
        self.serve(True)

    def serve(self, head_only):
        route = urlsplit(self.path).path
        if route == "/case-data.json":
            payload = self.server.case_data
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)
            return
        entry = self.server.files.get(route)
        if entry is None:
            self.send_error(404)
            return
        path, media_type = entry
        size = path.stat().st_size
        first, last = 0, size - 1
        byte_range = self.headers.get("Range")
        if byte_range:
            valid = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
            if valid and (valid[1] or valid[2]):
                if valid[1]:
                    first = int(valid[1])
                    last = min(last, int(valid[2])) if valid[2] else last
                else:
                    first = max(0, size - int(valid[2]))
            else:
                first = size
            if first > last:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if byte_range else 200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(last - first + 1))
        self.send_header("Accept-Ranges", "bytes")
        if route == "/download":
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        if byte_range:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        if head_only:
            return
        try:
            with path.open("rb") as file:
                if not byte_range:
                    shutil.copyfileobj(file, self.wfile)
                else:
                    file.seek(first)
                    remaining = last - first + 1
                    while remaining:
                        chunk = file.read(min(remaining, 64 * 1024))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # 영상 탐색 시 브라우저가 이전 범위 요청을 취소할 수 있습니다.
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    source, data, (preview, poster) = load_case(DEFAULT_CASE)
    with ThreadingHTTPServer(("127.0.0.1", args.port), CaseHandler) as server:
        server.case_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        server.files = {
            "/": (APP / "index.html", "text/html; charset=utf-8"),
            "/case.css": (APP / "case.css", "text/css; charset=utf-8"),
            "/case.js": (APP / "case.js", "text/javascript; charset=utf-8"),
            "/clip.webm": (preview, "video/webm"),
            "/poster.jpg": (poster, "image/jpeg"),
            "/download": (source, "video/mp4"),
        }
        print(f"RedBox 사건 상세  http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
