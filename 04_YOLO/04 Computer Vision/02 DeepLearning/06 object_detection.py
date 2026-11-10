#객체 검출 : YOLO모델 사용

#YOLO 모델을 배포하는 ultralytics 회사의 모듈을 설치
# pip install ultralytics

#0. 모듈 사용
import cv2
from ultralytics import YOLO

#1. 이미지 준비
img= cv2.imread('images/bus.jpg')
img= cv2.imread('images/zidane.jpg')
img= cv2.imread('images/boats.jpg')
# 분류명 중에 boats 가 존재함. 근데. 인식이 안된다면.. 훈련하지 않았던 시점의 사진(훈련은 옆/앞모습으로 훈련했음. 우리 사진은 위에서 내려다본 사진)
# 모델 중에서 회전된 객체들이 있을때 사용하도록 훈련된 모델도 존재함. -obb 모델

#2. 사전학습된 YOLO 모델 불러오기
model= YOLO('yolo26n.pt')  #파이토치의 가중치 파일 .pt파일로 모델 복원
# yolo26 nano 모델은 COCO 데이터셋을 훈련. 80개 객체 클래스 검출

#3. 이미지에서 객체를 검출
results= model.predict(
    source=img,
    conf=0.3,     # 신뢰도 점수가 0.3 이상인 것만 검출
    device= "cpu" # cpu에서 추론. GPU 사용할때는. device=0, or device="cuda"
)

#이미지를 1개만 주었으니.. 검출결과도 1개만 사용
result= results[0]

# yolo 모델의 분류명을 알고싶다면.
print('YOLO모델의 분류명 목록:', result.names)
print("-"*60)

#4. 검출된 객체 정보 추출
for bbox in result.boxes:  #검출된 객체들의 바운딩박스들
    #1) bounding box의 좌표 얻어오기
    #얻어온 좌표는 pytorch의 2차원 텐서데이터[[]]로 전달됨. 이 텐서데이터를  .tolist()로 파이썬 기본 리스트로 변환
    x1, y1, x2, y2 = map( int, bbox.xyxy[0].tolist() )  # map(int,...) 소수점 좌표를 정수로 변환

    #2) 객체의 클래스(분류) 번호
    class_id= int(bbox.cls[0])  # 2차원 텐서로 결과를 주기 때문에..

    #3) 객체의 검출 신뢰도 점수
    confidence= float(bbox.conf[0])  #2차원 텐서를 1차원 float값으로 추출

    #4) 객체의 분류번호를 화면에 표시하면 알아보기 어려워서.. 분류명 글씨로..
    class_name= result.names[class_id]

    print(class_name, round(confidence,3))

    #5. opencv를 이용하여 바운딩 박스 표시
    cv2.rectangle(img, (x1,y1), (x2,y2), (0,255,0), 3)

    # 라벨명도 박스영역 위에 표시하기
    label= f"{class_name} {confidence:.2f}"
    cv2.putText(img, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
#--------------------------------------------------------------------------------------

cv2.imshow('yolo object detection', img)

cv2.waitKey(0)
cv2.destroyAllWindows()


