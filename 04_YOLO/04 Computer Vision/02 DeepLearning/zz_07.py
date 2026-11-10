# -obb모델 (Oriented Bounding Box 회전된 경계 객체): 객체 방향에 맞춰 회전
from ultralytics import YOLO
model= YOLO('yolo26n-obb.pt')  # OBB모델사용
results= model.predict(
    source="images/boats.jpg",
    conf=0.25,
    imgsz=1024,
    device=0
)
print('obb모델의 총 분류명 목록:', results[0].names)
print('검출된 개수:',len(results[0].obb))
results[0].show()