# 직접 지정한 흰 정지선을 프레임마다 다시 찾습니다.
# 도로 특징점의 움직임으로 선을 옮긴 뒤, 그 자리에 도색이 보일 때만 채택합니다.
# 타깃 접지점과 선의 위치 관계를 034의 연속 확인 집계에 전달합니다.

import cv2
import numpy as np

STOP_LABEL = "정지선 통과 후보"
STOP_REVIEW = "검토 필요"
SAMPLE_WIDTH = 960
MAX_MOTION_GAP = 8


def road_motion(previous, gray, prior, vehicles):
    # 이전 선 주변 도로에서 움직이는 차량을 가리고, 왕복 추적이 맞는 점만 씁니다.
    height, width = gray.shape
    middle_y = prior[:, 1].mean()
    length = prior[1, 0] - prior[0, 0]
    margin = max(55, min(125, length * .65))
    left, right = np.clip(np.rint([prior[0, 0]-margin, prior[1, 0]+margin]).astype(int), 0, width)
    top, bottom = np.clip(np.rint([max(height*.50, middle_y-40), middle_y+85]).astype(int), 0, int(height*.93))
    if bottom-top < 20 or right-left < 36:
        return None
    allowed = np.zeros_like(gray)
    allowed[top:bottom, left:right] = 255
    for x1, y1, x2, y2 in vehicles:
        cv2.rectangle(allowed, (int(x1)-4, int(y1)-3), (int(x2)+4, int(y2)+7), 0, -1)
    points = cv2.goodFeaturesToTrack(previous, 110, .012, 6, mask=allowed, blockSize=5)
    if points is None or len(points) < 7:
        return None
    parameters = dict(winSize=(19, 19), maxLevel=2)
    current, status, _ = cv2.calcOpticalFlowPyrLK(previous, gray, points, None, **parameters)
    if current is None:
        return None
    back, backward, _ = cv2.calcOpticalFlowPyrLK(gray, previous, current, None, **parameters)
    if back is None:
        return None
    keep = status[:, 0].astype(bool) & backward[:, 0].astype(bool)
    keep &= np.linalg.norm(back[:, 0] - points[:, 0], axis=1) < 1.3
    former, latter = points[keep, 0], current[keep, 0]
    if len(former) < 7:
        return None
    transform, inliers = cv2.estimateAffinePartial2D(former, latter, method=cv2.RANSAC, ransacReprojThreshold=1.8)
    if transform is None or inliers.sum() < max(6, len(former)*.48):
        return None
    shared = former[inliers[:, 0].astype(bool)]
    projection = cv2.transform(prior[None].astype(np.float32), transform)[0]
    if np.ptp(shared[:, 0]) < 34 or np.ptp(shared[:, 1]) < 8:
        return None
    if not .81 <= np.linalg.norm(transform[0, :2]) <= 1.23 or np.max(np.linalg.norm(projection-prior, axis=1)) > 45:
        return None
    return projection


def locate_paint(small, predicted, boxes, radius, previous_support):
    # 선이 있을 좁은 띠를 가로로 여러 번 읽고, 주변보다 밝은 무채색 도색을 확인합니다.
    height, width = small.shape[:2]
    xs, ys = np.linspace(*predicted, 45, dtype=np.float32).T
    offsets = np.arange(-radius-9, radius+10, dtype=np.float32)
    grid = ys + offsets[:, None]
    xmap = np.broadcast_to(xs, grid.shape).copy()
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    stripes = cv2.remap(hsv, xmap, grid, cv2.INTER_LINEAR)
    value = stripes[:, :, 2].astype(np.float32)
    for x1, y1, x2, y2 in boxes:
        grid[(x1-2 <= xmap) & (xmap <= x2+2) & (y1-2 <= grid) & (grid <= y2+3)] = -1
    valid = (3 <= xmap) & (xmap < width-3) & (height*.46 <= grid) & (grid < height*.925)
    results = []
    for i, shift in enumerate(range(-radius, radius+1), 9):
        center = value[i]
        road = (value[i-7] + value[i+7]) / 2
        points = valid[i] & (stripes[i, :, 1] <= 90) & (center >= 91) & (center-road >= 9)
        count = int(points.sum())
        if count < 10 or np.ptp(xs[points]) < (xs[-1]-xs[0])*.34:
            continue
        score = count + min(12, float(np.median((center-road)[points]))*.15) - abs(shift)*.60
        results.append((score, shift, points))
    if not results:
        return None
    score, shift, points = max(results, key=lambda result: result[0])
    if any(other > score-2 and abs(shift-dy) >= 6 for other, dy, _ in results):
        # 차량이 움직여 도색이 더 드러났을 때는 직전과 같은 도색 조각을 우선합니다.
        # 카메라가 예측한 위치 가까이에 겹치는 조각도 없으면 두 후보 중에서 고르지 않습니다.
        anchored = [(value, dy, selected) for value, dy, selected in results
                    if previous_support is not None and abs(dy) <= 2 and value > score-2
                    and np.count_nonzero(selected & previous_support) >= previous_support.sum()*.65]
        if not anchored:
            return None
        _, shift, points = max(anchored, key=lambda result: result[0])
    line = predicted + [0, shift]
    return line, xs[points], points


class StopLine:
    def __init__(self, seed, frame_shape, camera):
        height, width = frame_shape[:2]
        self.size = (SAMPLE_WIDTH, round(height*SAMPLE_WIDTH/width))
        self.scale = np.array([self.size[0]/width, self.size[1]/height])
        points = np.asarray(seed).reshape(2, 2)*self.scale
        self.line = points[np.argsort(points[:, 0])]
        width = self.line[1, 0] - self.line[0, 0]
        if width < 25 or abs(self.line[1, 1] - self.line[0, 1]) > width*.50:
            raise ValueError("같은 정지선의 가로 방향 양쪽 끝에 두 점을 지정하세요.")
        self.origin_side = "far" if camera == "rear" else "near"
        self.gray = None
        self.boxes = []
        self.motion_gap = 0
        self.paint_gap = 0
        self.expired = False
        self.last_support = None

    def detect(self, frame, vehicles):
        if self.expired:
            return None, None, "stop_line_lost"
        small = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        boxes = [np.asarray(d["box"])*np.tile(self.scale, 2) for d in vehicles]
        if self.gray is None:
            prediction = self.line
        else:
            prediction = road_motion(self.gray, gray, self.line, self.boxes)
            if prediction is None:
                self.last_support = None
                self.motion_gap += 1
                self.expired = self.motion_gap > MAX_MOTION_GAP
                return None, None, "stop_motion_hold"
        self.gray, self.boxes = gray, boxes
        self.motion_gap = 0
        self.line = prediction
        paint = locate_paint(small, prediction, boxes, 8, self.last_support)
        if paint is None:
            self.last_support = None
            self.paint_gap += 1
            self.expired = self.paint_gap > MAX_MOTION_GAP
            return None, None, "stop_paint_hold"
        self.paint_gap = 0
        self.line, support, self.last_support = paint
        return (self.line/self.scale).tolist(), support, "stop_observed"

    def classify(self, vehicle, support):
        if vehicle is None:
            return None, None, "tracking_hold"
        x1, y1, x2, y2 = np.asarray(vehicle["box"])*np.tile(self.scale, 2)
        x = (x1+x2)/2
        (left, top), (right, bottom) = self.line
        width = right-left
        if (x2-x1 < 22 or y2 >= self.size[1]*.95 or not left <= x <= right
                or np.min(np.abs(support-x)) > width*.38):
            return None, None, "stop_contact_hold"
        # 화면에 보이는 타깃 박스 하단 중앙이 도로와 만나는 위치의 근삿값입니다.
        distance = y2 - (top + (x-left)*(bottom-top)/width)
        if abs(distance) < max(4.0, min(8, (y2-y1)*.035)):
            return None, float(distance), "stop_near_line"
        return ("near" if distance > 0 else "far"), float(distance), "stop_observed"


class StopLineMonitor:
    def __init__(self, seed, frame_shape, camera, crossing):
        self.detector = StopLine(seed, frame_shape, camera)
        self.crossing = crossing
        self.counted = False

    def update(self, number, frame, vehicles, target):
        line, support, status = self.detector.detect(frame, vehicles)
        side = distance = None
        if target is None:
            status = "tracking_hold"
        elif line is not None:
            side, distance, status = self.detector.classify(target, support)
        # 가려진 선이나 부정확한 접지점은 공백입니다. 선 근접은 관찰 중인 구간입니다.
        missing = status not in {"stop_observed", "stop_near_line"}
        event = self.crossing.update(number, side, missing)
        if self.crossing.recovery_hold:
            status = "stop_gap_hold"
        # 직접 지정한 도색 한 줄에 대해 주행 방향의 통과를 한 번만 기록합니다.
        if self.counted or event is None or event["from_side"] != self.detector.origin_side:
            event = None
        if event is not None:
            self.counted = True
        return dict(line=line, status=status, side=side, distance_px=distance), event
