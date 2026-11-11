#0. 모듈 사용
import cv2
from ultralytics import YOLO

#1. segmentation 모델 불러오기
model= YOLO('yolo26n-seg.pt')
#사전학습된 모델이기에 80개의 객체에 대한 이미지분할 가능함.
#커스텀은 roboflow를 이용한 라벨링 및 데이터셋 구축

#cap= cv2.VideoCapture(0)
cap= cv2.VideoCapture('test-videos/people-detection.mp4')
if not cap.isOpened():
    raise RuntimeError('웹캠 또는 동영상 연결 불가')

#실시간 위험구역 침입 감시
while True:
    ret, frame= cap.read()
    if not ret:
        break

    #화면 크기 동일
    frame= cv2.resize(frame, (640,640))
    h, w= frame.shape[:2]  #프레임의 사이즈

    #위험 구역의 좌표
    zone_x= int(w*0.65)  #화면 너비의 65% 이상 지점을 모두 위험구역
    zone_y= int(h*0.3)   #화면 높이의 30% 이상 지점을 모두 위험구역

    # yolo segmentation 모델에게 이미지 분할 요청
    result= model.predict(
        frame,
        classes=[0],  #이 모델은 80개의 객체를 분할하지만.. 이 실습에서는 첫번째 클래스인 person만 검출
        conf=0.4,
        retina_masks= True, #사람 윤곽에 마스크 표시
        verbose=False 
    )[0]

    # 마스킹 표시된 이미지 얻어오기
    masked_img= result.plot()

    # 객체의 윤곽영역 픽셀들(마스크)이 위험구역 픽셀들과 얼마나 겹치는지 검사
    danger= False

    if result.masks is not None:
        masks= result.masks.data.cpu().numpy()

        #검출된 모든 사람들의 픽셀들... 처리
        for mask in masks:  
            #위험구역에 포함된 사람의 마스크 픽셀개수
            overlap= mask[:zone_y, zone_x:].sum()
            print('겹친 구간의 픽셀 수:', overlap)

            #위험구역과 겹친 픽셀의 개수가 1000개 이상이면..
            if overlap > 1000:
                danger= True
                break

    #위험구역과 판정 결과를 표시
    cv2.rectangle(
        masked_img,
        (zone_x, 0),
        (w-1, zone_y),
        (0,0,255),
        3
    )
    cv2.putText(
        masked_img,
        "-Danger Zone-",
        (zone_x+5, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55, (0,0,255), 2
    )

    #침입여부에 따른 상태 표시
    status= "DANGER" if danger else "SAFE"
    color= (0,0,255) if danger else (0,255,0)
    cv2.putText(
        masked_img,
        status,
        (20, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5, color, 3
    )

    cv2.imshow('YOLO Segmentation Safety', masked_img)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()


#수행과제
#책. 컴퓨터비전과 딥러닝 chapter9 ~ chapter10 읽고 예제 따라하기.