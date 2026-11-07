import cv2
import mediapipe as mp

# 캐릭터 이미지 불러오기-------------------------------------------------------------------------
left_eye_img= cv2.imread('images/character_mask/left_eye.png', cv2.IMREAD_UNCHANGED)
right_eye_img= cv2.imread('images/character_mask/right_eye.png', cv2.IMREAD_UNCHANGED)
nose_img= cv2.imread('images/character_mask/nose.png', cv2.IMREAD_UNCHANGED)
#---------------------------------------------------------------------------------------------
model_path= 'model/face_detection.tflite'
options= mp.tasks.vision.FaceDetectorOptions(
    base_options= mp.tasks.BaseOptions(model_asset_path= model_path),
    running_mode= mp.tasks.vision.RunningMode.VIDEO,
    min_detection_confidence= 0.6
)
with mp.tasks.vision.FaceDetector.create_from_options(options) as detector:
    video_path= 'videos/talking.mp4'
    #cap= cv2.VideoCapture(video_path)
    cap= cv2.VideoCapture(0)

    last_timestamp= -1
    frame_count=0
    while True:
        ret, frame= cap.read()
        if not ret:
            break

        #얼굴 검출
        rgb= cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image= mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp= max(last_timestamp+1, int(frame_count*1000/30))
        last_timestamp= timestamp
        frame_count += 1

        result= detector.detect_for_video(mp_image, timestamp)

        #검출된 얼굴에 사각형 표시
        h,w= frame.shape[:2]
        for detection in result.detections:
            box= detection.bounding_box

            cv2.rectangle(frame, (box.origin_x, box.origin_y),(box.origin_x+box.width, box.origin_y+box.height),(255,255,255), 3)  #cv2.rectangle( frame,(좌상단좌표),(우하단좌표),(255,255,255),3)

            #얼굴의 주요지점 [key point] 6개 활용!
            #먼저, 6개의 얼굴 특징점에 빨간점 표시해보기!
            for keypoint in detection.keypoints:
                #정규화된 좌표(0~1) ==> 이미지의 좌표계
                px= int( keypoint.x * frame.shape[1] )  # 값 x 너비
                py= int( keypoint.y * frame.shape[0] )  # 값 x 높이

                #빨간색 원점 표시
                cv2.circle(frame, (px, py), 5, (0,0,255), -1)

            #6개 특징점 중에서 왼쪽눈, 오른쪽는, 코 위치만 추출(캐릭터 이미지 씌우기)
            right_eye= detection.keypoints[0]
            left_eye= detection.keypoints[1]
            nose= detection.keypoints[2]

            #이미지 좌표계로 변경
            re_x= int(right_eye.x * w)
            re_y= int(right_eye.y * h)
            le_x= int(left_eye.x * w)
            le_y= int(left_eye.y * h)
            nx= int(nose.x * w)
            ny= int(nose.y * h)

            #프레임(한 장면)에 캐릭터 이미지를 오버레이.
            #cv2.copyTo(src, mask, dst)
            #이미지 사이즈는 100x100으로
            #오른쪽 눈썹
            cv2.copyTo(
                src= right_eye_img[:,:,:3],  #복사할 원본 이미지의 BGR만.. 투명도 차원은 제거 [height,width,channel].. png이므로 [높이,너비,4]  #BGRA
                mask= right_eye_img[:,:,3],  #알파값을 마스크로 사용. 눈 있는 부분은 흰색, 나머지는 검정색
                dst= frame[re_y-110:re_y-10, re_x-50:re_x+50]
            )
            #왼쪽 눈썹
            cv2.copyTo(
                src= left_eye_img[:,:,:3],  #복사할 원본 이미지의 BGR만.. 투명도 차원은 제거 [height,width,channel].. png이므로 [높이,너비,4]  #BGRA
                mask= left_eye_img[:,:,3],  #알파값을 마스크로 사용. 눈 있는 부분은 흰색, 나머지는 검정색
                dst= frame[le_y-110:le_y-10, le_x-50:le_x+50]
            )
            #코 (100x300) 높이 너비
            cv2.copyTo(
                src= nose_img[:,:,:3],  #복사할 원본 이미지의 BGR만.. 투명도 차원은 제거 [height,width,channel].. png이므로 [높이,너비,4]  #BGRA
                mask= nose_img[:,:,3],  #알파값을 마스크로 사용. 눈 있는 부분은 흰색, 나머지는 검정색
                dst= frame[ny-50:ny+50, nx-150:nx+150]
            )

        cv2.imshow('video character', frame)
        if cv2.waitKey(10) == ord('q'):
            break
    #---------------- while ------------------------------

cap.release()
cv2.destroyAllWindows()