# 동영상 or 웹캠 객체 검출

#0. 모듈 사용
import cv2
from ultralytics import YOLO

#1. 영상 준비
source= 'videos/solution_ci_pose_demo.mp4'
source= 'videos/solutions_ci_demo.mp4'
source= 'videos/vtest.avi'
source=0 #웹캠

#2. 동영상 캡쳐
cap= cv2.VideoCapture(source)
if not cap.isOpened():
    raise RuntimeError('동영상 또는 웹캠을 열 수 없습니다.')

#3. 욜로 모델 불러오기
model= YOLO('yolo26n.pt')

#4. 기존 동영상의 정보(너비,높이,fps) 가져오기, 결과 동영상 저장을 위한 코덱 준비
width= int( cap.get(cv2.CAP_PROP_FRAME_WIDTH) )
height= int( cap.get(cv2.CAP_PROP_FRAME_HEIGHT) )
fps= cap.get(cv2.CAP_PROP_FPS)
if fps <=0:
    fps=30

#코덱 및 비디오저장 객체 생성
fourcc= cv2.VideoWriter_fourcc(*'mp4v')
out= cv2.VideoWriter('output/yolo_video_result.mp4', fourcc, fps, (width, height))

#5. 프레임별 객체 검출
while True:
    #동영상에서 한 프레임 얻어오기
    ret, frame= cap.read()
    if not ret:
        break

    #YOLO 객체 검출 요청
    results= model.predict(
        source=frame,
        conf=0.4, # 신뢰점수가 0.4 이상인 객체만 검출
        device=0, # GPU
        verbose=False
    )

    #현재 프레임의 결과만 추출
    result= results[0]

    #bounding box, 클래스명, 신뢰도 자동 표시
    annotated_img= result.plot()

    #현재 프레임에 객체가 몇개 검출되고 있는지 확인
    count= len(result.boxes)

    #개수를 이미지 위에 글씨로 표시
    cv2.putText(annotated_img, f"objects: {count}", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)

    #저장 및 보여주기
    out.write(annotated_img)
    cv2.imshow('yolo video detection', annotated_img)

    if cv2.waitKey(1) == ord('q'):
        break

#프로그램 종료
cap.release()
out.release()
cv2.destroyAllWindows()


