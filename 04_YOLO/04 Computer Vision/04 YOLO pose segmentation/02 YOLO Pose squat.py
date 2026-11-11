# 스쿼트 횟수 자동 카운팅 모델 만들기
# 동작원리 : 엉덩이, 무릎, 발목 사이의 각도를 계산하여 자세 추정

#1) 일어선 자세 : 엉덩이, 무릎, 발목이 일직선이 되기에 약 170도 정도
#2) 앉은 자세 : 엉덩이, 무릎, 발목 사이 각도가 약 90도 정도
#3) 다시 선 자세 : 엉덩이, 무릎, 발목이 일직선이 되기에 약 170도 정도

import cv2
import numpy as np
from ultralytics import YOLO

#1. 세 관절로 무릎 각도 계산해주는 함수 만들어놓기
def calculate_angle(hip, knee, ankle):
    a= hip-knee  #엉덩이-무릎 사이 직선의 벡터
    b= ankle-knee #발목-무릎 사이 직선의 벡터

    # 두 벡터 사이의 각도
    cos_angle= np.dot(a,b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8) # 1e-8: 분모가 0이 되지 않도록 하는 아주 작은 상수값
    # 코사인 각도는 -1~1 사이의 숫자를 '몇 도'로 변환하기
    angle= np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))

    return angle


model= YOLO('yolo26n-pose.pt')
cap= cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError('카메라 또는 동영상 불가!')

count=0 #스쿼트 횟수
state= "READY" #상태값(서있는지, 앉아있는지)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    result= model.predict(frame, conf=0.5, verbose=False)[0]
    frame= result.plot()  #17개의 지점을 그린 이미지 프레임 만들기

    if result.keypoints is not None and len(result.keypoints)>0:
        person= result.keypoints.data[0].cpu().numpy()
        #모델이 반환하는 키포인트 데이터는 [x좌표, y좌표, 신뢰도 점수]로 구성되어 있음.

        #측면을 바라보고 있다는 가정으로..
        #왼쪽 오른쪽 중에서 신뢰도가 높은 좌표로 계산

        #엉덩이, 무릎, 발목
        left= [11,13,15]
        right= [12,14,16]

        ids= left if min(person[left,2]) >=  min(person[right,2]) else right

        # 관절이 일정 수준 이상 정확히 검출되었을 때만 카운팅
        if min(person[ids,2]) >= 0.5:
            hip, knee, ankle= person[ids, :2] #각 지점의 x좌표, y좌표만 추출

            # 3개 지점 사이의 각도 계산
            angle= calculate_angle(hip, knee, ankle)

            # 자세 추정
            #1) 무릎을 펴면 up
            if angle >= 160:
                if state=="DOWN":  #이전 상태가 앉아있었다면..
                    count += 1     #다시 선 상태니까.. 카운트 +1업
                state= "UP"

            #2) 앉은 상태면 DOWN
            if angle <= 110 and state=="UP":
                state="DOWN"

            # 무릎 각도 이미지에 표시
            cv2.putText(
                frame,
                f"ANGLE: {angle:.0f}",
                (20,100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (255,255,0), 2)

    #스쿼트 횟수, 자세 표시
    cv2.putText(frame, f"SQUATS: {count}",
                (20,50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1, (0,255,0), 3)

    
    cv2.putText(frame, f"STATE: {state}",
                (20,1400),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0,255,255), 2)

    cv2.imshow("YOLO Squat Counter", frame)

    key= cv2.waitKey(1)

    if key== ord('q'):
        break
    elif key== ord('r'):
        count=0
        state="READY"

cap.release()
cv2.destroyAllWindows()

