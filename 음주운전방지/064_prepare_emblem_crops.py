# 064  같은 촬영 장면 분할에서 차량만 잘라 엠블럼 좌표를 다시 계산합니다.
# 전체 도로 사진으로 배운 모델이 차량 확대 사진에서 약해진 원인을 비교하는 실습입니다.
# 060 조사 결과와 YOLO 차량 상자를 읽어 crop JPG·TXT와 제외 사유를 저장합니다.
# 061로 별도 가중치를 학습하고, 062 검증 기준을 정한 뒤에만 test를 평가합니다.
import argparse
import json
import os
from pathlib import Path
import cv2
import numpy as np
import yaml

from redbox_emblem import owned
ROOT = Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"] = "true"
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "output/emblem_v1/config")
from ultralytics import YOLO


def prepare(audit_path, output, split_names):
    audit = json.loads(audit_path.read_text(encoding="utf8"))
    classes = audit["classes"]
    original_names = audit["config"]["names"]
    net = YOLO(str(ROOT / "yolo26n.pt"))
    output.mkdir(exist_ok=True, parents=True)
    cfg = dict(path=output.resolve().as_posix(), train="train/images", val="valid/images", test="test/images", names=classes)
    config_path = output / "data.yaml"
    if config_path.exists():
        if yaml.safe_load(config_path.read_text(encoding="utf8")) != cfg:
            raise ValueError("이 위치의 기존 데이터 구성이 다릅니다.")
    else:
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf8")
    for split in split_names:
        directory = output / split
        directory.mkdir(exist_ok=False)
        (directory / "images").mkdir()
        (directory / "labels").mkdir()
        log = []
        indices = audit["used"][split]
        for start in range(0, len(indices), 12):
            rows = [audit["items"][i] for i in indices[start:start+12]]
            images = [cv2.imdecode(np.fromfile(audit_path.parent / split / "images" / r["file"], np.uint8), 1) for r in rows]
            results = net.predict(images, classes=[2, 3, 5, 7], conf=.1, imgsz=640, device=0, verbose=False)
            for row, im, result in zip(rows, images, results):
                entry = dict(file=row["file"], group=row["group"])
                log.append(entry)
                if len(row["rows"]) != 1:
                    entry["status"] = "표식 하나로 해당 차량을 고를 수 없음"
                    continue
                k, x, y, w, h = row["rows"][0]
                height, width = im.shape[:2]
                badge = [(x-w/2)*width, (y-h/2)*height, (x+w/2)*width, (y+h/2)*height]
                boxes = np.rint(result.boxes.xyxy.cpu().numpy()).astype(int)
                targets = [box for box in boxes if owned(badge, box, [])]
                if len(targets) != 1:
                    entry["status"] = "표식이 들어 있는 차량 상자가 없거나 여러 개"
                    continue
                a, b, c, d = targets[0]
                if c-a < 12 or d-b < 12:
                    entry["status"] = "차량 상자가 너무 작음"
                    continue
                brand = original_names[k]
                label = ""
                if brand in classes:
                    # 원본의 표식 중심에서 차량 왼쪽·위 좌표를 빼고 차량 폭·높이로 나눕니다.
                    cx, cy = (x*width-a)/(c-a), (y*height-b)/(d-b)
                    label = f"{classes.index(brand)} {cx:.9f} {cy:.9f} {w*width/(c-a):.9f} {h*height/(d-b):.9f}\n"
                crop = im[b:d, a:c]
                # PNG를 써서 작은 표식이 JPG 재압축으로 다시 손실되지 않게 합니다.
                stem = Path(row["file"]).stem
                cv2.imencode(".png", crop)[1].tofile(directory / "images" / (stem+".png"))
                (directory / "labels" / (stem+".txt")).write_text(label, encoding="utf8")
                entry.update(status="ok", brand=brand, vehicle=[int(v) for v in targets[0]], badge=badge)
        (directory / "log.json").write_text(json.dumps(log,ensure_ascii=False), encoding="utf8")
        print(split, sum(r["status"]=="ok" for r in log), "/", len(log), flush=True)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--splits", nargs="+", choices=["train","valid","test"], default=["train","valid"])
    args = parser.parse_args()
    prepare(args.audit, args.output, args.splits)
