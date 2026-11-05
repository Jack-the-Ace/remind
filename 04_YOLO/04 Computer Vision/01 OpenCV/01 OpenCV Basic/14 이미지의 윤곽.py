#윤곽선 (contour) : 경계선을 연결한 선 (어떤 형태의 모양인지 완전하게 보여주는 선)

import cv2
img= cv2.imread('images/card.png')
cv2.imshow('image', img)

#1) 흑백이미지로 단순화. 윤곽을 찾을때 색상정보는 필요없으니..
gray= cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imshow('gray image', gray)

#2) 이진화를 위해 오츠알고리즘 사용
ret, otsu= cv2.threshold(gray, -1, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
cv2.imshow('otsu image', otsu)

#3) 이진화된 이미지에서 개체의 외곽선(윤곽선) 정보를 추출
contours, hierachy= cv2.findContours(otsu, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
#contours: 윤곽선 정보, hierachy: 윤곽선의 계층구조
#cv2.RETR_EXTERNAL : 가장 외곽의 윤곽만 추출 (카드 4장)
#cv2.RETR_LIST : 모든 윤곽을 계층구조 상관없이 리스트로..
#cv2.CHAIN_APPROX_NONE : 윤곽선을 구성하는 근사화 방법 지정. 모든 점들을 압축없이.. 그대로 저장

#윤곽선 정보를 기반으로 원본 이미지에 윤곽선을 그리기..
target_img= img.copy()  #원본 칼라 이미지를 복제

#윤곽선을 그릴 색상
COLOR= (0, 225, 0)  #녹색
#cv2.drawContours(image=target_img, contours=contours, contourIdx=0, color=COLOR) # 윤곽중에서 첫번째 윤곽만 그리기
cv2.drawContours(image=target_img, contours=contours, contourIdx=-1, color=COLOR) # contourIdx=-1 --> 모든 윤곽
cv2.imshow('contours image', target_img)

# 윤곽선을 통해 개체의 위치를 식별하는 사각형 영역 : bounding box
for contour in contours:
    x, y, width, height= cv2.boundingRect(contour)
    cv2.rectangle(target_img, (x,y), (x + width, y + height), COLOR, thickness=2)  #사각형의 좌상단좌표, 우하단좌표

cv2.imshow('bounding box image', target_img)

#윤곽선의 면적을 이용하여 일정크기 이상만 검출하도록
target_img2= img.copy()

for contour in contours:
    if cv2.contourArea(contour) > 250:
        x,y,width, height= cv2.boundingRect(contour)
        cv2.rectangle(target_img2, (x,y), (x+width, y+height), COLOR, thickness=3)

cv2.imshow('bounding box image2', target_img2)


#----------------------
cv2.waitKey(0)
cv2.destroyAllWindows()