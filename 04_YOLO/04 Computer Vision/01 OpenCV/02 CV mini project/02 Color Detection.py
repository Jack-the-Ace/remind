import cv2
import numpy as np

#1. 이미지 불러오기
src= cv2.imread('images/balls.png')
cv2.imshow('original', src)

dst= src.copy()  # 최종 결과물이 그려질 이미지

#2. 색정보를 구별하기 위해 BGR --> HSV 색상 변환 (빛의 영향으로 색상 구별이 어려운 것을 해결)
hsv= cv2.cvtColor(src, cv2.COLOR_BGR2HSV)
# H:색상종류(0~179), S:채도(색 선명도 0~255), V:명도(밝기 0~255)
#원래 색상은 0~360. 1byte가 255까지만 가능하기에.. 절반으로 나눠서 0~179

#3. 빨간색 영역 추출
# 적색은 Hue 범위가 0을 기준으로 양쪽 끝에 위치함. 따라서, 2개의 구간정보 필요
#1) 0~15 영역
lower_red1= np.array([0, 100, 100])  # H, S, V
upper_red1= np.array([15, 255, 255])

#2) 165~179
lower_red2= np.array([165, 100, 100])  # H, S, V
upper_red2= np.array([179, 255, 255])

# 위 2개 영역 마스크로 만들기
mask1= cv2.inRange(hsv, lower_red1, upper_red1)
mask2= cv2.inRange(hsv, lower_red2, upper_red2)

# 2개의 적색 마스크를 하나로 결합 - 
mask= cv2.bitwise_or(mask1, mask2)  # or: 둘 중에 하나라도 1이면 1

# 마스크 영역만 출력해보기
cv2.imshow('red mask', mask)

#4. 모폴로지-형태학 - 노이즈 제거
kernel= np.ones((5,5), np.int8)  #흰색 5x5
mask= cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
cv2.imshow('red mask remove noise', mask)

#빨간색만 추출
red_only= cv2.bitwise_and(src, src, mask=mask)
cv2.imshow('red only', red_only)

# 빨간색 개체만 윤곽선을 추출
contours, _= cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

for contour in contours:
    area= cv2.contourArea(contour)
    if area < 500:
        continue

    # 물체의 좌표와 영역
    x,y,width,height= cv2.boundingRect(contour)

    #물체의 영역에 사각형 그리기
    cv2.rectangle(dst, (x,y), (x+width,y+height), (0,255,0), 3)
#----------------------------------------------

cv2.imshow('red color detection', dst)


#---------------------
cv2.waitKey(0)
cv2.destroyAllWindows()