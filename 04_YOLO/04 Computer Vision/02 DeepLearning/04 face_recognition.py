# 얼굴인식 (같은 얼굴인지 판별 - 유사도 검사)
# 출입 시스템 같은 곳에 많이 활용

# 모듈 설치
# pip install insightface

#0. 모듈 사용
import cv2
import numpy as np
from insightface.app import FaceAnalysis

#1. 비교할 사진 2장 준비
# 1) 동일인물 2장
# img1= cv2.imread('images/face_sonny.jpg')
# img2= cv2.imread('images/face_sonny2.jpg')

# img1= cv2.imread('images/face_kimyuna2.jpg')
# img2= cv2.imread('images/face_kimyuna3.jpg')

# 다른 인물 2장
# img1= cv2.imread('images/face_sonny.jpg')
# img2= cv2.imread('images/face_kimyuna3.jpg')

# 같은 인물 옆모습 비교
# img1= cv2.imread('images/face_sonny.jpg')
# img2= cv2.imread('images/face_sonny5.jpg')

# 같은 인물 안경착용 비교
# img1= cv2.imread('images/face_sonny.jpg')
# img2= cv2.imread('images/face_sonny6.jpg')

# 같은 인물 마스크착용 비교
img1= cv2.imread('images/face_sonny.jpg')
img2= cv2.imread('images/face_sonny7.jpg')

#2. 얼굴 인식기 객체를 생성
app= FaceAnalysis(
    name="buffalo_l",  #buffalo large 모델 320MB 정도.. github에서 모델 종류 확인 가능
    allowed_modules=['detection', 'recognition'],  #모델 팩 내부에 기능별로 있는 모듈 선택 -- 외에도 landmark_2d_106, landmark_3d_68, genderage(성별/나이 예측)
    providers= ['CPUExecutionProvider']  # "CUDAExecutionProvider"
)

#3. 얼굴인식기 객체를 초기화
app.prepare(ctx_id=-1, det_size=(640,640))  # ctx_id : GPU 디바이스 번호 0,1,2,... CPU를 사용한다면 -1
#det_size : 얼굴 검출에 사용하는 입력 크기 ~ 원본의 가로세로 비율을 유지하면서 resize함. 나머지 공간은 padding 처리됨.

#4. 두 이미지에서 얼굴 검출 및 유사도 비교를 위한 특징 추출
faces1= app.get(img1)  #opencv로 읽어들인 이미지를 주고 얼굴들 검출 요청
faces2= app.get(img2)  #얼굴검출 + 특징추출
# 결과 : boundingbox, embedding 등
print(len(faces1), len(faces2))

#각 사진에 얼굴이 1개만 있는지 확인(인식을 위해)
if len(faces1) != 1 or len(faces2) != 1 :
    raise ValueError('각 이미지에 얼굴이 한명씩 검출되어야 인식이 가능합니다.')

# 각 사진들에서 얼굴 하나씩 추출
face1= faces1[0]
face2= faces2[0]

#5. 검출된 얼굴의 특성 벡터 추출 (Embedding)     내장된, 내재된
embedding1= face1.normed_embedding  #노름(norm): 선형대수학에서 벡터의 크기나 길이를 측정하는 함수.. 넘파이에도 있었음
embedding2= face2.normed_embedding  #정규화된 얼굴 특성 값
# 얼굴 이미지를 숫자 벡터로 표현

print('임베딩된 크기:', embedding1.shape)
print('임베딩된 크기:', embedding2.shape)
#print(embedding1)

#6. 벡터값들의 유사도 계산하여 이미지의 유사성을 알아내기 - 코사인 유사도 (두 벡터 사이의 각도)
similarity= np.dot(embedding1, embedding2)  # dot: 두 벡터의 내적곱 - 같은 자리의 요소끼리 곱
#코사인 각도의 범위: -1 ~ 1  [1에 가까울수록 유사성이 높다!]
print(f"얼굴 유사도: {similarity:.4f}")

# 특정 임계값 이상이면 동일인으로 판단
threshold= 0.4
if similarity >= threshold:
    print('동일인으로 판단')
else:
    print('다른 사람으로 판단')

#7. 얼굴 bounding box 표시 -- opencv로 얼굴 영역에 녹색 사각형 표시
#boundingbox의 좌상단, 우하단 좌표
x1, y1, x2, y2= face1.bbox.astype(int)
cv2.rectangle(img1, (x1,y1), (x2,y2), (0,255,0), 2)  #image, 좌상단좌표, 우하단좌표, 색상, 두께

x1, y1, x2, y2= face2.bbox.astype(int)
cv2.rectangle(img2, (x1,y1), (x2,y2), (0,255,0), 2)  


cv2.imshow('face1', img1)
cv2.imshow('face2', img2)

cv2.waitKey(0)
cv2.destroyAllWindows()

#수행과제..
#웹캠으로 출입시스템 구현.
#본인 사진 하나를 준비해놓고. 웹캠으로 들어온 영상의 인물 비교!