# RedBox HUD에 표시할 차량 외관과 번호판 후보를 계산합니다.
# 확정된 차량 상자 아래쪽에서만 문자 영역을 찾고 여러 프레임의 판독을 비교합니다.
# 외관과 OCR 후보는 저장한 사건 기록에서 사용자가 직접 확인하고 수정할 수 있습니다.

from collections import Counter
from base64 import b64encode
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
from threading import Thread

import cv2
import numpy as np


PLATE = re.compile(r"[0-9]{2,3}[가-힣][0-9]{4}")
PLATE_IN_TEXT = re.compile(r"(?<![0-9가-힣])[0-9]{2,3}[가-힣][0-9]{4}(?![0-9가-힣])")
PLATE_CHARACTERS = "0123456789가나다라마거너더러머버서어저고노도로모보소오조구누두루무부수우주아바사자배하허호"
CLASSES = {"car": "승용 계열", "truck": "화물차", "bus": "버스", "motorcycle": "이륜차"}


def apparent_color(crop):
    # 유리창과 도로를 줄이기 위해 상자 중하단의 차체 양옆을 봅니다.
    h, w = crop.shape[:2]
    band = crop[int(h * .48):int(h * .78), int(w * .18):int(w * .82)]
    if band.size == 0 or min(h, w) < 45:
        return None
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hue, sat, value = hsv.T
    neutral = sat < 85
    if neutral.mean() >= .65:
        median = float(np.percentile(value[neutral], 45))
        return "검정·진회색 계열" if median < 100 else "흰색 계열" if median > 174 else "회색·은색 계열"
    blue = (hue >= 93) & (hue <= 131) & (sat >= 85) & (value >= 65)
    return "파랑 계열" if blue.mean() > .58 else None


class WindowsOCR:
    def __init__(self):
        self.process = None
        self.replies = Queue()
        self.available = True

    def read(self, gray):
        if not self.available:
            return ""
        try:
            if self.process is None:
                script = Path(__file__).with_name("045_read_korean_plate.ps1").read_text(encoding="utf-8")
                command = b64encode(script.encode("utf-16-le")).decode("ascii")
                self.process = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-EncodedCommand", command],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
                )
                Thread(target=self.receive, daemon=True).start()
            enlarged = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            enlarged = cv2.copyMakeBorder(enlarged, 12, 12, 12, 12, cv2.BORDER_REPLICATE)
            ok, png = cv2.imencode(".png", enlarged)
            if not ok:
                return ""
            self.process.stdin.write(b64encode(png.tobytes()).decode("ascii")+"\n")
            self.process.stdin.flush()
            result = self.replies.get(timeout=7)
            if result is None:
                self.available = False
                return ""
            return result
        except (OSError, Empty):
            self.available = False
            self.close()
            return ""

    def receive(self):
        for line in self.process.stdout:
            self.replies.put(line.strip())
        self.replies.put(None)

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=5)


class VehicleInfo:
    def __init__(self, ocr_reader=None, manual_plate=None):
        self.reader = ocr_reader
        self.manual_plate = manual_plate
        self.colors = Counter()
        self.classes = Counter()
        self.ocr_frames = []
        self.windows_ocr = WindowsOCR() if self.reader is not None else None

    def sample(self, frame, vehicle, number):
        self.classes[vehicle["class"]] += 1
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = map(round, vehicle["box"])
        crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if not crop.size:
            return
        color = apparent_color(crop)
        if color:
            self.colors[color] += 1
        if self.reader is None or len(self.ocr_frames) >= 12:
            return
        matches = {}
        ch, cw = crop.shape[:2]
        if cw >= 105 and ch >= 65:
            # CRAFT로 차량 하단의 문자 사각형을 찾고 한국어 OCR에 넣습니다.
            search = crop[round(ch*.38):round(ch*.99), round(cw*.05):round(cw*.96)]
            rects, _ = self.reader.detect(search, mag_ratio=2, text_threshold=.46, low_text=.28,
                                          link_threshold=.20, min_size=9, width_ths=.85)
            gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
            boxes = []
            for left, right, top, bottom in sorted(rects[0], key=lambda box: box[1]-box[0], reverse=True):
                w, h = right-left, bottom-top
                if 30 < w < .85*gray.shape[1] and 1.45 < w/max(1,h) < 8:
                    boxes.append([left, right, top, bottom])
            for left, right, top, bottom in boxes[:2]:
                roi = gray[max(0,top-7):bottom+7, max(0,left-8):right+8]
                if not roi.size:
                    continue
                for variant in (roi, cv2.createCLAHE(2,(6,3)).apply(roi)):
                    text = re.sub(r"[\s·•.,'\`]+", "", self.windows_ocr.read(variant))
                    for plate in PLATE_IN_TEXT.findall(text):
                        matches.setdefault(plate, {})["windows_ko"] = True
            # 다른 검출 설정에서 분리된 문자 박스도 있으므로 EasyOCR 결과를 함께 모읍니다.
            for points, raw, confidence in self.reader.readtext(
                    search, allowlist=PLATE_CHARACTERS, mag_ratio=2, text_threshold=.50,
                    low_text=.30, link_threshold=.33, min_size=10):
                text = re.sub(r"\s+", "", raw)
                q = np.asarray(points)
                bw, bh = np.ptp(q, axis=0)
                if (PLATE.fullmatch(text) and confidence >= .24
                        and 1.5 <= bw / max(bh, 1) <= 9 and bw >= 26):
                    entry = matches.setdefault(text, {})
                    entry["easyocr"] = max(entry.get("easyocr", 0), round(float(confidence), 3))
        self.ocr_frames.append({"frame": number, "matches": matches})

    def plate_candidate(self):
        counts = Counter(text for sample in self.ocr_frames for text in sample["matches"])
        top = counts.most_common(2)
        # 반사광 아래에서는 같은 글자 오독이 되풀이될 수 있어 최소 4장을 요구합니다.
        if (len(self.ocr_frames) >= 8 and top and top[0][1] >= 4
                and (len(top) == 1 or top[0][1] >= 2*top[1][1])):
            return top[0][0]
        return None

    def snapshot(self):
        colors = self.colors.most_common(1)
        classes = self.classes.most_common(1)
        plate = self.plate_candidate()
        return {
            "plate": self.manual_plate or plate,
            "plate_source": "manual" if self.manual_plate else "ocr_candidate" if plate else None,
            "ocr_candidate": plate,
            "color": colors[0][0] if colors and colors[0][1] >= 2
            and colors[0][1] / self.colors.total() >= .65 else None,
            "vehicle_type": CLASSES.get(classes[0][0]) if classes
            and classes[0][1] / self.classes.total() >= .7 else None,
            "model_name": None,
        }
