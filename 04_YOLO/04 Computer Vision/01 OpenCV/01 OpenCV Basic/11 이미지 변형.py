import cv2

#1) 불러온 이미지를 흑백으로 변경시켜보기
img= cv2.imread('images/dog3.jpg')
img= cv2.resize(img, None, fx=0.3, fy=0.3, interpolation=cv2.INTER_AREA)
cv2.imshow('original', img)

img2= cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imshow('gray image', img2)

#2) 이미지 블러 처리(흐리게)
#2.1) 필터(커널)를 이용하는 방법
kernel_3= cv2.GaussianBlur(img, (3,3), 0)  #필터크기, 표준편차(시그마) 값
kernel_5= cv2.GaussianBlur(img, (5,5), 0)  #필터크기, 표준편차(시그마) 값
kernel_7= cv2.GaussianBlur(img, (7,7), 0)  #필터크기, 표준편차(시그마) 값
cv2.imshow('kernel 3', kernel_3)
cv2.imshow('kernel 5', kernel_5)
cv2.imshow('kernel 7', kernel_7)

#2.2) 표준편차를 이용한 블러처리.. 값이 클 수록 더 심하게 블러.. 정규분포가 넓어져서..
sigma1= cv2.GaussianBlur(img, (0,0), 1)  #표준편차 1
sigma2= cv2.GaussianBlur(img, (0,0), 5)  #표준편차 5
sigma3= cv2.GaussianBlur(img, (0,0), 10)  #표준편차 10
cv2.imshow('sigma1', sigma1)
cv2.imshow('sigma2', sigma2)
cv2.imshow('sigma3', sigma3)

#3) 원근 변경 -- 이미지에 비스듬하게 찍힌 이미지를 원근을 조절하여 똑바로 세우기. [문서 스캐너]
img= cv2.imread('images/newspaper.jpg')
cv2.imshow('newspaper image', img)

#잘라낼 사이즈
width, height= 640, 240

#원본이미지에서 잘라낼 영역의 좌표들 준비
import numpy as np
src= np.array([[511,352],[1008,345],[1122,584],[455,594]], dtype=np.float32)
dst= np.array([[0,0],[width,0],[width,height],[0,height]], dtype=np.float32)

matrix= cv2.getPerspectiveTransform(src, dst)
result= cv2.warpPerspective(img, matrix, (width, height))
cv2.imshow('newspaper transform', result)


#-------------
cv2.waitKey(0)
cv2.destroyAllWindows()