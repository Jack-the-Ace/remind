#얼굴인식 (유사도검사) 출입 시스템 같은 곳에 많이 활용
# pip install insightface
import cv2
import numpy as np
from insightface.app import FaceAnalysis

img1= cv2.imread('images/face_sonny.jpg')
img2= cv2.imread('images/face_sonny7.jpg')

app= FaceAnalysis(
    name="buffalo_l",
    allowed_modules=['detection', 'recognition'],
    providers= ['CPUExecutionProvider']  # "CUDAExecutionProvider"
)
app.prepare(ctx_id=-1, det_size=(640,640))

faces1= app.get(img1)
faces2= app.get(img2)
print(len(faces1), len(faces2))

if len(faces1) !=1 or len(faces2) !=1:
    raise ValueError('각 이미지에 얼굴이 한 명씩 검출되어야 인식이 가능합니다.')

face1= faces1[0]
face2= faces2[0]
embedding1= face1.normed_embedding
embedding2= face2.normed_embedding
print('임베딩된 크기1:', embedding1.shape)
print('임베딩된 크기2:', embedding2.shape)

similarity= np.dot(embedding1, embedding2)\
#코사인 각도의 범위: -1 ~ 1 [1에 가까울수록 유사성이 높다!]
print(f"얼굴 유사도: {similarity:.4f}")

threshold= 0.4
if similarity >= threshold:
    print('동일인으로 판단')
else:
    print('다른 사람으로 판단')

x1, y1, x2, y2= face1.bbox.astype(int)
cv2.rectangle(img1, (x1,y1), (x2,y2), (0,255,0), 2)

x1, y1, x2, y2= face2.bbox.astype(int)
cv2.rectangle(img2, (x1,y1), (x2,y2), (0,255,0), 2)

cv2.imshow('face1', img1)
cv2.imshow('face2', img2)

cv2.waitKey(0)
cv2.destroyAllWindows()
