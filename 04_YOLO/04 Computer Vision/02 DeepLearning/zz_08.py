from ultralytics import YOLO

model= YOLO('yolo26n.pt')

model.train(
    data= "coco8.yaml",
    epochs=10,
    imgsz=640,
    batch=4,
    workers=0
)

#trained_model= YOLO('runs/detect/train/weights/best.pt')
trained_model= YOLO(str(model.trainer.best))

results= trained_model.predict(source='images/bus.jpg', save=True)

results[0].show()