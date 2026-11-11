#웹갬으로 양팔 들기 감지
#원리: 양쪽 손목이 각각의 귀보다 위에 있으면 Up, 그렇지 않으면 Down 표시

import cv2
from ultralytics import YOLO

model= YOLO('yolo26n-pose.pt')

#웹캠 실행
cap= cv2.VideoCapture(0)

while True:
    ret, frame= cap.read()
    if not ret:
        break

    # 사람의 자세 추정
    results= model.predict(frame, conf=0.5, verbose=False)
    #한사람만 사용할 것이라서..
    result= results[0]

    state= "NORMAL"
    color= (0,255,0)

    #사람의 16개 관절들의 좌표... keypoints
    if result.keypoints is not None:
        #검출된 사람들의 관절 좌표 확인
        for person in result.keypoints.data.cpu().numpy():  #넘파이 배열로...
            
            left_ear= person[3]  #왼쪽 귀: 16개 좌표 중 3번 인덱
            right_ear= person[4] #오른쪽 귀: 16개 좌표 중 4번 인덱
            left_wrist= person[9]  #왼쪽 손목: 16개 좌표 중 9번 인덱
            right_wrist= person[10] #오른쪽 손목: 16개 좌표 중 10번 인덱

            #양쪽 손목이 귀 보다 위에 있는지 확인 (각 좌표(x,y) 중에서 y좌표만 확인)
            if left_wrist[1] < left_ear[1] and right_wrist[1] < right_ear[1]:
                state= "ARMS UP!"

    #인식 결과를 화면에 표시
    cv2.putText(frame, state, (30,50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)

    cv2.imshow('Yolo Pose', frame)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()






