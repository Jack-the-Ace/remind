# 동영상 리소스는 pixels 라는 곳에서 다운받을 수 있음!

import cv2
cap= cv2.VideoCapture('videos/dog_sd.mp4')

while cap.isOpened():
    ret, frame= cap.read()  #한 프레임씩 읽어옴. 리턴값 튜플(프레임 읽기 성공여부, 받아온 이미지(한장면))
    if not ret:
        print('더이상 읽어올 프레임이 없음')
        break

    cv2.imshow('dog video', frame)

    #만약 동영상을 도중에 멈추고 싶다면.
    #동영상의 프레임전환 속도 FPS (Frame per Second)
    #현재 비디오파일이 30FPS임. 그럼 장면 하나당 1000ms/30장 == 33ms
    if cv2.waitKey(33) == ord('q'):  #아스키 코드값으로 입력되기에..
        print('동영상 출력을 중간에 멈춥니다~')
        break

cap.release()   #자원 해제 (메모리 누수 방지)
cv2.destroyAllWindows()
