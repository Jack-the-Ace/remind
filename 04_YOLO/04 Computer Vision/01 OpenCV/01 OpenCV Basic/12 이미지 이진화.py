# 이미지 이진화 - 모든 픽셀을 1,0 으로만 변경 (흑백 이미지)
# 특정 값을 기준으로 0,1을 분류.  흑백이 명확하여 글씨같은 것이 식별이 용이해짐.

import cv2
img= cv2.imread('images/sudoku.png', cv2.IMREAD_GRAYSCALE)
cv2.imshow('book image', img)

# 흑백으로 구분한 임계값
threshold= 127  #255의 절반

#1) 이미지를 이진화 [조명이 균일할때 사용하는 기법] - 임계값 기준으로 0,255을 분류
ret, thresh= cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)  #리턴값(실제 사용된 임계값, 적용된 이미지)
cv2.imshow('thresh', thresh)

#2) 이미지의 최적의 임계값을 알아서 적용 - 오츠알고리즘. [조명이 균일할때 사용]
ret, otsu= cv2.threshold(img, -1, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
cv2.imshow('otsu', otsu)
print('otsu가 계산한 최적의 임계값', otsu)

#3) 적응형 이진화 - 가우시안 분포 활용
thresh2= cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
#블록 윈도우[11x11] 단위로 임계값 계산.
cv2.imshow('thresh2', thresh2)




#--------------------------------
cv2.waitKey(0)
cv2.destroyAllWindows()