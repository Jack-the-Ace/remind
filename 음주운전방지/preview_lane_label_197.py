# 수업 흐름: OpenCV로 읽기 → JSON 좌표 읽기 → 선 그리기 → JPG 저장
import argparse
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="197번 차선/정지선/횡단보도 정답 확인")
    parser.add_argument("jpg", type=Path)
    parser.add_argument("json", type=Path)
    args = parser.parse_args()
    img = cv2.imdecode(np.frombuffer(args.jpg.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("사진을 읽을 수 없습니다.")
    doc = json.loads(args.json.read_text(encoding="utf-8-sig"))
    if doc["image"]["file_name"].casefold() != args.jpg.name.casefold():
        raise ValueError("JSON이 가리키는 사진 이름이 다릅니다.")
    # 이 JSON의 image_size는 [높이, 너비]입니다. 폴더 이름의 1900을 너비로 쓰지 않습니다.
    height, width = img.shape[:2]
    if doc["image"]["image_size"] != [height, width]:
        raise ValueError(f"사진 크기 {width}x{height}와 JSON 크기가 다릅니다.")

    # 차선은 초록 선, 정지선은 빨간 선, 횡단보도는 파란 테두리로 구분합니다.
    styles = {"traffic_lane": ((0, 255, 0), "polyline"),
              "stop_line": ((0, 0, 255), "polyline"),
              "crosswalk": ((255, 140, 0), "polygon")}
    count = Counter()
    for annotation in doc["annotations"]:
        kind = annotation["class"]
        if kind not in styles:
            raise ValueError(f"확인이 필요한 클래스: {kind}")
        color, category = styles[kind]
        if annotation["category"] != category:
            raise ValueError(f"확인이 필요한 좌표 형식: {annotation['category']}")
        # data 목록의 x,y를 순서대로 연결합니다. 원본 픽셀 좌표를 그대로 사용합니다.
        points = np.array([[p["x"], p["y"]] for p in annotation["data"]], dtype=float)
        minimum = 3 if category == "polygon" else 2
        if points.ndim != 2 or points.shape[0] < minimum or points.shape[1] != 2:
            raise ValueError("좌표 개수 또는 구조가 올바르지 않습니다.")
        if (not np.isfinite(points).all() or (points < 0).any()
                or (points[:, 0] > width).any() or (points[:, 1] > height).any()):
            raise ValueError("원본 사진 범위 밖의 좌표가 있습니다.")
        points = np.rint(points).astype(np.int32)
        # 차선 polyline은 끝을 닫지 않습니다. 횡단보도 polygon만 닫힌 테두리입니다.
        cv2.polylines(img, [points], category == "polygon", color, 3, cv2.LINE_AA)
        count[kind] += 1
        x, y = points[len(points) // 2]
        text = f"{kind} {count[kind]}"
        cv2.putText(img, text, (min(int(x), width - 230), max(25, int(y) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
    cv2.putText(img, "GREEN: lane | RED: stop line | BLUE: crosswalk", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, .75, (255, 255, 255), 2)
    output_dir = Path(__file__).resolve().parent / "output" / "lane_label_check_197"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{args.jpg.stem}_preview.jpg"
    success, encoded = cv2.imencode(".jpg", img)
    if not success:
        raise RuntimeError("JPG 저장용 변환에 실패했습니다.")
    output.write_bytes(encoded.tobytes())
    print(f"{args.jpg.name}: {width}x{height}, {dict(count)} → {output}")


if __name__ == "__main__":
    main()
