# 001  사진 한 장에서 차량 찾기
# 수업의 YOLO로 차종을 걸러 사진부터 결과를 확인합니다.
# JPG 경로와 같은 폴더의 yolo26n.pt를 준비합니다.
# 차량에 네모를 그려 output/<사진명>_detected.jpg에 저장하고 영상 추적으로 넘어갑니다.

# 참고: 수업의 06 object_detection.py (이미지 → YOLO → 박스 그리기)
from pathlib import Path
import sys

import cv2
import numpy as np
from ultralytics import YOLO


def main():    
    work_dir = Path(__file__).resolve().parent
    weights_path = work_dir / "yolo26n.pt"

    # 명령 뒤에 JPG 경로를 주거나, 실행 후 직접 입력할 수 있습니다.
    image_text = sys.argv[1] if len(sys.argv) > 1 else input("JPG 경로를 입력하세요: ")
    image_path = Path(image_text.strip().strip('"')).expanduser().resolve()
    if not image_path.is_file() or image_path.suffix.lower() not in {".jpg", ".jpeg"}:
        raise ValueError(f"JPG 파일 경로를 입력해주세요: {image_path}")

    # 1. OpenCV로 사진 읽기
    img = cv2.imread(str(image_path))
    if img is None:
        # 일부 OpenCV 버전에서 한글 경로를 못 읽으면 바이트를 읽어 복원합니다.
        img = cv2.imdecode(np.frombuffer(image_path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"사진을 읽을 수 없습니다: {image_path}")

    # 2. 수업에서 사용한 사전 학습 가중치 불러오기 (새 학습은 하지 않습니다.)
    if not weights_path.is_file():
        raise FileNotFoundError(f"수업용 YOLO 가중치가 없습니다: {weights_path}")
    model = YOLO(str(weights_path))

    # 3. 이 실습의 신뢰도 기준(0.1)과 CPU로 객체 검출
    results = model.predict(source=img, conf=0.1, device="cpu", verbose=False)
    result = results[0]

    # 4. 차량 분류만 골라 빨간 네모 그리기 (사람·자전거 등은 제외)
    vehicle_names = {"car", "bus", "truck", "motorcycle"}
    vehicle_count = 0
    for bbox in result.boxes:
        class_id = int(bbox.cls[0])
        class_name = result.names[class_id]
        if class_name not in vehicle_names:
            continue  # 차량이 아니면 다음 검출 결과로 넘어갑니다.

        x1, y1, x2, y2 = map(int, bbox.xyxy[0].tolist())
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
        vehicle_count += 1

    # 5. 원본은 그대로 두고 작업 폴더의 output에 결과 JPG 저장
    output_dir = work_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{image_path.stem}_detected.jpg"
    success, jpg_data = cv2.imencode(".jpg", img)
    if not success:
        raise RuntimeError("결과 사진을 JPG로 변환하지 못했습니다.")
    # 한글 경로에도 저장되도록 JPG 바이트를 파일에 씁니다.
    output_path.write_bytes(jpg_data.tobytes())

    print(f"차량 수: {vehicle_count}대")
    print(f"결과 JPG 경로: {output_path}")


if __name__ == "__main__":
    # 파일을 직접 실행했을 때만 검출을 시작합니다.
    try:
        main()
    except (OSError, ValueError, RuntimeError, cv2.error) as error:
        print(f"오류: {error}", file=sys.stderr)
        sys.exit(1)
