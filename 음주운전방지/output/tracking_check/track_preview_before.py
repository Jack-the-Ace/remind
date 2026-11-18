# 참고: detect_preview.py의 차량 필터, 수업의 10 object_detection_video.py
from pathlib import Path

import cv2
from ultralytics import YOLO


def main():
    # 실행한 폴더가 달라도 이 파일 위치를 기준으로 영상과 가중치를 찾습니다.
    project_dir = Path(__file__).resolve().parent
    video_path = project_dir / "videos" / "비접촉_사고유발_영상.mp4"
    weights_path = project_dir / "yolo26n.pt"
    if not video_path.is_file():
        raise FileNotFoundError(f"영상이 없습니다: {video_path}")
    if not weights_path.is_file():
        raise FileNotFoundError(f"YOLO 가중치가 없습니다: {weights_path}")

    # 1. 수업처럼 VideoCapture로 영상을 열고 한 프레임씩 읽습니다.
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

        # 2. 사전 학습 모델과 기존 차량 종류 필터를 준비합니다.
        model = YOLO(str(weights_path))
        vehicle_names = {"car", "bus", "truck", "motorcycle"}
        # 모델의 분류명에서 차량 번호를 찾아 추적 대상도 차량으로 제한합니다.
        vehicle_ids = [key for key, name in model.names.items() if name in vehicle_names]
        fps = cap.get(cv2.CAP_PROP_FPS)
        delay = max(1, round(1000 / fps)) if fps > 0 else 33
        print("차량 추적을 시작합니다. 영상 창에서 q를 누르면 종료합니다.")

        # 3. 프레임별 차량 추적
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # track()은 차량을 검출하고 이전 프레임의 차량과 연결해 번호를 붙입니다.
            # ByteTrack은 검출 위치 등을 비교해 같은 차량을 이어 찾는 추적기입니다.
            # 가려지거나 검출이 오래 끊기면 같은 차량에도 새 번호가 붙을 수 있습니다.
            results = model.track(
                source=frame,
                tracker="bytetrack.yaml",
                persist=True,  # 이전 프레임의 추적 정보를 기억해 같은 번호를 이어 씁니다.
                conf=0.1,
                classes=vehicle_ids,
                device="cpu",
                verbose=False,
            )
            result = results[0]

            # 4. 차량마다 빨간 네모와 추적 번호 표시
            for bbox in result.boxes:
                class_id = int(bbox.cls[0])
                if result.names[class_id] not in vehicle_names:
                    continue

                x1, y1, x2, y2 = map(int, bbox.xyxy[0].tolist())
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                # id는 추적기가 붙인 번호이며, 번호를 아직 못 받으면 None입니다.
                if bbox.id is not None:
                    track_id = int(bbox.id[0])
                    cv2.putText(
                        frame, f"ID {track_id}", (x1, max(25, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
                    )

            # ID가 없는 프레임도 표시하고 q 입력을 확인해야 재생이 이어집니다.
            cv2.imshow("RedBox vehicle tracking", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        # 오류가 나거나 q로 종료해도 영상과 창을 정리합니다.
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
