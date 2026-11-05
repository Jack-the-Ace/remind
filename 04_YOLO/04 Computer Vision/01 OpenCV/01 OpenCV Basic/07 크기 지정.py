import cv2

#1. 이미지
img= cv2.imread('images/dog3.jpg')
cv2.imshow('original image', img)

#이미지의 크기 조정
#1) 고정 크기 지정
img2= cv2.resize(img, (300,500))  # width, height
cv2.imshow('resize image', img2)

#2) 비율 크기 지정
img3= cv2.resize(img, None, fx=1.3, fy=1.5, interpolation=cv2.INTER_LINEAR)  #두번째 파라미터인 크기인자를 None, 보간법 LINEAR : 이웃한 2x2픽셀(4개)의 평균으로 빈 픽셀을 채움. 늘릴때 사용. default임.
cv2.imshow('resize image - 2', img3)
img4= cv2.resize(img, None, fx=1.1, fy=1.1, interpolation=cv2.INTER_CUBIC)  #두번째 파라미터인 크기인자를 None, 보간법 CUBIC : 이웃한 4x4픽셀(16개)의 평균으로 빈 픽셀을 채움. 늘릴때 사용.
cv2.imshow('resize image - 3', img4)
img5= cv2.resize(img, None, fx=0.3, fy=0.5, interpolation=cv2.INTER_AREA)  # 크기를 줄일때 사용.
cv2.imshow('resize image - 4', img5)

cv2.waitKey(0)
cv2.destroyAllWindows()

#2. 동영상
cap= cv2.VideoCapture('videos/dog.mp4')
while cap.isOpened():
    ret, frame= cap.read()
    if not ret:
        break

    #프레임 크기 조정
    frame_resize= cv2.resize(frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    cv2.imshow('video', frame_resize)

    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()



