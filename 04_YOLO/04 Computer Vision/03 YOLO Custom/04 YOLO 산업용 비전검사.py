#동영상이나 웹캠의 부품들의 수량을 검사하는 모델

import cv2
from collections import Counter
from ultralytics import YOLO

model= YOLO('yolo_model/best.pt')
print(model.names)

# 정상 포장 기준 수량
required= {'Bolt':2, 'Nut':2, 'Washer':2}

#cv2.VideoCapture(0)  #웹캠 -- 실무현장은 카메라..
cap= cv2.VideoCapture('test-videos/bolt-nut-washer.mp4')  #동영상
if not cap.isOpened():
    raise RuntimeError('카메라 또는 동영상 연결불가!')

while True:
    ret, frame= cap.read()
    if not ret:
        break

    result= model.predict(frame, conf=0.5, verbose=False)[0]

    #부품 수량 계산
    counts= Counter(result.names[int(cls)] for cls in result.boxes.cls.tolist())

    #각 부품이 모두 2개씩인지 확인
    passed= all( counts[name]==required[name] for name in required )

    # bounding box와 클래스명, 신뢰도 점수가 표시된 이미지 얻어오기
    frame= result.plot()

    # PASS/FAIL 판정 표시
    h, w = frame.shape[:2]  #[h:w:c] 중에서 height, width만 추출

    # 표시할 글씨
    state= "[PASS]" if passed else "[FAIL]"
    # 색상
    color= (0,255,0) if passed else (0,0,255)  # BGR순
    # 폰트
    font= cv2.FONT_HERSHEY_SIMPLEX

    # 표시될 글씨의 총 너비,높이 추출
    (tw,th), _ = cv2.getTextSize(state, font, 2, 4) # 2:글씨 크기배율, 4:글씨 선두께
    # _ (baseline): 텍스트의 가장 아래 기준선...

    #우상단에 검은색 배경
    cv2.rectangle(frame, (w-tw-30, 10), (w-10, th+35), (0,0,0), -1)
    # 초록색 PASS 또는 빨간색 FAIL
    cv2.putText(frame, state, (w-tw-20, th+20), font, 2, color, 4)

    #부품별 수량 표시 (좌측 하단에)
    count_text= f"BOLT:{counts['Bolt']} NUT:{counts['Nut']} WASHER:{counts['Washer']}"
    cv2.putText(frame, count_text, (20,h-20), font, 0.8, (0,128,0), 2)

    #프레임 보여주기
    cv2.imshow('YOLO Parts Inspectation', frame)

    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

