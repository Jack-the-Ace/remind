# 034  차량의 차선 경계 통과 후보 기록하기
# 한 경계의 반대쪽에 6프레임 머물 때만 세어 짧은 깜빡임을 걸러냅니다.
# 006의 --selected-track 기록, 같은 영상, 640 모델, --seed-line과 새 --output이 필요합니다.
# 후보 시각을 candidates.json에 쓰고 전후 원본 클립을 잘라 사건 화면에 넘깁니다.

"""선택한 차량과 차선 경계를 따라 차선 경계 통과 후보를 기록합니다."""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageFont

from preview_lane_track_197 import (
    DEFAULT_VIDEO, ROOT, draw_overlay, load_lane_model, predict_lane, read_track_replay, verify_video,
)
from track_preview import video_digest


SIZE = (640, 400)
DEFAULT_MODEL = ROOT / "output/lane_transfer_197_highres/imagenet_v1_640x400_recalibrated.pt"
DEFAULT_TRACK = ROOT / "output/lane_video_197_retrained_compare/640x400/frames.jsonl"
SIDE_MARGIN = 9
HOLD_SECONDS = 0.20
MAX_UNCERTAIN_SECONDS = 1.35
EVENT_LABEL = "차선 경계 통과 후보"


class Boundary:
    def __init__(self, seed):
        x1, y1, x2, y2 = seed
        self.line = np.polyfit([y1, y2], [x1, x2], 1)
        self.direction = np.sign(self.line[0])

    def detect(self, mask, boxes, *, row_limits=(143, SIZE[1] - 2), min_points=12, min_span=53, corridor=None):
        # 이전에 선택한 선 주변만 살펴 다른 차선으로 바뀌는 것을 막습니다.
        points = []
        for y in range(*row_limits, 4):
            center = np.polyval(self.line, y)
            span = corridor if corridor is not None else 18 + (y - 143) * .044
            left, right = max(0, round(center - span)), min(SIZE[0], round(center + span) + 1)
            if right <= left:
                continue
            xs = np.flatnonzero(mask[y, left:right]) + left
            for x1, y1, x2, y2 in boxes:
                if y1 - 1 <= y <= y2 + 1:
                    xs = xs[(xs < x1 - 1) | (xs > x2 + 1)]
            parts = np.split(xs, np.flatnonzero(np.diff(xs) > 1) + 1)
            candidates = [float(np.mean(p)) for p in parts if 2 <= len(p) <= 24]
            if candidates:
                points.append((y, min(candidates, key=lambda x: abs(x - center))))
        if len(points) < min_points:
            return None
        y, x = np.array(points).T
        fit = np.polyfit(y, x, 1)
        keep = np.abs(x - np.polyval(fit, y)) <= 9
        if keep.sum() < min_points or np.ptp(y[keep]) < min_span:
            return None
        fit = np.polyfit(y[keep], x[keep], 1)
        check_rows = [180, 280, 370]
        if not .50 <= self.direction * fit[0] <= 2.45 or np.max(np.abs(np.polyval(fit - self.line, check_rows))) > 21:
            return None
        # 이동 평균은 선을 안정화하고, 유효 지점은 이번 프레임의 마스크에서만 가져옵니다.
        self.line = .62 * self.line + .38 * fit
        return y[keep]

    def endpoints(self, rows, scale):
        if rows is None:
            return None
        return [[float(np.polyval(self.line, y)/scale[0]), float(y/scale[1])]
                for y in (rows.min(), rows.max())]

    def classify(self, point, rows, boxes, *, paint_support=False):
        px, py = point
        x_on_lane = float(np.polyval(self.line, py))
        distance = (px - x_on_lane) / math.sqrt(1 + self.line[0] ** 2)
        # 가까운 지지점이 없는 긴 외삽과 차량에 가린 지점의 판정을 보류합니다.
        near = np.min(np.abs(rows - py))
        if near > 38 or py > rows.max() + 26 or py < rows.min() - 30:
            return None, distance, "boundary_not_supported"
        # 박스가 선을 덮는 모양이면 바퀴 바로 아래에 보이는 선 근거가 필요합니다.
        # 선택한 노란 도색을 좁게 확인한 경우에만 허용 거리를 12에서 18픽셀로 늘립니다.
        support_depth = 18 if paint_support else 12
        probe_y = py + 4
        probe_x = np.polyval(self.line, probe_y)
        covered = any(y1 <= probe_y <= y2 and x1 <= probe_x <= x2 for x1, y1, x2, y2 in boxes)
        overlaps_vehicle = any(y1 <= py - 3 <= y2 and x1 <= np.polyval(self.line, py - 3) <= x2
                               for x1, y1, x2, y2 in boxes)
        if covered or (overlaps_vehicle and not np.any((py + 1 <= rows) & (rows <= py + support_depth))):
            return None, distance, "boundary_occluded"
        if abs(distance) < SIDE_MARGIN:
            return None, distance, "near_boundary"
        return ("right" if distance > 0 else "left"), distance, "observed"


class Crossing:
    def __init__(self, fps):
        self.required = math.ceil(HOLD_SECONDS * fps)
        self.gap_limit = math.ceil(MAX_UNCERTAIN_SECONDS * fps)
        self.stable = None
        self.stable_frame = None
        self.pending = None
        self.pending_frame = None
        self.side_before_loss = None
        self.recovery_hold = False

    def update(self, frame, side, lost_id):
        self.recovery_hold = False
        if lost_id and self.stable is not None:
            # 끊기기 전 위치는 보류 이유를 남길 때만 씁니다.
            self.side_before_loss = self.stable
        if lost_id or (self.stable is not None and frame - self.stable_frame > self.gap_limit):
            self.stable = self.stable_frame = None
            self.pending = self.pending_frame = None
        if side is None:
            self.pending = self.pending_frame = None
            return None
        self.recovery_hold = self.side_before_loss is not None and side != self.side_before_loss
        if side == self.stable:
            self.stable_frame = frame
            self.pending = self.pending_frame = None
            return None
        if side != self.pending:
            self.pending, self.pending_frame = side, frame
        if frame - self.pending_frame + 1 < self.required:
            return None
        previous, previous_frame = self.stable, self.stable_frame
        self.stable, self.stable_frame = side, frame
        # 복귀 후 처음 확인한 쪽은 다음 통과를 판단할 새 기준 위치입니다.
        self.side_before_loss = None
        event = dict(from_side=previous, to_side=side, last_origin_frame=previous_frame,
                     first_confirmable_opposite_frame=self.pending_frame) if previous is not None else None
        self.pending = self.pending_frame = None
        return event


LANE_RULE_VERSION = "contact-1.5s-v1"


def footprint(box, endpoints, status, was_contact=False, paint_half_width=0.0):
    """현재 프레임에서 확인한 선과 차량 하단 양끝을 같은 원본 좌표로 비교합니다."""
    if box is None or endpoints is None or status not in {"observed", "near_boundary"}:
        return None
    (x1, y1), (x2, y2) = endpoints
    if abs(y2-y1) < 1e-6:
        return None
    left, _, right, bottom = box
    lane_x = x1 + (bottom-y1)*(x2-x1)/(y2-y1)
    # 도색의 가장자리까지 포함합니다. 접촉 중에는 작은 박스 떨림만큼 여유를 두고 복귀합니다.
    margin = paint_half_width + (min(2., (right-left)*.025) if was_contact else 0.)
    if right < lane_x-margin:
        return "left"
    if left > lane_x+margin:
        return "right"
    return "contact"


def source_seconds(cap, frame, fps):
    """디코딩 직후의 원본 PTS를 읽습니다. 시각을 주지 않는 컨테이너만 FPS로 환산합니다."""
    value = cap.get(cv2.CAP_PROP_POS_MSEC)
    if math.isfinite(value) and (value > 0 or (value == 0 and frame == 1)):
        return value/1000.
    return (frame-1)/fps


class LaneBehavior:
    """지정 차량 하나와 경계 하나의 관측을 원본 시각 순으로 받습니다."""

    def __init__(self, fps):
        self.fps = fps
        self.previous_frame = self.previous_time = None
        self.reset()

    def reset(self):
        self.origin = self.last_position = None
        self.start = self.start_frame = None
        self.ticks = 0
        self.opposite = self.opposite_frame = None
        self.maneuver_frame = None
        self.already_counted = False

    def observe(self, frame, seconds, box, endpoints, status, paint_half_width=0.):
        position = footprint(box, endpoints, status, self.last_position == "contact", paint_half_width)
        return self.update(frame, seconds, position)

    def update(self, frame, seconds, position):
        events = []
        if self.previous_frame is not None and (
                frame != self.previous_frame+1 or seconds <= self.previous_time
                or seconds-self.previous_time > max(.25, 1.75/self.fps)):
            self.reset()
        self.previous_frame, self.previous_time = frame, seconds
        if position is None:
            self.reset()
            return events
        if position not in {"left", "right", "contact"}:
            raise ValueError(position)
        self.last_position = position

        def record(label, reason, when, to_side):
            events.append(dict(label=label, reason=reason, time_s=min(seconds, when),
                               from_side=self.origin or "unknown", to_side=to_side,
                               maneuver_start_frame=self.maneuver_frame, contact_start_s=self.start,
                               opposite_start_frame=self.opposite_frame, confirmed_frame=frame,
                               frame=frame, rule_version=LANE_RULE_VERSION))

        if self.start is not None:
            # 복귀 프레임도 먼저 시간을 정산합니다. 정확히 3초면 두 번이고 복귀 보너스는 없습니다.
            while seconds + 1e-8 >= self.start + (self.ticks+1)*1.5:
                self.ticks += 1
                record("차선침범", "contact_interval", self.start+self.ticks*1.5, "boundary")
                self.already_counted = True
        if position == "contact":
            if self.start is None:
                self.start, self.start_frame, self.ticks = seconds, frame, 0
                if self.maneuver_frame is None:
                    self.maneuver_frame = frame
            self.opposite = self.opposite_frame = None
            return events

        if position == self.origin and self.maneuver_frame is not None and not self.already_counted:
            record("차선침범", "returned_to_origin", seconds, position)
        self.start = self.start_frame = None
        self.ticks = 0
        if self.origin is None or position == self.origin:
            self.origin = position
            self.opposite = self.opposite_frame = self.maneuver_frame = None
            self.already_counted = False
        else:
            if self.opposite is None:
                self.opposite, self.opposite_frame = seconds, frame
                if self.maneuver_frame is None:
                    self.maneuver_frame = frame
            if seconds-self.opposite + 1e-8 >= 1.:
                record("차선변경", "held_new_lane", seconds, position)
                self.origin = position
                self.opposite = self.opposite_frame = self.maneuver_frame = None
                self.already_counted = False
        return events


# 원본 해상도에서 적용하는 보수적인 시연 기준입니다. 확대된 검출 입력의 크기는 쓰지 않습니다.
READABILITY_RULES = dict(min_width=22, min_height=15, detail_width=32, detail_height=21,
                         min_laplacian=12, min_contrast=14, foreground_overlap=.35, identity_cover=.75,
                         clear_edge_margin=3, nearby_paint_contrast=10, nearby_paint_rows=3,
                         settle_seconds=HOLD_SECONDS)


def lane_evidence(image, box, endpoints, status, support_gap, vehicles):
    """추적된 차체, 앞을 가린 차, 원본 도색이 서로 구별되는지를 측정합니다."""
    metrics = {"support_gap_px":support_gap}
    if box is None:
        return "search", metrics
    left,top,right,bottom = box
    w,h = right-left,bottom-top
    metrics.update(width_px=w,height_px=h)
    height,width = image.shape[:2]
    x,X = np.clip([int(left),int(np.ceil(right))],0,width)
    y,Y = np.clip([int(top),int(np.ceil(bottom))],0,height)
    if X-x < 2 or Y-y < 2:
        return "small", metrics
    patch = cv2.cvtColor(image[y:Y,x:X],cv2.COLOR_BGR2GRAY)
    # 가까운 차는 넓고 매끈한 차체가 분산을 낮춥니다. 큰 패치만 같은 관찰 크기로 줄여
    # 윤곽의 선명도를 비교합니다. 작은 차를 키워 새 정보가 생긴 것으로 취급하지 않습니다.
    shrink=min(1.,64/patch.shape[1],48/patch.shape[0])
    detail=cv2.resize(patch,(max(2,round(patch.shape[1]*shrink)),max(2,round(patch.shape[0]*shrink))),
                      interpolation=cv2.INTER_AREA) if shrink<1 else patch
    lap = float(cv2.Laplacian(detail,cv2.CV_32F).var())
    contrast = float(np.ptp(np.percentile(patch,[10,90])))
    # 하단 띠를 더 가까운 차량이 덮는지 봅니다. 같은 타깃 박스는 깊이 조건에서 제외됩니다.
    cover = body_cover = 0.
    for car in vehicles:
        a,b,A,B = car["box"]
        if B <= bottom+max(4,h*.35):
            continue
        area = max(0,min(right,A)-max(left,a))*max(0,min(bottom,B)-max(bottom-h*.35,b))
        cover = max(cover,area/max(1,w*h*.35))
        full_area=max(0,min(right,A)-max(left,a))*max(0,min(bottom,B)-max(top,b))
        body_cover=max(body_cover,full_area/max(1,w*h))
    metrics.update(laplacian=lap,contrast=contrast,foreground_cover=cover,body_cover=body_cover)
    rule = READABILITY_RULES
    if min(cover,body_cover)>=rule["identity_cover"]:
        return "search", metrics
    if cover >= rule["foreground_overlap"]:
        return "unclear", metrics
    if w < rule["min_width"] or h < rule["min_height"]:
        return "small", metrics
    if lap < rule["min_laplacian"] or contrast < rule["min_contrast"]:
        return "unclear", metrics
    if endpoints is None or status not in {"observed","near_boundary"}:
        return "unclear", metrics
    if w >= rule["detail_width"] and h >= rule["detail_height"]:
        return "ready", metrics

    # 작은 차는 마스크만으로 선을 밟았는지 단정하기 어렵습니다. 차와 선 사이가
    # 분명히 벌어졌고, 가까운 도색이 원본에도 있는 경우에만 한쪽에 있음을 인정합니다.
    (a,b),(A,B) = endpoints
    if abs(B-b)<1e-6:
        return "unclear", metrics
    slope=(A-a)/(B-b)
    line_x=a+(bottom-b)*slope
    clearance=max(left-line_x,line_x-right)
    metrics["clearance_px"]=clearance
    if clearance <= rule["clear_edge_margin"]:
        return "small", metrics
    if support_gap is None or support_gap > max(5,h*.55):
        return "unclear", metrics
    votes=0
    for yy in range(Y+1,min(height,Y+1+min(16,max(5,round(.7*h))))):
        xx=round(a+(yy-b)*slope)
        if xx<10 or xx+10>=width:
            continue
        strip=cv2.cvtColor(image[yy:yy+1,xx-10:xx+11],cv2.COLOR_BGR2GRAY)[0]
        flank=max(float(np.median(strip[:4])),float(np.median(strip[-4:])))
        if float(np.max(strip[8:13]))-flank >= rule["nearby_paint_contrast"]:
            votes+=1
    metrics["paint_rows"]=votes
    return ("ready" if votes>=rule["nearby_paint_rows"] else "unclear"), metrics


class LaneReadability:
    """관측이 끊긴 순간에는 집계를 멈추고, 같은 경계 근거가 안정되면 다시 시작합니다."""

    def __init__(self, fps):
        self.behavior=LaneBehavior(fps)
        self.active=False
        self.pending=[]
        self.notice=None
        self.reason=None
        self.since=0.
        self.not_ready_since=None
        self.located_since=None

    def update(self, frame, seconds, box, boundary, status, raw, paint_half_width=0.):
        last=self.behavior
        if last.previous_frame is not None and (frame != last.previous_frame+1 or seconds <= last.previous_time
                or seconds-last.previous_time>max(.25,1.75/last.fps)) and not self.pending:
            self.active=False
        recent=self.pending[-1] if self.pending else None
        if recent and (frame!=recent[0]+1 or not 0<seconds-recent[1]<=max(.25,1.75/last.fps)):
            self.pending.clear()
        position=footprint(box,boundary,status,last.last_position=="contact",paint_half_width)
        events=[]
        if raw!="ready" or position is None:
            if raw=="ready":
                raw="unclear"
            self.pending.clear()
            self.active=False
            last.update(frame,seconds,None)
        elif self.active:
            events=last.update(frame,seconds,position)
        else:
            if self.pending and self.pending[-1][2]!=position:
                self.pending.clear()
            self.pending.append((frame,seconds,position))
            if seconds-self.pending[0][1]+1e-8>=HOLD_SECONDS:
                # 안정된 구간의 첫 관측 시각부터 셉니다. 공백 앞의 시간은 이어 붙이지 않습니다.
                self.active=True
                for item in self.pending:
                    events.extend(last.update(*item))
                self.pending.clear()
        if raw=="search":
            self.located_since=None
        elif self.located_since is None:
            self.located_since=seconds
        if raw!=self.reason:
            self.reason,self.since=raw,seconds
        if self.active:
            self.notice="ready"
            self.not_ready_since=None
        else:
            if self.not_ready_since is None:
                self.not_ready_since=seconds
            if self.notice is None:
                self.notice=raw if raw!="ready" else "checking"
            elif raw=="search":
                if seconds-self.since+1e-8>=HOLD_SECONDS:
                    self.notice="search"
            elif self.notice=="search":
                # 차량 확인과 차선 확인은 다른 조건입니다. 차를 다시 찾으면 위치 안내부터 해제합니다.
                if seconds-self.located_since+1e-8>=HOLD_SECONDS:
                    self.notice=raw if raw!="ready" else "checking"
            elif raw!="ready":
                duration=seconds-(self.not_ready_since if self.notice=="ready" else self.since)
                if duration+1e-8>=HOLD_SECONDS:
                    self.notice=raw
        return events,dict(raw=raw,notice=self.notice,counting=self.active)



class MeasuredBoundary:
    """작은 차의 각 경계를 별도로 기록하고, 미확인 프레임은 접촉 시간에서 뺍니다."""
    def __init__(self, fps):
        self.state=LaneBehavior(fps)
        self.restart()

    def restart(self):
        self.state.reset()
        self.state.previous_frame=self.state.previous_time=None
        self.last_valid=None
        self.index=0
        self.offset=0.
        self.pending=[]
        self.first_contact=None
        self.band_since=None
        self.approach_at=None
        self.band_used=False
        self.return_side=None
        self.last_frame=None
        self.maneuver_frame=self.opposite_frame=None

    def update(self, frame, seconds, position, visible, edge_band=False, strong_contact=False):
        interrupted=(self.last_frame is not None and frame!=self.last_frame+1)
        if not visible or interrupted:
            self.restart()
        self.last_frame=frame
        if not visible:
            return []
        # 경계와 차체를 모두 관측했지만 오차 띠 안이면 접근의 순서만 기억합니다.
        # 이 시간은 1.5초 타이머에 넣지 않고, 선 자체가 사라진 때와도 구분합니다.
        near_return=(position==self.state.origin and position is not None and
                     self.band_used and self.state.last_position=='contact')
        if near_return and self.return_side!=(frame-1,position):
            self.return_side=(frame,position)
            position=None
            edge_band=True
        elif not near_return:
            self.return_side=None
        if position is None and edge_band and self.last_valid:
            if self.approach_at is None:
                self.approach_at=seconds
            if self.band_since is None:
                self.band_since=seconds
            self.band_used=True
            self.pending.clear()
            if seconds-self.band_since>=1.5:
                self.restart()
            return []
        continuous_band=self.band_since is not None and (position is not None)
        self.band_since=None
        if self.last_valid and not continuous_band and (frame-self.last_valid[0]>3 or
                seconds-self.last_valid[1]>min(.25,3.5/self.state.fps)):
            self.restart()
        if position is None:
            self.pending.clear()
            return []
        if position=='contact' and self.approach_at is None:
            self.approach_at=seconds
        if self.last_valid:
            n,t=self.last_valid
            if frame!=n+1:
                self.offset+=seconds-t
                if not continuous_band and self.state.last_position!=position and position!=self.state.origin:
                    self.restart()
        self.last_valid=(frame,seconds)
        self.index+=1
        when=seconds-self.offset
        item=(self.index,when,position)
        if position=='contact' and self.state.last_position!='contact':
            self.pending.append((item,seconds))
            if len(self.pending)<3 and not strong_contact:
                return []
            batch=[i for i,_ in self.pending]
            self.first_contact=self.pending[0][1]
        else:
            batch=[item]
            if self.pending:
                # 미확인 접촉 두 장 이하로는 원래 차로를 바꾸거나 사건을 만들지 않습니다.
                if self.state.previous_time is not None:
                    self.state.previous_frame=item[0]-1
        self.pending=[]
        events=[]
        for i,at,pos in batch:
            # 공백 시간을 뺀 두 관측이 같은 시각이면 최소 부동소수점 차만 둡니다.
            if self.state.previous_time is not None:
                at=max(at,self.state.previous_time+1e-10)
                self.state.previous_frame=i-1
            found=self.state.update(i,at,pos)
            for e in found:
                e.update(frame=frame,confirmed_frame=frame,time_s=min(seconds,e['time_s']+self.offset),
                         contact_start_s=self.first_contact)
                # 내부 가상 프레임 번호는 제출 로그에 남기지 않습니다.
                e['maneuver_start_frame']=self.maneuver_frame
                if e.get('opposite_start_frame') is not None:
                    e['opposite_start_frame']=self.opposite_frame
            if self.band_used and self.approach_at is not None and seconds-self.approach_at>=1.5:
                # 불확실한 접근이 길면 짧은 침범이었다고 단정할 수 없습니다.
                found=[e for e in found if e['reason']!='returned_to_origin']
            events.extend(found)
            if pos=='contact' and self.state.start_frame==i and self.state.maneuver_frame==i:
                self.maneuver_frame=frame-len(batch)+1
            if self.state.opposite_frame==i:
                self.opposite_frame=frame
                if self.state.maneuver_frame==i:
                    self.maneuver_frame=frame
        if position!='contact':
            self.first_contact=self.approach_at=None
            self.band_used=False
        return events


class SceneLaneAnalysis:
    """웹과 제출본이 공유하는 관측 단계입니다. 문자·등화 판독 여부는 입력받지 않습니다."""
    def __init__(self, fps, seed):
        from redbox_lane_geometry import RoadGeometry
        self.geometry=RoadGeometry(seed)
        self.legacy=LaneReadability(fps)
        self.clocks={side:MeasuredBoundary(fps) for side in ('left','right')}
        self.mode=None
        self.notice=None
        self.bad_since=None
        self.observations=[]
        self.last_reading=None

    def evaluate(self, f, seconds, image, box, endpoints, status, gap, vehicles, model_mask, clock=None):
        raw,metrics=lane_evidence(image,box,endpoints,status,gap,vehicles)
        # 크기는 분석을 그만두는 문턱이 아니라 주변 도로를 다시 읽을지 결정하는 기준입니다.
        remote=box is not None and (box[2]-box[0]<40 or box[3]-box[1]<26)
        if self.mode=="remote" and box is not None:
            # 경계 근처에서 박스 크기가 한두 화소 흔들려도 같은 판독·타이머를 유지합니다.
            busy=any(c.state.start is not None or c.pending or c.band_since is not None for c in self.clocks.values())
            remote=remote or busy or box[2]-box[0]<48 or box[3]-box[1]<32
        if not remote and (box is not None or self.mode=="standard"):
            quality=dict(mode='standard',raw=raw,metrics=metrics)
        else:
            blurred=(metrics.get('laplacian',0)<12 and metrics.get('contrast',0)<14)
            covered=metrics.get('foreground_cover',0)>=READABILITY_RULES['foreground_overlap']
            blocked=(raw=='search' or covered or blurred)
            geometry=dict(primary=self.geometry.primary,edges={})
            if box and not blocked:
                geometry=self.geometry.measure(f,image,box,endpoints,vehicles,model_mask)
            pos={k:v['position'] for k,v in geometry['edges'].items() if v['position']}
            if self.geometry.primary not in pos and raw=='ready' and self.geometry.primary not in geometry['edges']:
                old=footprint(box,endpoints,status)
                if old in {'left','right'}:
                    pos[self.geometry.primary]=old
                    geometry['edges'][self.geometry.primary]=dict(position=old,points=endpoints,source='global_model_and_native')
            reason=('target_missing_or_covered' if raw=='search' else 'foreground_cover' if covered else 'low_body_contrast' if blurred else
                    'position_observed' if pos else 'edge_uncertainty' if geometry['edges'] else 'no_supported_paint')
            quality=dict(mode='remote',raw='search' if raw=='search' else ('ready' if pos else 'unclear'),
                         metrics=metrics,geometry=geometry,positions=pos,reason=reason,visible=bool(box and not blocked))
        if clock is not None:
            return self.advance_recorded(f,seconds,box,endpoints,status,quality,clock)
        return self.advance(f,seconds,box,endpoints,status,quality)

    def evaluate_curves(self, f, seconds, image, box, vehicles, full_mask, curves, clock, reset=None):
        """직접 고른 흰 경계를 추적합니다. 선택 도형은 경계 식별용이며 판정에는 현재 영상이 필요합니다."""
        if reset:
            self.clocks[reset].restart()
        raw,metrics=lane_evidence(image,box,None,"boundary_missing",None,vehicles)
        visible=(bool(box) and raw!="search" and metrics.get("foreground_cover",0)<READABILITY_RULES["foreground_overlap"]
                 and not (metrics.get("laplacian",0)<12 and metrics.get("contrast",0)<14))
        if clock["freeze"] and self.last_reading and visible:
            return self.advance_recorded(f,seconds,box,None,None,self.last_reading,clock)
        edges={}
        for side,curve in curves.items():
            fit=curve.measure(image,full_mask,vehicles,box)
            if fit and visible:
                edges[side]=fit
        pos={side:e["position"] for side,e in edges.items() if e["position"]}
        quality=dict(mode="remote",geometry=dict(edges=edges),positions=pos,visible=visible,metrics=metrics,
                     raw="search" if raw=="search" else "ready" if pos else "unclear")
        if reset: quality["reset_boundary"]=reset
        return self.advance_recorded(f,seconds,box,None,None,quality,clock)

    def advance_recorded(self,f,seconds,box,endpoints,status,quality,clock):
        # 녹화 정지 화면은 같은 관측입니다. 실제 프레임 번호와 주행 시계의 번호를 따로 기억합니다.
        if clock['freeze'] and self.last_reading and box and quality.get('visible',True) and quality.get('raw')!='search' and self.last_reading.get('raw')!='search':
            return [],dict(self.last_reading,freeze=True)
        drive=clock['drive_s']
        self.observations.append((f,seconds))
        events,state=self.advance(len(self.observations),drive,box,endpoints,status,quality)
        for event in events:
            event.update(driving_time_s=event['time_s'],time_s=seconds,frame=f,confirmed_frame=f)
            for key in ('maneuver_start_frame','opposite_start_frame'):
                if event.get(key): event[key]=self.observations[event[key]-1][0]
        if state.get('mode')=='remote':
            values=[c.state.previous_time-c.state.start for side,c in self.clocks.items()
                    if state['positions'].get(side)=='contact' and c.state.start is not None]
        else:
            c=self.legacy.behavior
            values=[drive-c.start] if c.start is not None else []
        state.update(contact_seconds=round(max(values,default=0.),3) if state['counting'] else None,freeze=False)
        self.last_reading=state
        return events,state

    def advance(self, f, seconds, box, endpoints, status, quality):
        mode=quality['mode']
        if mode!=self.mode:
            for clock in self.clocks.values(): clock.restart()
            self.legacy=LaneReadability(self.legacy.behavior.fps)
            self.mode=mode
        raw=quality['raw']
        if mode=='standard':
            events,state=self.legacy.update(f,seconds,box,endpoints,status,raw)
            self.notice=state['notice']
            self.bad_since=None
            return events,dict(quality,**{k:v for k,v in state.items() if k!='raw'})
        events=[]
        for side,clock in self.clocks.items():
            edge=quality['geometry']['edges'].get(side) or {}
            band=(box is not None and edge.get('position') is None and edge.get('model_rows',0)>=4
                  and edge.get('gap_px',float('inf'))<=max(5,.35*(box[3]-box[1])))
            pos=quality['positions'].get(side)
            strong=False
            if pos=='contact' and box and 'x_at_bottom' in edge:
                x=edge['x_at_bottom']
                # 도색이 바퀴 안쪽까지 충분히 들어온 한 장은 짧은 행동의 직접 근거로 사용합니다.
                strong=(min(x-box[0],box[2]-x)>max(3,.22*(box[2]-box[0])) and
                        edge['gap_px']<=2 and edge['residual_px']<=.8 and edge['model_rows']>=8)
            found=clock.update(f,seconds,pos,quality['visible'],band,strong)
            events.extend(dict(e,boundary_side=side) for e in found)
        ready=bool(quality['positions'])
        if ready:
            self.bad_since=None
            self.notice='ready'
        else:
            if self.bad_since is None or self.bad_since[0]!=raw:
                self.bad_since=(raw,seconds)
            if self.notice is None or seconds-self.bad_since[1]+1e-8>=HOLD_SECONDS:
                self.notice=raw
        return events,dict(quality,notice=self.notice,counting=ready)



def analyze_contact_rows(rows, fps):
    """저장한 관측도 실시간 분석과 같은 집계기에 순서대로 넣습니다."""
    behavior = LaneBehavior(fps)
    gate = LaneReadability(fps)
    events = []
    scene = None
    for row in rows:
        args=(row["frame"],row["seconds"],row.get("box"),row.get("boundary"),row.get("lane_observation",row.get("status")))
        reading=row.get("lane_readability") or {}
        if reading.get("mode"):
            if scene is None:
                # 재생에는 저장된 양쪽 경계 관측만 필요합니다.
                scene=SceneLaneAnalysis(fps,[[0,0],[1,1]])
            if reading.get('reset_boundary'):
                scene.clocks[reading['reset_boundary']].restart()
            if 'drive_s' in row:
                found,_=scene.advance_recorded(*args,reading,row)
            else:
                found,_=scene.advance(*args,reading)
        elif reading:
            found,_=gate.update(*args,row["lane_readability"]["raw"],row.get("paint_half_width",0.))
        else:
            found=behavior.observe(*args,row.get("paint_half_width",0.))
        events.extend(dict(event, track_id=row.get("track_id"), event_source="automatic") for event in found)
    return events


def draw_hud(canvas, font, number, fps, count, track_id, status):
    detail = f"ID {track_id}   F{number:04d}  {(number-1)/fps:.2f}초   {status}"
    from importlib import import_module
    hud = import_module("041_redbox_mvp")
    # 진단 영상도 공통 패널의 글자 경계와 알파 합성을 사용합니다.
    region = canvas[:min(100,canvas.shape[0])]
    panel = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
    hud.hud_panel(panel, 16, 13, [(0, [(f"경계 관찰  {count}건", hud.HUD_GREEN)], font.size),
                                  (30, [(detail, hud.HUD_WHITE)], font.size)])
    region[:] = cv2.cvtColor(np.asarray(panel), cv2.COLOR_RGB2BGR)


def save_original_clips(video, output, events, fps, shape, count, *, open_video=cv2.VideoCapture):
    if not events:
        return
    folder = output / "original_clips"
    folder.mkdir()
    height, width = shape
    radius = round(fps * 3)
    capture = open_video(str(video.resolve()))
    try:
        if not capture.isOpened():
            raise RuntimeError("후보 클립을 만들 원본을 열 수 없습니다.")
        for event in events:
            number = event["frame"]
            # 프레임은 1부터 셉니다. 끝 시각은 마지막 프레임의 재생이 끝나는 시각입니다.
            first = max(1, number - radius)
            last = min(count, number + radius - 1)
            clip = folder / f"candidate_{event['candidate']:03d}_ID{event['track_id']}_F{number:04d}.mp4"
            temporary = clip.with_suffix(".part.mp4")
            writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            try:
                if not capture.set(cv2.CAP_PROP_POS_FRAMES, first - 1) or not writer.isOpened():
                    raise RuntimeError(f"후보 클립을 열 수 없습니다: {clip}")
                for frame_no in range(first, last + 1):
                    ok, frame = capture.read()
                    if not ok or frame.shape[:2] != shape:
                        raise RuntimeError(f"후보 클립의 원본 프레임을 읽지 못했습니다: F{frame_no}")
                    writer.write(frame)
            finally:
                writer.release()
            verify_video(temporary, shape, fps, last - first + 1)
            temporary.replace(clip)
            event.update(clip_path=str(clip), clip_start_frame=first, clip_last_frame=last,
                         clip_start_s=(first - 1) / fps, clip_end_s_exclusive=last / fps,
                         clip_frames=last - first + 1, clip_duration_s=(last - first + 1) / fps,
                         clip_start_truncated=(first > number - radius), clip_end_truncated=(last < number + radius - 1),
                         clip_verified=True, clip_audio="none")
    finally:
        capture.release()


def render(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "lane_crossing_candidates.mp4"
    if path.exists():
        raise FileExistsError(path)
    cap = cv2.VideoCapture(str(args.video.resolve()))
    writer = cv2.VideoWriter()
    font = ImageFont.truetype(str(args.font), 23)
    model = load_lane_model(args.model, torch.device("cuda:0"))
    device = torch.device("cuda:0")
    timing = (torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True))
    cv2.setNumThreads(2)
    torch.set_num_threads(4)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width, height, count = (int(cap.get(k)) for k in (
        cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT, cv2.CAP_PROP_FRAME_COUNT
    ))
    selected = None
    if args.selected_track:
        data = json.loads(args.selected_track.read_text(encoding="utf-8"))
        selected = data["frames"]
        if (data["video_sha256"] != video_digest(args.video) or abs(data["fps"] - fps) > .01
                or not 0 < len(selected) <= count
                or any(row["frame"] != i for i, row in enumerate(selected, 1))):
            raise ValueError("수동 선택·추적 기록과 원본 영상이 일치하지 않습니다.")
        track = [row["vehicles"] for row in selected]
    else:
        track = read_track_replay(args.tracks, args.video, count, fps, width, height)
    start_frame = args.start_frame if args.start_frame is not None else (1 if selected else 170)
    end_frame = args.end_frame if args.end_frame is not None else len(track)
    if not start_frame <= end_frame <= len(track):
        raise ValueError("검증 프레임 범위가 원본 영상 밖입니다.")
    if selected:
        if not any(row["selection"] == args.selection and row["status"] == "confirmed"
                   for row in selected[start_frame - 1:end_frame]):
            raise ValueError(f"지정한 구간에 수동 선택 #{args.selection}의 확정 상자가 없습니다.")
    else:
        selected_categories = {car["class"] for detections in track[start_frame - 1:end_frame]
                               for car in detections if car["id"] == args.track_id}
        if args.target_class not in selected_categories:
            raise ValueError(f"선택 구간에서 ID {args.track_id}의 {args.target_class} 추적 기록을 찾지 못했습니다.")
    scale = np.array([SIZE[0] / width, SIZE[1] / height])
    seed = (np.array(args.seed_line).reshape(2, 2) * scale).flatten()
    boundary = Boundary(seed)
    paint_rows = (max(143, int(min(seed[1], seed[3])) - 13), min(SIZE[1] - 2, int(max(seed[1], seed[3])) - 3))
    crossing = Crossing(fps)
    # 기존 6프레임 경계 통과 진단과 사용자에게 표시할 행동 사건은 각각 보관합니다.
    from importlib import import_module
    from collections import Counter
    hud_module = import_module("041_redbox_mvp")
    behavior = LaneBehavior(fps)
    actions, action_counts = [], Counter()
    events = []
    actual_count = 0
    hold_labels = {
        "before_selection": "선택 대기", "after_selection": "검증 구간 종료",
        "tracking_hold": "추적 보류",
        "crossing_unobserved_during_tracking_gap": "판정 보류 · 추적 공백 중 통과 불명",
        "track_id_missing": "판정 보류 · ID 없음",
        "track_class_changed": "판정 보류 · 차량 상자 불확실",
        "boundary_missing": "판정 보류 · 경계 미검출",
        "boundary_not_supported": "판정 보류 · 경계 근거 부족",
        "boundary_occluded": "판정 보류 · 경계 가림",
        "near_boundary": "판정 보류 · 경계에 근접",
    }
    try:
        if not cap.isOpened() or not writer.open(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)):
            raise RuntimeError("MP4를 열 수 없습니다.")
        from redbox_lane_geometry import recording_clock
        clip_clock=recording_clock(cap,1,len(track),source_seconds)
        observed_frames=[]
        with (output / "frames.jsonl").open("x", encoding="utf-8") as stream:
            for number, detections in enumerate(track, 1):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError(f"원본 프레임 {number}를 읽을 수 없습니다.")
                actual_count = number
                mask, _ = predict_lane(model, frame, device, SIZE, timing)
                seconds = source_seconds(cap, number, fps)
                canvas = draw_overlay(frame, mask, detections, number, seconds, SIZE)
                selection_active = True
                if selected:
                    row = selected[number - 1]
                    selection_active = row["selection"] == args.selection
                    # ID가 바뀌더라도 006이 같은 차량으로 채택한 상자만 판정합니다.
                    # 주변 차량의 상자는 경계 가림을 검사할 때만 사용합니다.
                    vehicle = row if selection_active and row["status"] == "confirmed" else None
                    target_id = vehicle["id"] if vehicle else None
                else:
                    vehicle = next((car for car in detections if car["id"] == args.track_id), None)
                    target_id = args.track_id
                boxes = [np.asarray(car["box"]) * np.tile(scale, 2) for car in detections]
                active = start_frame <= number <= end_frame and selection_active
                rows = boundary.detect(mask, boxes) if active else None
                boundary_source = "model" if rows is not None else None
                if active and rows is None and args.yellow_support:
                    # 모델 근거가 부족할 때만 같은 경계 주변의 눈에 보이는 노란 도색을 확인합니다.
                    small = cv2.resize(frame, SIZE, interpolation=cv2.INTER_AREA)
                    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                    yellow = cv2.inRange(hsv, (12, 80, 100), (42, 255, 255))
                    # 이중선의 옆 줄과 차체 색을 피하려고 처음 지정한 선 가까이만 확인합니다.
                    rows = boundary.detect(yellow, boxes, row_limits=paint_rows, min_points=5, min_span=16, corridor=10)
                    if rows is not None:
                        boundary_source = "yellow_paint"
                point = None
                side = distance = None
                reason = ("before_selection" if number < start_frame or
                          (selected and row["selection"] < args.selection) else "after_selection")
                if active:
                    if vehicle is None:
                        reason = "tracking_hold" if selected else "track_id_missing"
                    elif not selected and vehicle["class"] != args.target_class:
                        reason = "track_class_changed"
                    else:
                        x1, y1, x2, y2 = map(round, vehicle["box"])
                        point = ((x1 + x2) / 2, y2)
                        cv2.rectangle(canvas, (x1, y1), (x2, y2), (250, 100, 235), 3)
                        cv2.drawMarker(canvas, (round(point[0]), y2), (250, 100, 235), cv2.MARKER_CROSS, 23, 3)
                        if rows is None:
                            reason = "boundary_missing"
                        else:
                            side, distance, reason = boundary.classify(
                                np.array(point) * scale, rows, boxes, paint_support=boundary_source == "yellow_paint"
                            )
                if rows is not None:
                    endpoints = [tuple(np.rint(np.array([np.polyval(boundary.line, y), y]) / scale).astype(int))
                                 for y in (rows.min(), rows.max())]
                    cv2.line(canvas, *endpoints, (250, 215, 55), 3, cv2.LINE_AA)
                # 추적을 놓치면 반대쪽 확인을 처음부터 다시 시작합니다.
                # 보이지 않는 동안 경계를 넘었는지는 계산에 넣지 않습니다.
                event = crossing.update(number, side, reason in {"track_id_missing", "track_class_changed", "tracking_hold"})
                endpoints = boundary.endpoints(rows, scale)
                observed=clip_clock[number-1]
                actions_now=[]
                if not observed["freeze"] or vehicle is None or not active:
                    observed_frames.append(number)
                    actions_now=behavior.observe(len(observed_frames),observed["drive_s"],vehicle["box"] if vehicle and active else None,endpoints,reason)
                for action in actions_now:
                    action.update(frame=number,confirmed_frame=number,driving_time_s=action["time_s"],time_s=seconds)
                    for key in ("opposite_start_frame","maneuver_start_frame"):
                        if action.get(key): action[key]=observed_frames[action[key]-1]
                    entry = dict(action, track_id=target_id, source_video=args.video.name, event_source="automatic",
                                 incident_id=f"selection-{args.selection}-F{number}-{len(actions)+1}",
                                 hud_anchor=hud_module.event_position(vehicle["box"],width,height))
                    actions.append(hud_module.set_float_slot(entry,actions))
                    action_counts[entry["label"]] += 1
                if crossing.recovery_hold:
                    reason = "crossing_unobserved_during_tracking_gap"
                if event is not None:
                    events.append(dict(label=EVENT_LABEL, source_video=args.video.name, candidate=len(events)+1,
                                       frame=number, time_s=seconds, track_id=target_id,
                                       direction=f"{event['from_side']}_to_{event['to_side']}",
                                       confirmation_boundary_source=boundary_source, **event))
                status = ("경계 왼쪽" if side == "left" else "경계 오른쪽") if reason == "observed" else hold_labels[reason]
                draw_hud(canvas, font, number, fps, len(events), target_id if target_id is not None else "—", status)
                if actions:
                    panel = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
                    rows = [(i*30, hud_module.count_parts(label, total), 22)
                            for i,(label,total) in enumerate(action_counts.items())]
                    hud_module.hud_panel(panel,width-18,18,rows,align="right")
                    hud_module.draw_event_floats(panel,actions,seconds)
                    canvas = cv2.cvtColor(np.asarray(panel),cv2.COLOR_RGB2BGR)
                writer.write(canvas)
                stream.write(json.dumps(dict(frame=number, time_s=seconds, target_id=target_id, **observed,
                                             footprint_position=behavior.last_position, event_counts=dict(action_counts),
                                             target_point=point, side=side, distance_px=distance, status=reason,
                                             boundary_source=boundary_source,
                                             boundary_fit=boundary.line.tolist() if rows is not None else None,
                                             boundary_rows=rows.tolist() if rows is not None else None,
                                             stable_side=crossing.stable, count=len(events))) + "\n")
    finally:
        writer.release()
        cap.release()
    verify_video(path, (height, width), fps, actual_count)
    (output/"lane_events.json").write_text(json.dumps(dict(lane_rule_version=LANE_RULE_VERSION,events=actions,
                                          event_counts=dict(action_counts)),indent=2,ensure_ascii=False),encoding="utf-8")
    save_original_clips(args.video, output, events, fps, (height, width), count)
    (output / "candidates.json").write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(events, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--tracks", type=Path, default=DEFAULT_TRACK)
    inputs.add_argument("--selected-track", type=Path, help="006의 수동 선택·추적 JSON")
    parser.add_argument("--selection", type=int, default=1, help="집계할 수동 선택 순번")
    parser.add_argument("--track-id", type=int, default=72)
    parser.add_argument("--target-class", default="car")
    parser.add_argument("--start-frame", type=int, help="기본값은 수동 선택 모드 1, 기존 ID 지정 모드 170")
    parser.add_argument("--end-frame", type=int, help="마지막으로 판정할 프레임")
    parser.add_argument("--yellow-support", action="store_true", help="노란 경계에서 보이는 도색을 보조 근거로 사용합니다.")
    parser.add_argument("--seed-line", nargs=4, type=float, default=(770, 340, 1140, 637))
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/malgunbd.ttf"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (args.start_frame is not None and args.start_frame < 1 or args.selection < 1
            or args.seed_line[1] == args.seed_line[3] or args.seed_line[0] == args.seed_line[2]):
        parser.error("시작 프레임과 차선의 시작 좌표를 확인하세요.")
    render(args)


if __name__ == "__main__":
    main()
