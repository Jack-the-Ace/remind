# 동영상에서 얼굴검출과 모자이크 처리 & 파일로 저장
import cv2
import mediapipe as mp
import time

#모델 파일 경로
model_path= "model/face_detection.tflite"

#얼굴검출 모델 옵션 준비
options= mp.tasks.vision.FaceDetectorOptions(
    base_options= mp.tasks.BaseOptions(model_asset_path= model_path),
    running_mode= mp.tasks.vision.RunningMode.VIDEO,
    min_detection_confidence= 0.2
)

#얼굴검출 객체 생성
with mp.tasks.vision.FaceDetector.create_from_options(options) as detector:
    #동영상 준비
    video_path= "videos/talking.mp4"
    video_path= "videos/talking2.mp4"
    cap= cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError('동영상 파일을 열 수 없어요~~')

    #모자이크 처리한 영상을 저장해야 하기에 관련 준비
    output_path= "videos/face_mosaic.mp4"
    #원본 동영상의 정보
    fps= cap.get(cv2.CAP_PROP_FPS)
    width= int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height= int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    #FPS 정보가 없는 경우가 있음.
    if fps<=0:
        fps=30

    #코덱 준비
    fourcc= cv2.VideoWriter_fourcc(*"mp4v")
    #영상 저장객체 생성
    out= cv2.VideoWriter(output_path, fourcc, fps, (width,height))
    if not out.isOpened():
        cap.release()
        raise RuntimeError('출력 동영상 저장이 불가능합니다.')

    frame_count=0
    last_timestamp= -1    
    while True:
        ret, frame= cap.read()
        if not ret:
            break

        # mediapipe face detector 로 얼굴 검출 및 모자이크
        rgb= cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image= mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        #프레임시간 계산
        timestamp= max(last_timestamp + 1, int(frame_count*1000) / fps)
        last_timestamp= timestamp
        frame_count += 1

        result= detector.detect_for_video(mp_image, int(timestamp))

        #모자이크 적용
        h, w= frame.shape[:2]  #채널정보 제외.
        for detection in result.detections:
            box=detection.bounding_box
            x= box.origin_x
            y= box.origin_y
            bw= box.width
            bh= box.height

            x1= max(0, x-bw//10)
            y1= max(0, y-bh//10)
            x2= min(w, x+bw+bw//10)
            y2= min(h, y+bh+bh//10)

            face= frame[y1:y2, x1:x2]

            small= cv2.resize(face, (face.shape[1]//30, face.shape[0]//30))
            mosaic= cv2.resize(small, (face.shape[1], face.shape[0]))

            frame[y1:y2, x1:x2] = mosaic

        cv2.imshow("video mosaic", frame)  #영상보이기
        out.write(frame)   #영상저장

        if cv2.waitKey(1) == ord('q'):
            break

cap.release()
out.release()
cv2.destroyAllWindows()