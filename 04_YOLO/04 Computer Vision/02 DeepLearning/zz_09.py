from ultralytics import YOLOWorld

model= YOLOWorld('yolov8s-world.pt')

model.set_classes(['helmet','shoes','glove'])

results=model.predict('images/workers.webp')
results[0].show()