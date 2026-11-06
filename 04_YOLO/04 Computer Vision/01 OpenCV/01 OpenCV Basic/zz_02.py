import cv2
cap= cv2.VideoCapture('videos/dog_sd.mp4')

while cap.isOpened():
    ret, frame= cap.read()  # 한 프레임씩 읽어옴. 리턴값 튜플(프레임 읽기 성공여부, 받아온 이미지(한장면))
    if not ret:
        print('더이상 읽어올 프레임이 없음')
        break

    cv2.imshow('dog video', frame)

    if cv2.waitKey(33) == ord('q'):
        print('I am Stopping now')
        break


cap.release()
cv2.destroyAllWindows()