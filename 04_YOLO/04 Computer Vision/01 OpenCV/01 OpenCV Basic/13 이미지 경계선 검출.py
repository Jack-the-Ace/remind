import cv2
img= cv2.imread('images/snowman.png')
cv2.imshow('image', img)

# 캐니 알고리즘으로 경계선 추출 (색상이 급격하게 바뀌는 픽셀영역을 추출)

edges= cv2.Canny(img, 150, 200)
#150 (threshold1, 하한값) : 엣지로 판단할 최소 임계값
#200 (threshold2, 상한값) : 확실한 엣지로 판단할 임계값
#150~200 은? 주변을 계속 따라가다 보니... 210이 나타나면... 그놈은 엣지로 판별
#150~200 은? 주변을 계속 따라가다 보니... 130이 나타나면... 그놈은 엣지가 아닌걸로 판별

cv2.imshow('canny edge image', edges)




#-------------------------
cv2.waitKey(0)
cv2.destroyAllWindows()
