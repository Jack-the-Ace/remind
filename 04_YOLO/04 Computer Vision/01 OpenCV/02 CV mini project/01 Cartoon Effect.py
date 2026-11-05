# 사진을 만화처럼

import cv2

#원본이미지
img= cv2.imread('images/woman.jpg')
img= cv2.imread('images/dog1.jpg')

if img is None:
    raise FileNotFoundError('이미지 파일을 찾을 수 없어요!!')

img= cv2.resize(img, (600, 400))
cv2.imshow('original', img)

#색상을 단순화 
#평균이동(meanshift) 알고리즘을 적용
color= cv2.pyrMeanShiftFiltering(
    img,
    sp=20,  #주변 픽셀을 탐색하는 공간 범위
    sr=40,  #주변 색상이 비슷하다 라고 판단하는 범위
)
cv2.imshow('cartoon color image', color)

#조금 더 만화처럼 보이도록 윤곽선을 그려내기
#1)흑백으로..
gray= cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#2)잔털이나 잡티나 노이즈를 제거하기 위해 블러처리
blur= cv2.GaussianBlur(gray, (9,9), 0)  # 9x9 필터 사용
cv2.imshow('blur', blur)
#3) 주요 경계선 검출
edges= cv2.Canny(blur, 80, 160)
cv2.imshow('edges image', edges)
#4) 주요 경계선을 검정색으로 표시(카툰의 선 처럼)
cartoon= color.copy()
cartoon[edges>0] = (10,10,10)  # 어두운 BGR
cv2.imshow('cartoon image', cartoon)

#결과 저장
cv2.imwrite('cartoon.jpg', cartoon)






#--------------------
cv2.waitKey(0)
cv2.destroyAllWindows()

