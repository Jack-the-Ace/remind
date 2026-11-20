# 014  628번 사진에서 차선 영역 확인하기
# 628번은 차선의 폭을 다각형으로 기록하므로 내부와 테두리를 함께 그립니다.
# 같은 장면의 JPG와 JSON을 차례로 입력합니다.
# 원본에 겹친 output/lane_label_preview.jpg를 보고 여러 장의 라벨을 점검합니다.

# JPG 읽기 → JSON의 차선 좌표 읽기 → OpenCV로 그리기 → JPG 저장
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="AI Hub 차선 정답 한 장 확인")
    parser.add_argument("jpg", type=Path, help="원천 JPG 경로")
    parser.add_argument("json", type=Path, help="짝이 되는 라벨 JSON 경로")
    args = parser.parse_args()

    # 1. 한글 경로에서도 읽도록 파일 바이트를 OpenCV 이미지로 복원합니다.
    img = cv2.imdecode(np.frombuffer(args.jpg.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"사진을 읽을 수 없습니다: {args.jpg}")
    height, width = img.shape[:2]

    # 2. 실제 JSON 구조: data_set_info 안에 sourceValue와 data 목록이 있습니다.
    label = json.loads(args.json.read_text(encoding="utf-8-sig"))
    info = label["data_set_info"]
    # 엉뚱한 사진에 좌표를 그리지 않도록 JSON의 JPG 이름과 대조합니다.
    # sourceValue에는 JPG 이름만 있거나 IMAGE/A/... 같은 상대 경로가 들어 있습니다.
    source_name = info["sourceValue"].replace("\\", "/").rsplit("/", 1)[-1]
    if source_name != args.jpg.name:
        raise ValueError(f"사진 이름 불일치: JSON은 {info['sourceValue']}을 가리킵니다.")

    lanes = []
    for item in info["data"]:
        value = item["value"]
        # 차량도 같은 목록에 있으므로 extra.value가 lane인 항목만 고릅니다.
        if value.get("extra", {}).get("value") != "lane":
            continue
        # 확인한 라벨은 POLYGONS: 차선의 폭을 포함하는 닫힌 영역입니다.
        # 선의 중심 좌표로 취급하지 않고, 다각형 영역으로 채워 그립니다.
        if value["annotation"] != "POLYGONS":
            raise ValueError(f"확인이 필요한 차선 좌표 형식: {value['annotation']}")
        points = np.array([[p["x"], p["y"]] for p in value["points"]], dtype=float)
        if points.ndim != 2 or points.shape[0] < 3 or points.shape[1] != 2:
            raise ValueError("차선 영역은 최소 3개의 x,y 좌표가 필요합니다.")
        # 좌표는 원본 픽셀 기준으로 사용합니다. 범위를 벗어나면 임의로 늘리거나 자르지 않습니다.
        if (not np.isfinite(points).all() or (points < 0).any()
                or (points[:, 0] > width).any() or (points[:, 1] > height).any()):
            raise ValueError(f"차선 좌표가 사진 크기({width}x{height}) 밖입니다. 좌표 기준을 확인해주세요.")
        # 영역의 끝은 y=높이(예:1080)까지 올 수 있습니다. OpenCV가 화면 경계에서 그립니다.
        lanes.append((np.rint(points).astype(np.int32), value["object_Label"]))

    if not lanes:
        raise ValueError("JSON에 차선 라벨이 없습니다.")

    # 3. 차선 영역만 반투명으로 칠해 원본 차선과 겹쳐지는지 볼 수 있게 합니다.
    overlay = img.copy()
    colors = [(0, 255, 255), (0, 255, 0), (255, 180, 0), (255, 0, 255)]
    for i, (points, _) in enumerate(lanes):
        cv2.fillPoly(overlay, [points], colors[i % len(colors)])
    preview = cv2.addWeighted(overlay, 0.3, img, 0.7, 0)
    for i, (points, attributes) in enumerate(lanes):
        color = colors[i % len(colors)]
        cv2.polylines(preview, [points], True, color, 2)
        x, y = points[0]
        # OpenCV 기본 글꼴에 맞춰 그림 안의 설명은 영문으로 표시합니다.
        text = f"Lane {i + 1}: {attributes.get('lane_type', 'lane')}"
        cv2.putText(preview, text, (max(0, min(int(x), width - 350)), max(25, int(y) - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

    # 4. 원본을 덮어쓰지 않고 프로젝트 output 폴더에 저장합니다.
    output = Path(__file__).resolve().parent / "output" / "lane_label_preview.jpg"
    output.parent.mkdir(exist_ok=True)
    if args.jpg.resolve() == output.resolve():
        raise ValueError("결과 파일을 원본 입력으로 사용할 수 없습니다.")
    success, encoded = cv2.imencode(".jpg", preview)
    if not success:
        raise RuntimeError("JPG 변환에 실패했습니다.")
    output.write_bytes(encoded.tobytes())
    print(f"원본 크기: {width} x {height}")
    print(f"그린 차선 라벨 수: {len(lanes)}개 (POLYGONS 영역)")
    print(f"결과 이미지: {output}")


if __name__ == "__main__":
    main()
