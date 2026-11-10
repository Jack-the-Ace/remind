import cv2
import numpy as np
from insightface.app import FaceAnalysis

# 1. 비교 기준 사진
img1 = cv2.imread('images/jack.jpg')

# 2. 얼굴 인식 모델 준비
app = FaceAnalysis(
    name='buffalo_l',
    allowed_modules=['detection', 'recognition'],
    providers=['CPUExecutionProvider']
)
app.prepare(ctx_id=-1, det_size=(640, 640))

# 3. 기준 사진의 얼굴 특징 추출
faces1 = app.get(img1)

if len(faces1) != 1:
    raise ValueError('기준 사진에서 얼굴이 한 명만 검출되어야 합니다.')

embedding1 = faces1[0].normed_embedding

# 4. 웹캠 연결
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    raise ValueError('웹캠 연결 실패')

# 5. 실시간 얼굴 비교
while True:
    ret, frame = cap.read()

    if not ret:
        break

    faces2 = app.get(frame)

    for face in faces2:
        embedding2 = face.normed_embedding
        similarity = np.dot(embedding1, embedding2)

        if similarity >= 0.4:
            message = 'MATCH'
            color = (0, 255, 0)
        else:
            message = 'NOT MATCH'
            color = (0, 0, 255)

        x1, y1, x2, y2 = face.bbox.astype(int)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f'{message}: {similarity:.2f}',
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2
        )

    cv2.imshow('Real-time Face Recognition', frame)

    # Q 키로 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()