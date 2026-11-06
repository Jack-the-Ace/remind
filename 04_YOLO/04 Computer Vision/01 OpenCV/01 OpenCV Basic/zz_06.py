import cv2

img= cv2.imread('images/pome.png', cv2.IMREAD_GRAYSCALE)
cv2.imshow('gray image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()

result= cv2.imwrite('saved/img.jpg', img)
print('저장결과:', result)

img2= cv2.imread('images/receipt.jpg', cv2.IMREAD_GRAYSCALE)
cv2.imwrite('saved/img2.png', img2)

# 동영상 저장~
