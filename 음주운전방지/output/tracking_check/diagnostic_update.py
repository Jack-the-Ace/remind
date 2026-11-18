def update(self, detections, frame, number):
    if self.box is None:
        return None
    gap = number - self.last_frame
    # 1초 넘게 놓치면 자동 연결을 멈춥니다. 사용자가 다시 선택해야 합니다.
    if gap > 30:
        for d in (detections or [None]): record(self, number, d, "30프레임 초과")
        return None
    size = np.maximum(self.box[2:] - self.box[:2], 1)
    center = (self.box[:2] + self.box[2:]) / 2
    predicted = center + self.velocity * min(gap, 10)
    candidates = []
    for d in detections:
        if d['id'] is None:
            record(self, number, d, 'ID 없음')
            continue
        b = np.array(d['box'])
        ratio = (b[2:] - b[:2]) / size
        distance = np.linalg.norm(((b[:2] + b[2:]) / 2 - predicted) / size)
        if np.any(ratio < .5) or np.any(ratio > 2) or distance > min(1.4, .65 + gap * .04):
            record(self, number, d, "위치·크기 조건", ratio=ratio.tolist(), distance=float(distance), limit=min(1.4, .65+gap*.04))
            continue
        look = appearance(frame, b)
        if look is None or self.look is None:
            record(self, number, d, "외형·색상 점수", unavailable=True)
            continue
        shape = float(cv2.matchTemplate(look[0], self.look[0], cv2.TM_CCOEFF_NORMED)[0, 0])
        color = 1 - cv2.compareHist(look[1], self.look[1], cv2.HISTCMP_BHATTACHARYYA)
        same_id = d['id'] == self.track_id
        # 같은 ID여도 위치와 외형을 검사합니다. 번호만으로 성공 처리하지 않습니다.
        if shape < (.15 if same_id else .20) or color < (.45 if same_id else .70):
            record(self, number, d, "외형·색상 점수", shape=shape, color=float(color), shape_limit=.15 if same_id else .20, color_limit=.45 if same_id else .70)
            continue
        candidates.append((.6 * shape + .4 * color - .15 * distance, d))
    candidates.sort(key=lambda item: item[0], reverse=True)
    # 비슷한 후보가 둘이면 보류합니다. 다른 차에 상자를 붙이지 않는 쪽을 택합니다.
    if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .12):
        for score, d in candidates: record(self, number, d, "후보끼리 점수가 비슷함", score=score)
        self.pending, self.streak = None, 0
        return None
    d = candidates[0][1]
    if d['id'] != self.track_id:
        self.streak = self.streak + 1 if self.pending == d['id'] else 1
        self.pending = d['id']
        # 새 번호는 3개 연속 프레임에서 같은 후보가 확인되어야 연결합니다.
        if self.streak < 3:
            record(self, number, d, "새 ID가 3프레임 연속 확인되지 않음", streak=self.streak)
            return None
    record(self, number, d, '채택')
    b = np.array(d['box'])
    movement = ((b[:2] + b[2:]) / 2 - center) / max(gap, 1)
    self.velocity = .6 * self.velocity + .4 * movement
    self.box, self.track_id, self.last_frame = b, d['id'], number
    self.look = appearance(frame, b)
    self.pending, self.streak = None, 0
    return d
