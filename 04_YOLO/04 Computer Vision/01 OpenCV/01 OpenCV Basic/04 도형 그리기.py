# 이미지 도형을 오버레이 하여 그리기
# 컴퓨터비전분야에서 이미지의 영역, 얼굴 영역 등에 사각형 그려내고자 할 때 필요한 기술
import cv2

#1. 빈 스케치북 윈도우
#세로:480, 너비:640, 3채널 스케치북 만들기
import numpy as np
img= np.zeros( (480,640,3), dtype=np.uint8 )  #모든 픽셀값들이 0인 이미지(검정색 이미지)
#img[:]= (255,255,255) #전체 픽셀값을 흰색으로 지정
#img[:]= (255,0,0)  #RGB 가 아님. opencv에서는 BGR 순서임. (파랑색)
print(img)

#3. 도형 그리기
#3.1 특정 영역(픽셀영역) 색칠하기
img[100:200, 200:300] = (255,255,255)  #세로(행): 100~200 픽셀영역,  가로(열): 200~300 위치를 흰색으로

#3.2 직선 그리기
COLOR= (0,255,255)  #선색깔 Yellow - BGR순
THICKNESS= 3  #선 두께

#직선의 종류
#cv2.LINE_4 : 다음 점을 현재 점의 상하좌우 4개 영역으로 가 그릴 수 있는 종류
#cv2.LINE_8 : 다음 점을 현재 점의 상하좌우대각 8개 영역으로 가 그릴 수 있는 종류
#cv2.LINE_AA: 부드러운 선 (anti-aliasing)
cv2.line(img, (50,100), (400,50), COLOR, THICKNESS, cv2.LINE_4)   #이미지대상,(시작점),(끝점),색상,두께,선 종류
cv2.line(img, (50,200), (400,150), COLOR, THICKNESS, cv2.LINE_8)
cv2.line(img, (50,300), (400,250), COLOR, THICKNESS, cv2.LINE_AA)

#3.3 원 그리기
COLOR= (255,255,0)  #청록색(옥색)
RADIUS= 50  #반지름
THICKNESS= 10  #두께

cv2.circle(img, (200,350), RADIUS, COLOR, THICKNESS, cv2.LINE_AA)  #중심좌표, 반지름, 색상, 두께, 선 종류
# 면 칠하기
cv2.circle(img, (200,350), RADIUS, COLOR, cv2.FILLED, cv2.LINE_AA)

#3.5 다각형 그리기
COLOR= (0,0,255)  #적색
THICKNESS= 3

points= np.array([ [100,100],[200,100],[100,200] ])  #좌표3개: 삼각형
points2= np.array([ [200,100],[300,100],[300,200] ])  #좌표3개: 삼각형

cv2.polylines(img, [points, points2], True, COLOR, THICKNESS, cv2.LINE_AA)   # [다각형 좌표들], 다각형을 닫을지 여부, 색상, 두께, 선 종류

points3= np.array([
    [[100,300],[200,300],[100,400]],
    [[200,300],[300,300],[300,400]],
])
cv2.fillPoly(img, points3, COLOR, cv2.LINE_AA)


#-------------------------------------------------
#2. 위에서 만든 이미지덩어리를 화면에 보이기
cv2.imshow('image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()
