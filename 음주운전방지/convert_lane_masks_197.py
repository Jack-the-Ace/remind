# 024  차선 좌표를 흑백 마스크로 바꾸기
# 선을 한 줄씩 연결해 서로 다른 경계가 한 영역으로 채워지지 않게 합니다.
# --data-root와 --output을 지정합니다. --samples 2215110으로 한 장부터 봅니다.
# 기본 굵기 5픽셀의 PNG와 manifest.csv를 만들어 데이터 분할에 씁니다.

"""AI Hub 197 daylight JPG와 JSON에서 차선 경로 마스크를 만듭니다."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np


FIELDS = ("jpg", "json", "mask", "width", "height", "lane_count", "thickness",
          "white_pixels", "status", "detail")


class SampleError(ValueError):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status


def inventory(root):
    section = Path("1900_1200/daylight")
    images = defaultdict(list)
    labels = defaultdict(list)
    errors = []
    for folder in (root / "원천데이터" / section, root / "라벨링데이터" / section):
        if not folder.is_dir():
            raise FileNotFoundError(folder)
    for jpg in sorted((root / "원천데이터" / section).rglob("*.jpg")):
        images[jpg.name.casefold()].append(jpg)
    for path in sorted((root / "라벨링데이터" / section).rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
            name = doc["image"]["file_name"]
            if not isinstance(name, str) or not name.strip():
                raise ValueError("image.file_name 오류")
            labels[Path(name).name.casefold()].append((path, doc))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(dict(json=path, status="JSON 오류", detail=str(exc)))
    return images, labels, errors


def read_image(path, mode):
    # 한글 경로도 열 수 있게 파일을 바이트로 읽은 뒤 OpenCV로 풉니다.
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(data, mode) if data.size else None
    if image is None:
        raise ValueError(f"이미지를 열 수 없습니다: {path}")
    return image


def lane_points(annotation, width, height):
    try:
        coords = [[p["x"], p["y"]] for p in annotation["data"]]
        pts = np.asarray(coords)
        if pts.ndim != 2 or pts.shape[0] < 2 or pts.dtype.kind not in "iuf":
            raise ValueError("숫자 좌표가 두 점 이상 필요합니다.")
        # 기존 미리보기와 같이 이미지 테두리까지 허용합니다. 테두리 밖은 오류입니다.
        if (not np.isfinite(pts).all() or (pts < 0).any()
                or (pts[:, 0] > width).any() or (pts[:, 1] > height).any()):
            bad = next(pt for pt in coords if not (0 <= pt[0] <= width and 0 <= pt[1] <= height))
            raise ValueError(f"사진 범위 밖의 점 {bad}")
        points = np.rint(pts).astype(np.int32)
        if not (points != points[0]).any():
            raise ValueError("서로 다른 점이 필요합니다.")
        return points
    except (KeyError, TypeError, ValueError) as exc:
        raise SampleError("좌표 오류", str(exc)) from exc


def encode(path, img):
    ok, data = cv2.imencode(path.suffix, img)
    if not ok:
        raise OSError(f"인코딩 오류: {path}")
    return data.tobytes()


def verify(mask, shape):
    if mask.dtype != np.uint8 or mask.ndim != 2 or mask.shape != shape:
        raise ValueError("마스크 크기 또는 채널·비트 수 오류")
    white = int(cv2.countNonZero(cv2.compare(mask, 255, cv2.CMP_EQ)))
    if white == 0 or white != cv2.countNonZero(mask):
        raise ValueError("흰 차선이 없거나 0, 255 이외의 값이 있습니다.")
    return white


def write_mask(path, mask):
    # 임시 PNG를 다시 열어 검증한 뒤 최종 이름으로 옮깁니다.
    with NamedTemporaryFile(dir=path.parent, suffix=".png", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        temporary.write_bytes(encode(path, mask))
        saved = read_image(temporary, cv2.IMREAD_UNCHANGED)
        count = verify(saved, mask.shape)
        if not np.array_equal(saved, mask):
            raise ValueError("저장 전후의 마스크가 다릅니다.")
        temporary.replace(path)
        return count
    finally:
        temporary.unlink(missing_ok=True)


def comparison(photo, saved_mask, path):
    overlay = photo.copy()
    overlay[saved_mask == 255] = (0, 255, 0)
    panels = []
    for title, img in (("Original", photo), ("Mask", cv2.cvtColor(saved_mask, cv2.COLOR_GRAY2BGR)),
                       ("Overlay", overlay)):
        height, width = img.shape[:2]
        panel = cv2.resize(img, (800, round(height * 800 / width)), interpolation=cv2.INTER_AREA)
        panel = cv2.copyMakeBorder(panel, 38, 0, 0, 0, cv2.BORDER_CONSTANT)
        cv2.putText(panel, title, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, .75, (255, 255, 255), 1, cv2.LINE_AA)
        panels.append(panel)
    path.write_bytes(encode(path, np.hstack(panels)))


def convert(row, doc, output, sample):
    photo = read_image(row["jpg"], cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    height, width = photo.shape[:2]
    row.update(width=width, height=height)
    lanes = [a for a in doc["annotations"] if a["class"] == "traffic_lane" and a["category"] == "polyline"]
    row["lane_count"] = len(lanes)
    if doc["image"]["image_size"] != [height, width]:
        raise SampleError("크기 불일치", f'JSON image_size={doc["image"]["image_size"]}')
    if not lanes:
        raise SampleError("차선 라벨 없음", "traffic_lane / polyline 0개")
    # 검정 단일 채널 바탕에 차선 하나씩 그립니다. 점선 사이도 JSON의 순서대로 잇습니다.
    mask = np.zeros((height, width), dtype=np.uint8)
    for number, lane in enumerate(lanes, 1):
        try:
            points = lane_points(lane, width, height)
        except SampleError as exc:
            raise SampleError(exc.status, f"차선 {number}: {exc}") from exc
        # False는 마지막 점과 첫 점을 잇지 않는다는 뜻입니다. LINE_8은 중간 회색을 만들지 않습니다.
        cv2.polylines(mask, [points], False, 255, row["thickness"], cv2.LINE_8)
    path = output / "masks" / (row["jpg"].stem + "_mask.png")
    row["white_pixels"] = write_mask(path, mask)
    row["mask"] = path
    if sample:
        comparison(photo, read_image(path, cv2.IMREAD_UNCHANGED),
                   output / "comparisons" / (row["jpg"].stem + "_compare.jpg"))
    row["status"] = "성공"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path, help="dataSetSn_197로 시작하는 실제 폴더")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", nargs="+", help="샘플 JPG의 이름 또는 확장자를 뺀 이름")
    parser.add_argument("--thickness", default=5, type=int)
    args = parser.parse_args()
    if not 1 <= args.thickness <= 32767:
        parser.error("--thickness는 1~32767 사이의 정수여야 합니다.")
    root, output = args.data_root.resolve(), args.output.resolve()
    if output.is_relative_to(root):
        parser.error("출력은 원본 데이터셋 폴더 바깥으로 지정하세요.")
    images, labels, errors = inventory(root)
    keys = images.keys() | labels.keys()
    matched = sum(len(images.get(k, [])) == len(labels.get(k, [])) == 1 for k in keys)
    print(f"JPG {sum(map(len, images.values()))}, JSON {sum(map(len, labels.values())) + len(errors)}, "
          f"1:1 매칭 {matched}", flush=True)
    if args.samples:
        keys = {Path(s).with_suffix(".jpg").name.casefold() for s in args.samples}
        (output / "comparisons").mkdir(parents=True, exist_ok=True)
    (output / "masks").mkdir(parents=True, exist_ok=True)
    rows = [] if args.samples else errors.copy()
    for key in sorted(keys):
        jpgs, docs = images.get(key, []), labels.get(key, [])
        row = dict(jpg=" | ".join(map(str, jpgs)), json=" | ".join(str(p) for p, _ in docs),
                   thickness=args.thickness)
        if len(jpgs) > 1 or len(docs) > 1:
            row.update(status="중복", detail=f"{key}: JPG {len(jpgs)}, JSON {len(docs)}")
        elif not jpgs or not docs:
            row.update(status="짝 누락", detail=f"{key}: JPG {len(jpgs)}, JSON {len(docs)}")
        else:
            row.update(jpg=jpgs[0], json=docs[0][0])
            try:
                convert(row, docs[0][1], output, bool(args.samples))
            except SampleError as exc:
                row.update(status=exc.status, detail=str(exc))
            except (ValueError, TypeError, KeyError, OSError, cv2.error) as exc:
                row.update(status="처리 오류", detail=str(exc))
        rows.append(row)
    manifest = output / ("sample_manifest.csv" if args.samples else "manifest.csv")
    with manifest.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    # CSV를 다시 읽어 성공 목록과 실제 PNG 파일 목록을 대조합니다.
    with manifest.open(encoding="utf-8-sig", newline="") as file:
        checked = list(csv.DictReader(file))
    success = [Path(r["mask"]) for r in checked if r["status"] == "성공"]
    actual = set((output / "masks").glob("*.png"))
    if len(set(success)) != len(success) or not set(success) <= actual or (not args.samples and set(success) != actual):
        raise RuntimeError("CSV 성공 목록과 출력 PNG가 다릅니다. 기존 출력 파일을 확인하세요.")
    for row in checked:
        if row["status"] == "성공":
            saved = read_image(Path(row["mask"]), cv2.IMREAD_UNCHANGED)
            original_size = (int(row["height"]), int(row["width"]))
            if verify(saved, original_size) != int(row["white_pixels"]):
                raise ValueError(f'흰 픽셀 수가 CSV와 다릅니다: {row["mask"]}')
    print(dict(Counter(r["status"] for r in checked)), manifest)


if __name__ == "__main__":
    main()
