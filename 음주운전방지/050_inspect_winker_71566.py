# 050  국도 CCTV에서 같은 차량의 방향지시등 행동 구간 찾기
# 원천 PNG와 JSON을 폴더·파일명으로 짝짓고 촬영 단위와 차량 라벨을 셉니다.
# 한 차량에 같은 행동이 연속해서 붙은 구간만 051의 시험 학습 입력으로 남깁니다.
# --data는 경량본의 루트이고 --output에는 조사 결과와 육안 점검용 사진을 저장합니다.

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from convert_lane_masks_197 import encode, read_image
from redbox_winker import LABELS, SEQUENCE_LENGTH


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_sheet(image, data, frame):
    # 큰 사진에는 실제 차 위치를, 아래에는 같은 프레임의 차량 확대도를 표시합니다.
    canvas = image.copy()
    crops = []
    for obj in data["annotation"]:
        if obj["DrivingType"] not in LABELS:
            continue
        x, y, w, h = map(int, obj["bbox"])
        crops.append(cv2.resize(image[y:y+h, x:x+w], (180, 110)))
        cv2.rectangle(canvas, (x, y), (x+w, y+h), (60, 255, 60), 2)
        cv2.putText(canvas, f"ID {obj['id']}", (x, y-4), 0, .65, (60, 255, 60), 2)
    for entry in data["winker"]:
        for box in entry.values():
            x, y, w, h = map(int, box)
            cv2.rectangle(canvas, (x, y), (x+w, y+h), (0, 180, 255), 1)
    panel = cv2.resize(canvas, (640, 360))
    strip = np.zeros((110, 640, 3), np.uint8)
    for i, crop in enumerate(crops[:3]):
        strip[:, i*180:(i+1)*180] = crop
    cv2.putText(panel, f"F{frame}", (8, 26), 0, .7, (255, 255, 255), 2)
    return np.vstack([panel, strip])


def inspect(root, out):
    images, labels = root / "01.원천데이터", root / "02.라벨링데이터"
    if not images.is_dir() or not labels.is_dir():
        raise ValueError("원천데이터와 라벨링데이터 폴더를 확인하세요.")
    out.mkdir(parents=True, exist_ok=False)
    remaining = {p.relative_to(images) for p in images.rglob("*.png")}
    counts = Counter(p.suffix.lower() for p in root.rglob("*") if p.is_file())
    sequences, mismatches, unpaired, tracks = {}, Counter(), [], defaultdict(list)
    boxes = []
    for label in sorted(labels.rglob("*.json")):
        relative = label.relative_to(labels).with_suffix(".png")
        if relative not in remaining:
            unpaired.append(str(label))
            continue
        remaining.remove(relative)
        d = json.loads(label.read_text("utf-8-sig"))
        m, info = d["meta"], d["imageInfo"]
        folder, frame = label.parent.name, int(label.stem.rsplit("_", 1)[1])
        code = folder.split("_")[3]
        source = [m["cctvID"], m["created"], m["time"]]
        s = sequences.setdefault(folder, dict(code=code, source=source, frames=[],
            event_bounds=[], fps_field=[], driving_types=Counter(), ids=set(), winker_keys=Counter(),
            winker_nonempty=0, resolutions=set()))
        if s["source"] != source:
            raise ValueError(f"폴더 안의 촬영 정보가 달라졌습니다: {folder}")
        s["frames"].append(frame)
        for key, value in [("event_bounds", [float(m["eventstart"]), float(m["eventstop"])]),
                           ("fps_field", m["fpsNumber"])]:
            if value not in s[key]:
                s[key].append(value)
        s["resolutions"].add((info["width"], info["height"]))
        mismatches["internal_name_exact" if info["fileName"] == relative.name else
                   "internal_name_differs"] += 1
        s["winker_nonempty"] += bool(d.get("winker"))
        for item in d.get("winker", []):
            s["winker_keys"].update(item.keys())
        seen = Counter(obj["id"] for obj in d["annotation"])
        for obj in d["annotation"]:
            ident, action = obj["id"], obj["DrivingType"]
            s["driving_types"][action] += 1
            s["ids"].add(ident)
            if code not in ("n1", "an1") or action != LABELS[int(code == "an1")]:
                continue
            x, y, w, h = obj["bbox"]
            if (seen[ident] != 1 or w <= 0 or h <= 0 or x < 0 or y < 0
                    or x+w > info["width"] or y+h > info["height"]):
                continue
            tracks[folder, ident, action].append((frame, str(relative), [x,y,w,h]))
        if code in ("n1", "an1") and frame in (8, 15, 21):
            image = read_image(images / relative, cv2.IMREAD_COLOR)
            boxes.append((folder, sample_sheet(image, d, frame)))
    for folder, s in sequences.items():
        s["ids"] = sorted(s["ids"])
        s["resolutions"] = sorted(s["resolutions"])
        frames = sorted(s["frames"])
        s["missing_frames"] = sorted(set(range(frames[0], frames[-1]+1)) - set(frames))
        panels = [panel for group, panel in boxes if group == folder]
        if panels:
            path = out / (folder + ".jpg")
            path.write_bytes(encode(path, np.hstack(panels)))
    windows = []
    for (group, ident, action), rows in sorted(tracks.items()):
        # ID가 같아도 차가 갑자기 다른 위치로 뛰거나 중간 프레임이 비면 끊습니다.
        run = []
        for row in sorted(rows):
            frame, _, (x, y, w, h) = row
            if run:
                prev, _, (px, py, pw, ph) = run[-1]
                overlap = min(x+w, px+pw) > max(x,px) and min(y+h, py+ph) > max(y,py)
                if frame != prev+1 or not overlap:
                    run = []
            run.append(row)
            if len(run) >= SEQUENCE_LENGTH and (len(run)-SEQUENCE_LENGTH) % 5 == 0:
                windows.append(dict(group=group, source=sequences[group]["source"], id=ident,
                                    label=action, frames=run[-SEQUENCE_LENGTH:]))
    save_json(out / "inventory.json", dict(files=counts, matched=sum(mismatches.values()),
              name_check=mismatches, unpaired_json=unpaired, unpaired_png=sorted(map(str, remaining)),
              sequences=sequences))
    save_json(out / "smoke_windows.json", dict(images=str(images.resolve()), windows=windows))
    print("파일", counts, "매칭", sum(mismatches.values()), "시험 학습 구간", len(windows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inspect(args.data, args.output)
