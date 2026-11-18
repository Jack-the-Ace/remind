# 수업 흐름: VideoCapture → 프레임 읽기 → model.track → OpenCV 표시
from pathlib import Path
import argparse
import json

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
VEHICLES = {"car", "bus", "truck", "motorcycle"}


def appearance(frame, box):
    # 차량 부분만 잘라 밝기 모양과 색 분포를 기억합니다. 야간에는 이것도 완벽하지 않습니다.
    x1, y1, x2, y2 = map(int, box)
    h, w = frame.shape[:2]
    crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return None
    small = cv2.resize(crop, (48, 32))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256])
    return gray, cv2.normalize(hist, None).flatten()


class Target:
    def __init__(self):
        self.box = None
        self.track_id = None
        self.last_frame = 0
        self.look = None
        self.velocity = np.zeros(2)
        self.pending = None
        self.streak = 0

    def select(self, detection, frame, number):
        self.box = np.array(detection['box'], dtype=float)
        self.track_id = detection['id']
        self.look = appearance(frame, self.box)
        self.last_frame = number
        self.velocity = np.zeros(2)
        self.pending = None
        self.streak = 0

    def update(self, detections, frame, number):
        if self.box is None:
            return None
        gap = number - self.last_frame
        # 1초 넘게 놓치면 자동 연결을 멈춥니다. 사용자가 다시 선택해야 합니다.
        if gap > 30:
            return None
        size = np.maximum(self.box[2:] - self.box[:2], 1)
        center = (self.box[:2] + self.box[2:]) / 2
        predicted = center + self.velocity * min(gap, 10)
        candidates = []
        for d in detections:
            if d['id'] is None:
                continue
            b = np.array(d['box'])
            ratio = (b[2:] - b[:2]) / size
            distance = np.linalg.norm(((b[:2] + b[2:]) / 2 - predicted) / size)
            if np.any(ratio < .5) or np.any(ratio > 2) or distance > min(1.4, .65 + gap * .04):
                continue
            look = appearance(frame, b)
            if look is None or self.look is None:
                continue
            shape = float(cv2.matchTemplate(look[0], self.look[0], cv2.TM_CCOEFF_NORMED)[0, 0])
            color = 1 - cv2.compareHist(look[1], self.look[1], cv2.HISTCMP_BHATTACHARYYA)
            same_id = d['id'] == self.track_id
            # 같은 ID여도 위치와 외형을 검사합니다. 번호만으로 성공 처리하지 않습니다.
            if shape < (.15 if same_id else .20) or color < (.45 if same_id else .70):
                continue
            candidates.append((.6 * shape + .4 * color - .15 * distance, d))
        candidates.sort(key=lambda item: item[0], reverse=True)
        # 비슷한 후보가 둘이면 보류합니다. 다른 차에 상자를 붙이지 않는 쪽을 택합니다.
        if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .12):
            self.pending, self.streak = None, 0
            return None
        d = candidates[0][1]
        if d['id'] != self.track_id:
            self.streak = self.streak + 1 if self.pending == d['id'] else 1
            self.pending = d['id']
            # 새 번호는 3개 연속 프레임에서 같은 후보가 확인되어야 연결합니다.
            if self.streak < 3:
                return None
        b = np.array(d['box'])
        movement = ((b[:2] + b[2:]) / 2 - center) / max(gap, 1)
        self.velocity = .6 * self.velocity + .4 * movement
        self.box, self.track_id, self.last_frame = b, d['id'], number
        self.look = appearance(frame, b)
        self.pending, self.streak = None, 0
        return d


def main():
    parser = argparse.ArgumentParser()
    # 아래 옵션은 창 없이도 같은 영상과 첫 선택 위치로 검증하기 위한 것입니다.
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--select', nargs=2, type=int, metavar=('X', 'Y'))
    parser.add_argument('--select-frame', type=int, default=1)
    parser.add_argument('--log', type=Path)
    args = parser.parse_args()
    if args.headless and args.select is None:
        parser.error('--headless 검증에는 --select X Y가 필요합니다.')
    video = ROOT / 'videos' / '비접촉_사고유발_영상_낮.mp4'
    weights = ROOT / 'yolo26n.pt'
    if not video.is_file() or not weights.is_file():
        raise FileNotFoundError('프로젝트의 영상과 yolo26n.pt를 확인해주세요.')
    cap = cv2.VideoCapture(str(video))
    window = 'RedBox target tracking'
    target = Target()
    state = {'detections': [], 'frame': None, 'number': 0, 'selected': None}
    paused = not args.headless
    delay = 1  # 기존의 빠른 재생을 유지합니다. +/-로 대기 시간을 바꿀 수 있습니다.
    logs = []

    def click(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        hits = [d for d in state['detections'] if d['box'][0] <= x <= d['box'][2]
                and d['box'][1] <= y <= d['box'][3] and d['id'] is not None]
        if hits:
            # 상자가 겹치면 클릭 위치를 포함하는 작은 상자를 선택합니다.
            d = min(hits, key=lambda d: (d['box'][2]-d['box'][0])*(d['box'][3]-d['box'][1]))
            target.select(d, state['frame'], state['number'])
            state['selected'] = d

    try:
        if not cap.isOpened():
            raise RuntimeError('영상을 열 수 없습니다.')
        model = YOLO(str(weights))
        vehicle_ids = [i for i, name in model.names.items() if name in VEHICLES]
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        if not args.headless:
            cv2.namedWindow(window)
            cv2.setMouseCallback(window, click)
        print('차량 상자 클릭 → Space 재생/일시정지 | r 재선택 | +/- 속도 | q 종료')
        while True:
            if state['frame'] is None or not paused:
                ret, frame = cap.read()
                if not ret:
                    break
                state['number'] += 1
                # persist=True는 이전 프레임을 기억합니다. ByteTrack이 붙이는 ID는 바뀔 수 있습니다.
                result = model.track(source=frame, tracker='bytetrack.yaml', persist=True,
                                     conf=.1, classes=vehicle_ids, device='cpu', verbose=False)[0]
                ds = [{'id': int(b.id[0]) if b.id is not None else None,
                       'box': b.xyxy[0].tolist()} for b in result.boxes]
                state['frame'], state['detections'] = frame, ds
                if args.select and state['number'] == args.select_frame:
                    click(cv2.EVENT_LBUTTONDOWN, *args.select, 0, None)
                else:
                    state['selected'] = target.update(ds, frame, state['number'])
                d = state['selected']
                logs.append({'frame': state['number'], 'id': d['id'] if d else None,
                             'box': d['box'] if d else None})
            canvas = state['frame'].copy()
            # 선택 전에는 클릭할 차량들을 보여주고, 선택 후에는 확인된 타깃만 강조합니다.
            shown = state['detections'] if target.box is None else ([state['selected']] if state['selected'] else [])
            for d in shown:
                x1, y1, x2, y2 = map(int, d['box'])
                color = (0, 255, 255) if target.box is not None else (0, 0, 255)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 3)
                cv2.putText(canvas, f"ID {d['id']}", (x1, max(25, y1-10)), 0, .8, color, 2)
            status = 'CLICK A BOX' if target.box is None else ('TARGET' if state['selected'] else 'TARGET LOST - press r to reselect')
            cv2.putText(canvas, f"{status} | F{state['number']} {(state['number']-1)/fps:.2f}s", (20, 35), 0, .8, (0, 255, 255), 2)
            cv2.putText(canvas, f"Space: pause | r: reselect | +/-: speed | q: quit | delay {delay}ms", (20, 70), 0, .65, (255, 255, 255), 2)
            if args.headless:
                continue
            cv2.imshow(window, canvas)
            key = cv2.waitKey(30 if paused else delay) & 0xFF
            if key == ord('q'):
                break
            if key == ord(' '):
                paused = not paused
            elif key == ord('r'):
                target = Target()
                state['selected'] = None
                paused = True
            elif key in (ord('+'), ord('=')):
                delay = max(1, delay - 10)
            elif key == ord('-'):
                delay = min(1000, delay + 10)
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if args.log:
            args.log.write_text(json.dumps(logs), encoding='utf-8')


if __name__ == '__main__':
    main()




