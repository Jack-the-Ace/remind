#객체검출: YOLO모델 사용 pip install ultralytics
import cv2
from ultralytics import YOLO

img= cv2.imread('images/bus.jpg')

model= YOLO('yolo26n.pt')

results= model.predict(
    source=img,
    conf=0.3,
    device="cpu"  #GPU사용할땐 device=0 or "cuda"
)
result= results[0]
print(result.names)
print("="*90)
for bbox in result.boxes:
    x1, y1, x2, y2 = map(int, bbox.xyxy[0].tolist())
    class_id= int(bbox.cls[0])
    confidence= float(bbox.conf[0])
    class_name= result.names[class_id]
    print(class_name, round(confidence,3))
    cv2.rectangle(img, (x1,y1), (x2,y2), (0,255,0), 3)

    label= f"{class_name} @ {confidence:.2f}"
    cv2.putText(img, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
#---------------------------------------------------------------------------------------
cv2.imshow('yolo object detection!@', img)
cv2.waitKey(0)
cv2.destroyAllWindows()
