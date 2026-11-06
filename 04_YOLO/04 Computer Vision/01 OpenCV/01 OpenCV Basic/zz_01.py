#0. OpenCV 모듈 설치
# pip install opencv-python

#1. OpenCV 모듈 사용
import cv2
img= cv2.imread('images/dog3.jpg')

cv2.imshow('Dog Image', img)

cv2.waitKey(0)
cv2.destroyAllWindows()

cv2.namedWindow('image', cv2.WINDOW_NORMAL)
cv2.resizeWindow('image', 800, 600)
cv2.imshow('image', img)

cv2.waitKey(0)
cv2.destroyAllWindows()

img1= cv2.imread('images/cat.png', cv2.IMREAD_COLOR)
img2= cv2.imread('images/cat.png', cv2.IMREAD_GRAYSCALE)
img3= cv2.imread('images/cat.png', cv2.IMREAD_UNCHANGED)

cv2.imshow('color image', img1)
cv2.imshow('gray image', img2)
cv2.imshow('unchaned image', img3)

cv2.waitKey(0)
cv2.destroyAllWindows()

img= cv2.imread('images/dog3.jpg')
print(img.shape)

img= cv2.imread('images/cat.png', cv2.IMREAD_UNCHANGED)
print(img.shape)
