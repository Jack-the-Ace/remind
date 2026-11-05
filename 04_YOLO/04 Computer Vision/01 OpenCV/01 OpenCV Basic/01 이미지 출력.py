#0. OpenCV 모듈 설치
# pip install opencv-python

#1. OpenCV 모듈 사용
import cv2

#(실습1) 이미지 출력
#2. 이미지파일 읽어오기
img= cv2.imread('images/dog3.jpg')

#3. 이미지를 새 창(윈도우)에 표시하기
cv2.imshow('Dog Image', img)

#4. 사용자가 키보드의 아무 키나 누를 때까지 대기.
cv2.waitKey(0)   # 3000 = 3000ms  (0은 무한대기)
#5. 모든 윈도우를 닫아라.
cv2.destroyAllWindows()

#(실습1-1) window 창의 크기를 조절하고 싶다면.
cv2.namedWindow('image', cv2.WINDOW_NORMAL)
cv2.resizeWindow('image', 800, 600)  #윈도우 제목, 가로, 세로
cv2.imshow('image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()

#(실습2) 이미지 읽어들일때 읽기 옵션 적용
img1= cv2.imread('images/cat.png', cv2.IMREAD_COLOR)  #컬러이미지로 읽어오기. 단, 투명영역은 무시(default)
img2= cv2.imread('images/cat.png', cv2.IMREAD_GRAYSCALE)  #흑백 이미지
img3= cv2.imread('images/cat.png', cv2.IMREAD_UNCHANGED)  #원래 그림의 채널정보 그대로. 투명영역까지 포함

cv2.imshow('color image', img1)
cv2.imshow('gray image', img2)
cv2.imshow('unchanged image', img3)

cv2.waitKey(0)
cv2.destroyAllWindows()

#(실습3) shape
img= cv2.imread('images/dog3.jpg')
print(img.shape)  #(높이,너비,채널)

img= cv2.imread('images/cat.png', cv2.IMREAD_UNCHANGED)
print(img.shape)  #(높이,너비,채널)

