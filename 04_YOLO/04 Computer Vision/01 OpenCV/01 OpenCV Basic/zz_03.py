import cv2

cap= cv2.VideoCapture(0)
if not cap.isOpened():
    exit()

while True:
    ret, frame= cap.read()
    if not ret:
        break
    cv2.imshow('camera', frame)

    flipped_img= cv2.flip(frame, 1)
    cv2.imshow('camera', flipped_img)

    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()