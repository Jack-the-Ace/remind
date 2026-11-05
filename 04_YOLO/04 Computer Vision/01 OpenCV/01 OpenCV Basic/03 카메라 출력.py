import cv2

# 카메라 장치에서 비디오 캡처
cap= cv2.VideoCapture(0)   # 0번째 카메라 장치 (device ID)
if not cap.isOpened():
    exit()   #프로그램 종료

while True:
    ret, frame= cap.read()
    if not ret:
        break

    #cv2.imshow('camera', frame)

    #좌우반전을 하고 싶다면..
    flipped_img= cv2.flip(frame, 1)  # 1:좌우반전, 0:상하반전, -1:상하좌우반전
    cv2.imshow('camera', flipped_img)


    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()


