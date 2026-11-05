import cv2

img= cv2.imread('images/dog3.jpg')
cv2.imshow('original', img)

img2= cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)  #시계방향 90도
cv2.imshow('rotate_90', img2)

img3= cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)  #시계 반대방향 90도
cv2.imshow('rotate_270', img3)

img4= cv2.rotate(img, cv2.ROTATE_180)  # 180도
cv2.imshow('rotate_180', img4)

cv2.waitKey(0)
cv2.destroyAllWindows()