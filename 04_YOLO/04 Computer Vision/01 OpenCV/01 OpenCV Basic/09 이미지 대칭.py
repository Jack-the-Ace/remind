import cv2

img= cv2.imread('images/dog3.jpg')
cv2.imshow('original', img)

#1) 좌우
img2= cv2.flip(img, flipCode=1)  # 0보다 크면
cv2.imshow('flip_horizontal', img2)
#2) 상하
img3= cv2.flip(img, flipCode=0)  # 0
cv2.imshow('flip_vertical', img3)
#3) 상하좌우
img4= cv2.flip(img, flipCode=-1)  # 0보다 작으면
cv2.imshow('flip_both', img4)

cv2.waitKey(0)
cv2.destroyAllWindows()
