# 006  차량 한 대를 골라 계속 따라가기
# 옆 차로 넘어가지 않게 위치·크기·외형을 함께 확인합니다.
# 기본은 주간 영상과 yolo26n.pt입니다. 상자를 클릭하고 Space로 재생합니다.
# 추적 보류와 확정 상자를 --selected-track에 기록해 034의 집계에 씁니다.

# 수업 흐름: VideoCapture → 프레임 읽기 → model.track → OpenCV 표시
from pathlib import Path
import argparse
from collections import deque
import hashlib
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
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


def appearance_scores(look, reference):
    gray, histogram = reference
    shape = float(cv2.matchTemplate(look[0], gray, cv2.TM_CCOEFF_NORMED)[0, 0])
    color = 1 - cv2.compareHist(look[1], histogram, cv2.HISTCMP_BHATTACHARYYA)
    return shape, color


def box_overlap(first, second):
    common = np.maximum(0, np.minimum(first[2:], second[2:]) - np.maximum(first[:2], second[:2])).prod()
    union = np.prod(first[2:] - first[:2]) + np.prod(second[2:] - second[:2]) - common
    return common / max(union, 1)


class Target:
    def __init__(self, diagnostic=None):
        self.box = None
        self.track_id = None
        self.last_frame = 0
        self.look = None
        self.recent_looks = deque(maxlen=12)
        self.velocity = np.zeros(2)
        self.diagnostic = diagnostic
        self.clear_pending()

    def clear_pending(self):
        self.pending = None
        self.streak = 0
        self.used_transition = False
        self.used_extension = False

    def report(self, number, detection, reason, **scores):
        if self.diagnostic is not None:
            self.diagnostic(dict(frame=number, last_accepted=self.last_frame, gap=number-self.last_frame,
                                 candidate_id=detection['id'] if detection else None,
                                 reason=reason, **scores))

    def select(self, detection, frame, number):
        self.box = np.array(detection['box'], dtype=float)
        self.track_id = detection['id']
        self.look = appearance(frame, self.box)
        self.recent_looks.clear()
        if self.look is not None:
            self.recent_looks.append(self.look)
        self.last_frame = number
        self.velocity = np.zeros(2)
        self.clear_pending()

    def update(self, detections, frame, number):
        if self.box is None:
            return None
        gap = number - self.last_frame
        # 1초 넘게 놓치면 자동 연결을 멈춥니다. 사용자가 다시 선택해야 합니다.
        if gap > 30:
            self.report(number, None, 'reconnect_timeout')
            return None
        size = np.maximum(self.box[2:] - self.box[:2], 1)
        center = (self.box[:2] + self.box[2:]) / 2
        predicted = center + self.velocity * min(gap, 10)
        limit = min(1.4, .65 + gap * .04)
        candidates = []
        if not detections:
            self.report(number, None, 'no_tracked_box')
        for d in detections:
            if d['id'] is None:
                self.report(number, d, 'no_track_id')
                continue
            b = np.array(d['box'])
            ratio = (b[2:] - b[:2]) / size
            distance = np.linalg.norm(((b[:2] + b[2:]) / 2 - predicted) / size)
            same_id = d['id'] == self.track_id
            # 새 후보의 첫 상자는 기존 조건을 그대로 통과해야 합니다.
            # 다음 프레임에 같은 후보 상자가 충분히 겹칠 때만 짧은 이동을 이어 봅니다.
            same_pending = (
                not same_id and self.pending is not None and self.pending[0] == number - 1
                and self.pending[1]['id'] == d['id']
            )
            continuous = (same_pending and self.pending[1]['class'] == d['class']
                          and box_overlap(np.asarray(self.pending[1]['box']), b) >= .50)
            extended = distance > limit
            # 원래 위치·외형 조건만 쓰는 후보는 기존 방식으로 연속 확인합니다.
            # 한 번이라도 확장 조건을 쓰면 이후에도 상자가 겹쳐야 같은 흐름으로 봅니다.
            continues_streak = continuous or (same_pending and not self.used_extension and not extended)
            if np.any(ratio < .5) or np.any(ratio > 2) or distance > limit + (.45 if continuous else 0):
                self.report(number, d, 'position_or_size', ratio=ratio.tolist(),
                            distance=float(distance), limit=limit + (.45 if continuous else 0))
                continue
            look = appearance(frame, b)
            if look is None or self.look is None:
                self.report(number, d, 'appearance_unavailable')
                continue
            # 같은 ID여도 위치와 외형을 검사합니다. 번호만으로 성공 처리하지 않습니다.
            # 번호를 잃기 직전에는 가린 차량이 섞일 수 있어 최근에 확인한 모습도 비교합니다.
            references = self.recent_looks if not same_id and gap > 1 else (self.look,)
            comparisons = [appearance_scores(look, reference) for reference in references]
            scores = []
            for shape, color in comparisons:
                if shape >= (.15 if same_id else .20) and color >= (.45 if same_id else .70):
                    scores.append(.6 * shape + .4 * color - .15 * distance)
            if scores:
                candidates.append((max(scores), d, look, continues_streak, True, extended))
            elif continuous and not self.used_transition:
                # 겹치는 임시 상자의 외형이 거의 같으면 한 프레임만 연결을 보류합니다.
                # 이 프레임은 외형 확인 3회에 포함하지 않고 화면·집계에도 넘기지 않습니다.
                shape, color = appearance_scores(look, self.pending[2])
                if shape >= .35 and color >= .85:
                    candidates.append((.6 * shape + .4 * color - .15 * distance, d, look, True, False, True))
                    continue
                self.report(number, d, 'appearance', comparisons=comparisons,
                            pending_shape=shape, pending_color=color)
            else:
                self.report(number, d, 'appearance', comparisons=comparisons)
        candidates.sort(key=lambda item: item[0], reverse=True)
        # 비슷한 후보가 둘이면 보류합니다. 다른 차에 상자를 붙이지 않는 쪽을 택합니다.
        if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .12):
            for score, d, *_ in candidates:
                self.report(number, d, 'ambiguous_candidates', score=float(score))
            self.clear_pending()
            return None
        _, d, look, continues_streak, confirmed_look, extended = candidates[0]
        if d['id'] != self.track_id:
            if not continues_streak:
                self.clear_pending()
            self.pending = number, d, look
            self.streak += int(confirmed_look)
            self.used_transition |= not confirmed_look
            self.used_extension |= extended
            # 끊김 없는 짧은 경로에서 기존 차량의 외형이 3회 확인되어야 새 ID를 채택합니다.
            if self.streak < 3:
                self.report(number, d, 'awaiting_id_confirmation' if confirmed_look else 'appearance_transition',
                            confirmations=self.streak)
                return None
        self.report(number, d, 'accepted')
        b = np.array(d['box'])
        movement = ((b[:2] + b[2:]) / 2 - center) / max(gap, 1)
        self.velocity = .6 * self.velocity + .4 * movement
        self.box, self.track_id, self.last_frame = b, d['id'], number
        self.look = look
        self.recent_looks.append(self.look)
        self.clear_pending()
        return d


def video_digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    # 아래 옵션은 창 없이도 같은 영상과 첫 선택 위치로 검증하기 위한 것입니다.
    parser.add_argument('--video', type=Path, default=ROOT / 'videos/비접촉_사고유발_영상_낮.mp4')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--select', nargs=2, type=int, metavar=('X', 'Y'))
    parser.add_argument('--select-frame', type=int, default=1)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--selected-track', type=Path, help='034가 읽을 수동 선택·추적 기록 (새 JSON 파일)')
    args = parser.parse_args()
    if args.headless and args.select is None:
        parser.error('--headless 검증에는 --select X Y가 필요합니다.')
    video = args.video
    weights = ROOT / 'yolo26n.pt'
    if not video.is_file() or not weights.is_file():
        raise FileNotFoundError('프로젝트의 영상과 yolo26n.pt를 확인해주세요.')
    if args.selected_track and (args.selected_track.exists()
                                or (args.log and args.selected_track.resolve() == args.log.resolve())):
        parser.error('--selected-track에는 다른 새 파일 경로가 필요합니다.')
    cap = cv2.VideoCapture(str(video))
    window = 'RedBox target tracking'
    target = Target()
    state = {'detections': [], 'frame': None, 'number': 0, 'selected': None}
    paused = not args.headless
    delay = 1  # 기존의 빠른 재생을 유지합니다. +/-로 대기 시간을 바꿀 수 있습니다.
    logs = []
    selection = 0
    selected_rows = []

    def record():
        number, d = state['number'], state['selected']
        row = {'frame': number, 'id': d['id'] if d else None, 'box': d['box'] if d else None}
        logs[number - 1:] = [row]
        if args.selected_track:
            # 클릭은 일시정지한 프레임에도 적용합니다. 다시 고르면 이전 차량과 별개로 기록합니다.
            status = 'confirmed' if d else ('tracking_hold' if target.box is not None else 'unselected')
            selected_rows[number - 1:] = [
                dict(row, selection=selection, status=status, vehicles=state['detections'])
            ]

    def click(event, x, y, flags, param):
        nonlocal selection
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        hits = [d for d in state['detections'] if d['box'][0] <= x <= d['box'][2]
                and d['box'][1] <= y <= d['box'][3] and d['id'] is not None]
        if hits:
            # 상자가 겹치면 클릭 위치를 포함하는 작은 상자를 선택합니다.
            d = min(hits, key=lambda d: (d['box'][2]-d['box'][0])*(d['box'][3]-d['box'][1]))
            target.select(d, state['frame'], state['number'])
            state['selected'] = d
            selection += 1
            record()

    try:
        if not cap.isOpened():
            raise RuntimeError('영상을 열 수 없습니다.')
        model = YOLO(str(weights))
        vehicle_ids = [i for i, name in model.names.items() if name in VEHICLES]
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        if not args.headless:
            hold_font = ImageFont.truetype(str(Path('C:/Windows/Fonts/malgunbd.ttf')), 24)
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
                       'box': b.xyxy[0].tolist(), 'class': result.names[int(b.cls[0])]} for b in result.boxes]
                state['frame'], state['detections'] = frame, ds
                if args.select and state['number'] == args.select_frame:
                    click(cv2.EVENT_LBUTTONDOWN, *args.select, 0, None)
                else:
                    state['selected'] = target.update(ds, frame, state['number'])
                record()
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
            if target.box is not None and state['selected'] is None:
                panel = Image.new('RGB', (canvas.shape[1], 32))
                ImageDraw.Draw(panel).text(
                    (20, 1), f"추적 보류  |  F{state['number']}  |  r: 재선택", font=hold_font,
                    fill=(255, 235, 110)
                )
                canvas[8:40] = cv2.cvtColor(np.asarray(panel), cv2.COLOR_RGB2BGR)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(30 if paused else delay) & 0xFF
            if key == ord('q'):
                break
            if key == ord(' '):
                paused = not paused
            elif key == ord('r'):
                target = Target()
                state['selected'] = None
                record()
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
    if args.selected_track:
        # 영상 내용과 프레임 번호가 일치할 때만 034에서 이 기록을 사용합니다.
        with args.selected_track.open('x', encoding='utf-8') as stream:
            json.dump({'video_sha256': video_digest(video), 'fps': fps, 'frames': selected_rows}, stream)


if __name__ == '__main__':
    main()




