# 025  이미지와 마스크를 세 묶음으로 나누기
# 인접 파일명으로 임시 구간을 만들어 비슷한 사진이 나뉘는 일을 줄입니다.
# 보정된 1,200쌍의 --manifest를 주고 --output으로 분할 목록 위치를 정합니다.
# 같은 시드로 train.csv, val.csv, test.csv를 만들고 학습에는 앞의 두 목록을 씁니다.

"""197번 daylight 이미지·마스크 1,200쌍의 임시 분할을 생성합니다."""

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2

from convert_lane_masks_197 import read_image, verify


TARGET = {"train": 960, "val": 120, "test": 120}
NUMERIC_GAP = 1000
STATUS = "provisional"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_pairs(manifest):
    rows = read_csv(manifest)
    if len(rows) != sum(TARGET.values()) or any(row["status"] != "성공" for row in rows):
        raise ValueError("전체 1,200행이 성공이어야 합니다.")
    image_ids = set()
    image_digests = set()
    paths = {column: set() for column in ("jpg", "json", "mask")}
    for row in rows:
        for column, seen in paths.items():
            path = Path(row[column])
            if not path.is_absolute() or not path.is_file() or path.resolve() in seen:
                raise ValueError(f"잘못되었거나 중복된 {column} 경로: {path}")
            seen.add(path.resolve())
        jpg, label, mask = (Path(row[column]) for column in paths)
        image_id = int(jpg.stem)
        if image_id in image_ids or mask.name.casefold() != f"{jpg.stem}_mask.png".casefold():
            raise ValueError(f"중복 이미지 번호 또는 마스크 이름 불일치: {jpg}")
        image_ids.add(image_id)
        metadata = json.loads(label.read_bytes())["image"]
        height, width = int(row["height"]), int(row["width"])
        photo = read_image(jpg, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if (metadata["file_name"].casefold() != jpg.name.casefold()
                or photo.shape[:2] != (height, width)
                or metadata["image_size"] != [height, width]):
            raise ValueError(f"JPG와 JSON의 파일명 또는 해상도 불일치: {jpg}")
        digest = hashlib.sha256(photo).digest()
        if digest in image_digests:
            raise ValueError(f"다른 경로에 동일한 이미지 픽셀이 있습니다: {jpg}")
        image_digests.add(digest)
        if verify(read_image(mask, cv2.IMREAD_UNCHANGED), (height, width)) != int(row["white_pixels"]):
            raise ValueError(f"마스크의 흰 픽셀 수 불일치: {mask}")
    if 2215570 not in image_ids:
        raise ValueError("보정 대상 2215570이 빠졌습니다.")
    return sorted(rows, key=lambda row: int(Path(row["jpg"]).stem))


def group_by_filename(rows):
    # 원본 영상 ID가 없어 파일명의 가까운 숫자를 임시 기준으로 사용합니다.
    groups = []
    previous = None
    for row in rows:
        number = int(Path(row["jpg"]).stem)
        if previous is None or number - previous > NUMERIC_GAP:
            groups.append([])
        groups[-1].append(row)
        previous = number
    for group in groups:
        start, end = (Path(group[index]["jpg"]).stem for index in (0, -1))
        for row in group:
            row.update(provisional_group=f"{start}-{end}", split_status=STATUS)
    return groups


def assign_groups(groups, seed):
    # 상태별로 (검증 수, 테스트 수)를 기록하며 각 그룹을 한 묶음에 통째로 넣습니다.
    random.Random(seed).shuffle(groups)
    choices = {(0, 0): ()}
    for group in groups:
        size = len(group)
        next_choices = {}
        for (val, test), allocations in choices.items():
            for split, counts in (("train", (val, test)), ("val", (val + size, test)),
                                  ("test", (val, test + size))):
                if counts[0] <= TARGET["val"] and counts[1] <= TARGET["test"]:
                    next_choices.setdefault(counts, (*allocations, split))
        choices = next_choices
    feasible = [counts for counts in choices if min(counts) > 0]
    if not feasible:
        raise ValueError("검증과 테스트에 각각 통째로 담을 그룹이 없습니다.")
    best = max(feasible, key=lambda counts: (sum(counts), min(counts)))
    splits = {split: [] for split in TARGET}
    for group, split in zip(groups, choices[best], strict=True):
        splits[split].extend(group)
    for rows in splits.values():
        rows.sort(key=lambda row: int(Path(row["jpg"]).stem))
    return splits


def write_splits(rows, splits, output, manifest, seed):
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as staging:
        stage = Path(staging)
        fieldnames = list(rows[0])
        observed = {}
        group_owners = {}
        count = {}
        for split, entries in splits.items():
            path = stage / f"{split}.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(entries)
            saved = read_csv(path)
            for row in saved:
                jpg, group = row["jpg"], row["provisional_group"]
                if jpg in observed or group_owners.setdefault(group, split) != split:
                    raise ValueError(f"CSV에 이미지 또는 임시 그룹이 겹칩니다: {jpg}")
                observed[jpg] = row
            count[split] = {"pairs": len(saved), "percent": 100 * len(saved) / len(rows),
                            "groups": len({row["provisional_group"] for row in saved})}
        if observed != {row["jpg"]: row for row in rows}:
            raise ValueError("CSV의 경로 또는 데이터 행이 입력과 다릅니다.")
        verification = {
            "split_status": STATUS,
            "manifest": str(manifest),
            "seed": seed,
            "adjacent_filename_gap": NUMERIC_GAP,
            "source_video_or_drive_ids_verified": False,
            "count": count,
            "checks": {"missing_pairs": 0, "duplicate_pairs": 0, "duplicate_image_pixels": 0,
                       "invalid_paths": 0, "overlapping_provisional_groups": 0},
        }
        (stage / "verification.json").write_text(
            json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for path in stage.iterdir():
            path.replace(output / path.name)
    print(json.dumps(verification, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="기본값은 매니페스트 옆 splits")
    parser.add_argument("--seed", type=int, default=197)
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    output = args.output.resolve() if args.output else manifest.parent / "splits"
    rows = load_pairs(manifest)
    splits = assign_groups(group_by_filename(rows), args.seed)
    write_splits(rows, splits, output, manifest, args.seed)


if __name__ == "__main__":
    main()
