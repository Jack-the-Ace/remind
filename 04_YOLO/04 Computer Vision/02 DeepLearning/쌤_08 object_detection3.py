# Ultralytics의 다른 데이터셋들 로드하여 새로 학습 시키기
# 기본모델은 COCO 데이터셋으로 훈련된 모델임.

#0. 모듈 사용
from ultralytics import YOLO

#1. COCO 사전학습된 모델 불러오기
model= YOLO('yolo26n.pt')

#2. 작은 데이터셋으로 학습시키는 연습
model.train(
    data="coco8.yaml", #학습,테스트용 데이터셋 경로와 클래스명 등을 설명한 문서(학습방법을 작성한 설정문서). ultralytics에 내장된 설정파일을 불러와서 사용해보기. 처음 한번 다운로드함.
    epochs=10,
    imgsz=640,
    batch=4,
    #device=0  #0을 쓰면 GPU, -1: CPU . 안쓰면.. 자동으로 선택(GPU우선)
    workers=0
)

#3. 학습된 모델 불러오기
# 위 학습을 완료하면 runs 폴더가 새로 생겨있을 것임.
# runs/detect/train/weights/폴더안에
# 가장 성능이 좋았던 best 모델의 가중치값을 저장한 .pt 파일이 생김
# best.pt 로 새로운 YOLO 모델을 만들기

#trained_model= YOLO('runs/detect/train/weights/best.pt')
trained_model= YOLO(str(model.trainer.best))

#4. 새로운 모델에게 객체 검출 요청하기
results= trained_model.predict(source='images/bus.jpg', save=True)

#5. 바운딩박스가 그려진 결과를 이미지로 보기
results[0].show()
