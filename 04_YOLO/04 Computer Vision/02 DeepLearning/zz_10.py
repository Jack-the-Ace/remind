import cv2
from ultralytics import YOLO

source= 'videos/solutions_ci_demo.mp4'
source= 0

cap= cv2.VideoCapture(source)
if not cap.isOpened():
    raise RuntimeError('동영상 또는 웹캠을 열 수 없습니다.')

model= YOLO('yolo26n.pt')

width= int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height= int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps= cap.get(cv2.CAP_PROP_FPS)
if fps <= 0:
    fps= 30

fourcc= cv2.VideoWriter_fourcc(*'mp4v')
out= cv2.VideoWriter('output/yolo_video_result.mp4', fourcc, fps, (width,height))

while True:
    ret, frame= cap.read()
    if not ret:
        break

    results= model.predict(
        source= frame,
        conf= 0.4,
        device= 0,
        verbose= False
    )
    result= results[0]

    annotated_img= result.plot()

    count= len(result.boxes)

    cv2.putText(annotated_img, f"objects: {count}", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)

    out.write(annotated_img)
    cv2.imshow('YOLO Video Detection', annotated_img)

    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
out.release()
cv2.destroyAllWindows()
