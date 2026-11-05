# 이미지의 일부영역을 잘라내기
import cv2
img= cv2.imread('images/dog3.jpg')
crop= img[200:600, 600:1000]  #이미지의 행열을 슬라이싱 [행:100~600, 열:600~1000]

cv2.imshow('original image', img)
cv2.imshow('croped image', crop)

#영역을 잘라서 기존 윈도우 창에 표시하기
img[200:600, 1500:1900]= crop
cv2.imshow('composition image', img)

cv2.waitKey(0)
cv2.destroyAllWindows()

