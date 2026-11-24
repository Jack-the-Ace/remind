# 047  블랙박스 전·후방 표본 조사와 원본 복사
# 새 영상의 여러 시점 이미지와 해시를 만들어 같은 장면을 골라냅니다.
# review는 조사 결과만 저장하고, copy는 선별 목록에 적힌 원본만 videos에 복사합니다.
# 출력 목록과 이미지로 정지선·OCR·추적 검증 구간을 고릅니다.

import argparse
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import hashlib
import json
from pathlib import Path
import re
import shutil

import cv2
import numpy as np

app = import_module("041_redbox_mvp")
FORMATS = {".avi", ".mp4", ".mov", ".mkv", ".wmv", ".m4v", ".mts", ".ts", ".webm"}
WIDTH, HEIGHT = 360, 198


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def jpg(path, image):
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 87])
    if not ok:
        raise RuntimeError("JPG 저장에 실패했습니다.")
    with path.open("xb") as stream:
        stream.write(data)


def review_file(number, path):
    row = dict(index=number, path=str(path), sha256=digest(path), cameras={})
    views = []
    cameras = ("front", "rear") if path.suffix.lower() == ".avi" else ("front",)
    for camera in cameras:
        frames = []
        status = row["cameras"][camera] = {"times": []}
        try:
            with app.capture(path, camera) as cap:
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                if total <= 0 or fps <= 0:
                    raise ValueError("영상 길이를 확인할 수 없습니다.")
                status.update(frames=total, fps=fps)
                for fraction in (.07, .28, .50, .72, .93):
                    index = round((total-1)*fraction)
                    if not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
                        continue
                    ok, frame = cap.read()
                    if ok:
                        seconds = index/fps
                        tile = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
                        cv2.putText(tile, f"{number:03d} {camera} {seconds:.2f}s", (7, 19),
                                    cv2.FONT_HERSHEY_SIMPLEX, .54, (0, 0, 0), 4, cv2.LINE_AA)
                        cv2.putText(tile, f"{number:03d} {camera} {seconds:.2f}s", (7, 19),
                                    cv2.FONT_HERSHEY_SIMPLEX, .54, (255, 255, 255), 1, cv2.LINE_AA)
                        frames.append(tile)
                        status["times"].append(seconds)
        except (OSError, ValueError, cv2.error) as error:
            status["error"] = str(error)
        while len(frames) < 5:
            frames.append(np.zeros((HEIGHT, WIDTH, 3), np.uint8))
        views.append(np.hstack(frames))
    return row, views


def review(root, output):
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in FORMATS)
    output.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    rows, tiles = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for row, views in pool.map(review_file, range(1, len(paths)+1), paths):
            rows.append(row)
            tiles.extend(views)
            if len(rows) % 4 == 0 or len(rows) == len(paths):
                jpg(output/f"review_{(len(rows)-1)//4+1:02d}.jpg", np.vstack(tiles))
                tiles.clear()
    with (output/"inventory.json").open("x", encoding="utf-8") as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
    print(len(rows), "개 파일 조사")


def copy(root, selection, output):
    candidates = json.loads(selection.read_text(encoding="utf-8-sig"))
    destination = (app.ROOT/"videos").resolve()
    root = root.resolve()
    existing = {digest(path):path.name for path in destination.iterdir()
                if path.is_file() and path.suffix.lower() in FORMATS}
    output.mkdir(parents=True, exist_ok=False)
    with (output/"copies.jsonl").open("x", encoding="utf-8") as log:
        for candidate in candidates:
            source = (root/candidate["source"]).resolve(strict=True)
            if not source.is_relative_to(root) or source.suffix.lower() not in FORMATS or not source.is_file():
                raise ValueError(f"원본 영상 경로를 확인하세요: {source}")
            sha = digest(source)
            if sha in existing:
                record = dict(status="duplicate", destination=existing[sha])
            else:
                match = re.match(r"(\d{8})-(\d{2})h(\d{2})m(\d{2})s", source.name)
                stem = f"BB_{match[1]}_{match[2]}{match[3]}{match[4]}" if match else "BB_날짜미상"
                index = 1
                while True:
                    name = stem+(f"_{index:02d}" if index > 1 else "")+source.suffix.lower()
                    target = destination/name
                    try:
                        stream = target.open("xb")
                        break
                    except FileExistsError:
                        index += 1
                try:
                    with stream, source.open("rb") as original:
                        shutil.copyfileobj(original, stream)
                    if digest(target) != sha:
                        raise RuntimeError(f"복사본 해시가 다릅니다: {target}")
                except BaseException:
                    # 이번 실행에서 새로 만든 불완전한 복사본만 정리합니다.
                    target.unlink()
                    raise
                existing[sha] = name
                record = dict(status="copied_and_verified", destination=name)
            log.write(json.dumps(dict(candidate, sha256=sha, **record), ensure_ascii=False)+"\n")
            log.flush()
            print(record["destination"], record["status"])


def main():
    parser = argparse.ArgumentParser(description="블랙박스 원본 조사와 선별 복사")
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path, help="있으면 원본 상대경로와 용도가 적힌 JSON 목록만 복사")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error("신규 블랙박스 폴더가 없습니다.")
    if args.selection:
        copy(args.root, args.selection, args.output)
    else:
        review(args.root, args.output)


if __name__ == "__main__":
    main()
