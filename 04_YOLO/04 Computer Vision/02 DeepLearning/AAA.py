#0. 모듈 사용
import cv2
import numpy as np
from insightface.app import FaceAnalysis

img1= cv2.imread('images/jack.jpg')

app= FaceAnalysis(
    name="buffalo_l",  #buffalo large 모델 320MB 정도.. github에서 모델 종류 확인 가능
    allowed_modules=['detection', 'recognition'],  #모델 팩 내부에 기능별로 있는 모듈 선택 -- 외에도 landmark_2d_106, landmark_3d_68, genderage(성별/나이 예측)
    providers= ['CPUExecutionProvider']  # "CUDAExcutionProvider"
)
app.prepare(ctx_id=-1, det_size=(640,640))

faces1= app.get(img1) # 결과 : boundingbox, embedding 등
print(len(faces1))

#각 사진에 얼굴이 1개만 있는지 확인(인식을 위해)
if len(faces1) != 1:
    raise ValueError('기준 이미지에 얼굴이 한명만 검출되어야 인식이 가능합니다.')

# 각 사진들에서 얼굴 하나씩 추출
face1= faces1[0]

#5. 검출된 얼굴의 특성 벡터 추출 (Embedding)     내장된, 내재된
embedding1= face1.normed_embedding  #노름(norm): 선형대수학에서 벡터의 크기나 길이를 측정하는 함수.. 넘파이에도 있었음
# 얼굴 이미지를 숫자 벡터로 표현

print('임베딩된 크기:', embedding1.shape)
#print(embedding1)

# 특정 임계값 이상이면 동일인으로 판단
threshold= 0.4
if similarity >= threshold:
    print('동일인으로 판단')
else:
    print('다른 사람으로 판단')

#6. 얼굴 bounding box 표시 -- opencv로 얼굴 영역에 녹색 사각형 표시
#boundingbox의 좌상단, 우하단 좌표
x1, y1, x2, y2= face1.bbox.astype(int)
cv2.rectangle(img1, (x1,y1), (x2,y2), (0,255,0), 2)  #image, 좌상단좌표, 우하단좌표, 색상, 두께

x1, y1, x2, y2= face2.bbox.astype(int)
cv2.rectangle(img2, (x1,y1), (x2,y2), (0,255,0), 2)  


cv2.imshow('face1', img1)
cv2.imshow('face2', img2)

cv2.waitKey(0)
cv2.destroyAllWindows()
