# 필요한 모듈 설치
# pip install mediapipe opencv-python

#0. 모듈 사용
import time
import cv2
import mediapipe as mp   # 온디바이스AI용으로 공개된 구글의 open source [경량모델]

#1. 얼굴 검출 모델을 다운로드 (다운로드 경로 URL 이용)
from pathlib import Path
from urllib.request import urlretrieve
model_url= "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
model_path= Path(__file__).resolve().parent / "model/face_detection.tflite"
if not model_path.exists():
    print('얼굴 검출 모델 다운로드 중......')
    urlretrieve(model_url, model_path)

#2. mediapipe 에서 제공하는 얼굴 검출기 객체를 생성할 옵션 준비
options= mp.tasks.vision.FaceDetectorOptions(
    base_options= mp.tasks.BaseOptions(model_asset_path=str(model_path)),
    running_mode= mp.tasks.vision.RunningMode.VIDEO,  # VIDEO: 연속된 영상 프레임 처리
    min_detection_confidence=0.5   #얼굴검출의 최소 신뢰도
)

#3. 얼굴 검출 객체 생성 및 웹캠 실시간 얼굴검출 실행
with mp.tasks.vision.FaceDetector.create_from_options(options) as detector:
    #4. 웹캠 연결
    cap= cv2.VideoCapture(0)  #0:첫번째 카메라 번호
    if not cap.isOpened():
        raise RuntimeError('웹캠을 열 수 없어요~~')

    #영상 프레임 시간 계산을 위해..
    last_timestamp= -1
    start_time= time.monotonic()  #단조 시간. 시스템시간과 상관없이 일정하게 증가하는 시간

    while True:
        ret, frame= cap.read()  #한 프레임 읽기
        if not ret:
            break

        #좌우반전
        frame= cv2.flip(frame, 1)

        # opencv BGR --> mediapipe RGB
        rgb_frame= cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        #미디어파이프 모델이 추론할 수 있도록 미디어파이프용 이미지 객체로 만들기
        mp_image= mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)   # SRGB: standard RGB - 기기 상관없이 RGB를 동일하게 표현하도록 만든 표준

        #얼굴 검출 요청
        timestamp= max(last_timestamp+1, int((time.monotonic()-start_time)*1000))
        last_timestamp= timestamp
        result= detector.detect_for_video(mp_image, timestamp)  # timestamp: 분석프레임과 영상프레임 속도 차이로 인한 문제 해결
        #print('검출정보:', result )

        #5. 검출된 얼굴 영역에 모자이크 적용
        # 프레임 사이즈 확인
        height, width= frame.shape[:2]  #프레임의 차원정보[height, width]  <-- channel은 필요없으니..

        #얼굴영역(boundingbox) 보다 10% 큰 영역을 모자이크 처리
        for detection in result.detections:
            # 얼굴 사각형 좌표 추출
            box= detection.bounding_box

            # 검출된 사각형 영역의 좌상단 좌표와 너비, 높이
            x= box.origin_x
            y= box.origin_y
            bw= box.width
            bh= box.height

            # 모자이크 처리할 영역을 얼굴영역의 10% 큰 사이즈로 덮도록 좌표들 준비
            # 좌상단 좌표
            x1= max(0, x-bw//10)
            y1= max(0, y-bh//10)

            # 우하단 좌표
            x2= min(width, x+bw+bw//10)
            y2= min(height, y+bh+bh//10)

            # 얼굴 영역 추출 (ROI: Region of Interest - 관심영역)
            face= frame[y1:y2, x1:x2]  #행,열 슬라이싱
            if face.size==0:
                continue

            # 모자이크는 해상도를 줄이면 됨. 얼굴 이미지를 작게.. 원래크기에 15나눈 몫값으로
            small= cv2.resize(face, (face.shape[1]//15, face.shape[0]//15))  # <-- 튜플로 줘야됨

            # 작은 이미지를 다시 원래크기로 그리면..
            mosaic= cv2.resize(small, (face.shape[1], face.shape[0]), interpolation=cv2.INTER_LINEAR)

            # 모자이크 이미지를 영상 프레임에 적용(이미지 잘라 붙이기)
            frame[y1:y2, x1:x2]= mosaic

        # 얼굴이 몇 개 검출되었는지 화면에 표시
        cv2.putText(
            frame,
            f"Faces: {len(result.detections)}",
            (20,40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0,255,0),
            2
        )


        cv2.imshow('face detection', frame)
        # q키를 누르면 종료
        if cv2.waitKey(1) == ord('q'):
            break


#모든 작업이 종료되면
cap.release()
cv2.destroyAllWindows()