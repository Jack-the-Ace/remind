# -obb 모델 (Oriented Bounding Box 회전된 경계 객체): 객체 방향에 맞춰 회전

from ultralytics import YOLO

model= YOLO('yolo26n-obb.pt')  # OBB모델 사용

results= model.predict(
    source="images/boats.jpg",
    #source="images/zidane.jpg",  <--- 학습하지 않은건 검출 못함
    conf=0.25,
    imgsz=1024,  # 작은 개체의 특징을 더 잘 유지하도록 입력 해상도 증가
    device= 0   #GPU 사용
)

print('obb모델의 총 분류명 목록:', results[0].names)  # 15개

print('검출된 개수:', len(results[0].obb))  # boxes 대신 obb 속성 사용
#바운딩 박스 그려내기..가 짜증..
#욜로 모델이 알아서 바운딩 박스를 그려서 이미지로 보여주는 기능을 가지고 있음.
results[0].show()


# 모델이 훈련하지 않은 객체분류가 필요하다면???
# 다른 데이터셋으로 훈련시켜야 함.

