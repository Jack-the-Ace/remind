#Open-Vocabulary Detection
#YOLO-world 모델로 기존 YOLO와 달리 텍스트로 찾고싶은 객체를 지정하여 검출할 수 있음.

from ultralytics import YOLOWorld

model=YOLOWorld('yolov8s-world.pt')

# 이 모델도 기본 COCO 데이터셋으로 훈련했기에 80개의 객체를 검출함.

# 내가 원하는 새로운 객체를 검출하려면.. 이 객체들의 이름을 모델에게 지정해줌.
# 인부들이 헬멧을 쓰고 있는지 검출
model.set_classes(['helmet','shoes','person'])

# 검출 테스트
results= model.predict('images/workers.webp')
results[0].show()