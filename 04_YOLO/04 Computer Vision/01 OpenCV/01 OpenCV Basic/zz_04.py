import cv2
import numpy as np
img= np.zeros( (480,640,3), dtype= np.uint8 )
img[:]= (255,255,255) 
img[:]= (255,0,0)
print(img)

img[100:200, 200:300] = (255,255,255)

COLOR= (0,255,255)
THICKNESS= 3

cv2.line(img, (50,100),(400,50), COLOR, THICKNESS, cv2.LINE_4)
cv2.line(img, (50,200),(400,150), COLOR, THICKNESS, cv2.LINE_8)
cv2.line(img, (50,300),(400,250), COLOR, THICKNESS, cv2.LINE_AA)

COLOR= (255,255,0)
THICKNESS= 10
RADIUS= 50

cv2. circle(img, (200,350), RADIUS, COLOR, THICKNESS, cv2.LINE_AA)
cv2.circle(img, (400,350), RADIUS, COLOR, cv2.FILLED, cv2.LINE_AA)

COLOR= (0,0,255)
THICKNESS= 3

points= np.array([[100,100],[200,100],[100,200]])
points2= np.array([[200,100],[300,100],[300,200]])

cv2.polylines(img, [points, points2], True, COLOR, THICKNESS, cv2.LINE_AA)

points3= np.array([
    [[100,300],[200,300],[100,400]],
    [[200,300],[300,300],[300,400]]
])
cv2.fillPoly(img, points3, COLOR, cv2.LINE_AA)

#-----------------------------------
cv2.imshow('image', img)
cv2.waitKey(0)
cv2.destroyAllWindows()