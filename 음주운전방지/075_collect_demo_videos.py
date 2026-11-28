# 075 · 제출 직전에 고를 수 있도록 검수된 시연본을 한 폴더에 모읍니다.
# 입력은 아래의 기존 제출본과 프로젝트별 최종 확인 영상입니다.
# 영상 전체를 읽고 장면 표본과 지문을 남긴 뒤, --copy에서 검증된 사본만 저장합니다.
# 다음 단계에서는 목록의 사건 종류와 재생시간을 보고 제출할 영상을 고릅니다.
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
SUBMIT = ROOT.parents[1] / "RedBox_11월30일_제출용"
DEST = SUBMIT / "최종_시연영상_모음"
REVIEW = OUTPUT / "mvp_review_drive2"
INDEX = REVIEW / "모음검수.json"


def selections():
    # 같은 장면이라도 원본과 나란히 비교하는 영상과 단일 HUD 영상은 따로 고릅니다.
    cases = []
    def add(path, title=None):
        cases.append((path, title or path.name))

    add(REVIEW / "음주운전2_분석.mp4")
    for name in ["00_RedBox_MVP_종합시연", "01_차량추적_차선통과_BeforeAfter", "02_번호판OCR_차량정보_BeforeAfter"]:
        add(SUBMIT / (name + ".mp4"))
    for name in ["정지선위반2_BeforeAfter", "정지선위반3_BeforeAfter"]:
        add(SUBMIT / "정지선_시연" / (name + ".mp4"))
    # 다음 자료는 녹색 신호에서 정상 통과하는 별개 실험입니다. 나중의 정차 시연과 장면이 다릅니다.
    add(OUTPUT / "lane_video_197_mvp/terms_before_submission_backup/03_정지선통과_실험_BeforeAfter.mp4")
    for name in ["00_RedBox_종합시연", "07_졸음운전_예측", "08_원거리_타깃_분석",
                 "자동분석/01_차량번호_추적", "수동검증/02_정상차선변경_화물차",
                 "수동검증/03_정상차선변경_흰승용차", "램프위치지정/04_제동과_우측점멸",
                 "수동검증/05_정지선위반_정차차량", "수동검증/06_정지선위반_이륜차",
                 "차선접촉_검증/졸음운전4_분석", "차선접촉_검증/테스트용1_분석", "차선접촉_검증/테스트용1_비포애프터"]:
        add(SUBMIT / "신규_시연_검토용" / (name + ".mp4"))
    add(OUTPUT / "mvp_plate_hud_1128/browser_local/jobs/930bc2b3217c/hud.mp4", "낮_검은SUV_차선행동_분석.mp4")
    add(OUTPUT / "mvp_review_pair/regression_near/10/hud.mp4", "낮_흰승용차_0건대조.mp4")
    add(OUTPUT / "mvp_review_pair/regression_signal_normal/hud.mp4", "정상차선변경1_미검출대조.mp4")
    selected = OUTPUT / "lane_video_197_selected_20261120"
    add(selected / "uturn/lane_crossing_candidates.mp4", "불법유턴1_경계통과_분석.mp4")
    add(selected / "merge/lane_crossing_candidates.mp4", "끼어들기_경계판독_대조.mp4")
    stop = OUTPUT / "lane_video_197_stopline_20261124"
    add(stop / "regression/night/hud.mp4", "밤_은색승용차_추적복귀.mp4")
    add(stop / "regression/01/hud.mp4", "BB_20260111_125520_터널_추적보류.mp4")
    tracking = OUTPUT / "lane_video_197_tracking_20261124/final"
    for code, title in [("02", "20261113_134044_후방_버스추적"), ("03", "20261113_141715_원거리추적"),
                        ("04", "20261113_192304_야간_추적보류"), ("05", "20261122_141908_번호판인식"),
                        ("06", "20261122_171859_차량추적"), ("07", "20261122_172259_차량추적")]:
        # 05의 추적 회귀본은 OCR을 끈 실행입니다. 실제로 번호를 읽은 최종 HUD를 사용합니다.
        directory = OUTPUT / "lane_video_197_mvp/validation_final_20261123" if code == "05" else tracking
        add(directory / code / "hud.mp4", "BB_" + title + ".mp4")
    add(stop / "chrome_final/jobs/bc3b5cf4e40e/hud.mp4", "정지선_녹색신호_통과분석.mp4")
    add(stop / "chrome_final/jobs/029c7e109796/hud.mp4", "정지선_정상정지_분석.mp4")
    for code, title in [("02", "우회전_통과분석"), ("04", "우회전_누락대조"),
                        ("05", "화물차_판독보류"), ("06", "옆차량_0건대조")]:
        add(OUTPUT / "lane_video_197_mvp/stopline_final_20261124" / code / "hud.mp4", "정지선_" + title + ".mp4")
    for key in ("133431", "133631"):
        filename = f"BB_20261123_{key}_정지선위반_분석_11.28.mp4"
        add(OUTPUT / "mvp_review_redstop" / filename)
    return cases


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect():
    cases = selections()
    assert len({n for _, n in cases}) == len(cases)
    records, strips = [], []
    for source, name in cases:
        cap = cv2.VideoCapture(str(source))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w, h = int(cap.get(3)), int(cap.get(4))
        if not cap.isOpened() or min(count, fps, w, h) <= 0:
            raise OSError(source)
        samples = []
        try:
            for n in range(count):
                ok, frame = cap.read()
                if not ok or frame.shape[:2] != (h, w):
                    raise ValueError((name, n+1))
                if n in {0, count//2, count-1}:
                    thumb = np.zeros((85,160,3), np.uint8)
                    scale = min(160/w,85/h)
                    small = cv2.resize(frame, (max(1,round(w*scale)), max(1,round(h*scale))), interpolation=cv2.INTER_AREA)
                    sy,sx = small.shape[:2]
                    thumb[(85-sy)//2:(85-sy)//2+sy,(160-sx)//2:(160-sx)//2+sx] = small
                    samples.append(thumb)
            if cap.read()[0]:
                raise ValueError(("프레임 수 불일치", name))
        finally:
            cap.release()
        strip = np.hstack(samples)
        index = len(records)+1
        cv2.putText(strip, str(index), (4,17), 0,.56,(0,0,0),3)
        cv2.putText(strip, str(index), (4,17), 0,.56,(255,255,255),1)
        strips.append(strip)
        records.append(dict(index=index, name=name, source=str(source), sha256=digest(source),
                            decoded=count, fps=fps, seconds=count/fps, width=w, height=h, bytes=source.stat().st_size))
        print(index, name, count, flush=True)
    if len({r["sha256"] for r in records}) != len(records):
        raise ValueError("내용이 동일한 영상이 중복 선택되었습니다.")
    REVIEW.mkdir(parents=True, exist_ok=True)
    for start in range(0,len(strips),10):
        file = REVIEW / f"목록_재생검수_{start+1:02d}.jpg"
        cv2.imencode(".jpg", np.vstack(strips[start:start+10]))[1].tofile(file)
    INDEX.write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding="utf8")


def collect():
    rows = json.loads(INDEX.read_text(encoding="utf8"))
    if [(Path(r["source"]), r["name"]) for r in rows] != selections():
        raise ValueError("검수 목록이 달라졌습니다. inspect를 다시 실행하세요.")
    DEST.mkdir(exist_ok=True)
    names = {r["name"] for r in rows}
    for existing in DEST.iterdir():
        if not existing.is_file() or existing.name not in names:
            raise ValueError(f"별도 확인이 필요한 기존 항목: {existing}")
    for r in rows:
        source = Path(r["source"])
        target = DEST / r["name"]
        if digest(source) != r["sha256"]:
            raise ValueError(("검수 이후 원본 변경", source))
        if not target.exists():
            # 같은 폴더의 임시 파일에서 지문이 맞아야 실제 MP4 이름을 붙입니다.
            with NamedTemporaryFile(dir=DEST, delete=False, suffix=".part") as tmp:
                pending = Path(tmp.name)
            try:
                shutil.copyfile(source, pending)
                if digest(pending) != r["sha256"]:
                    raise OSError(pending)
                pending.rename(target)
            finally:
                pending.unlink(missing_ok=True)
        if digest(target) != r["sha256"]:
            raise FileExistsError(f"같은 이름의 다른 파일을 보존했습니다: {target}")
    if {p.name for p in DEST.iterdir()} != names:
        raise ValueError("최종 폴더에 예상하지 않은 항목이 있습니다.")
    lines = ["# 최종 시연 영상 모음", "", f"검수한 MP4 {len(rows)}개, 합계 {sum(r['seconds'] for r in rows):.2f}초. "
             "원본 전체 디코딩과 복사본 SHA-256 대조를 완료했습니다.", "",
             "| 번호 | 파일 | 재생시간(초) | 프레임 | 검수본 출처 |","|---:|---|---:|---:|---|"]
    for r in rows:
        relative = Path(os.path.relpath(DEST / r["name"], REVIEW)).as_posix()
        lines.append(f"| {r['index']} | [{r['name']}](<{relative}>) | {r['seconds']:.2f} | "
                     f"{r['decoded']} | {r['source']} |")
    lines.extend(["", "종합본은 장면 구성과 화면 형식이 다른 두 편입니다. 정지선위반3의 같은 이륜차 좌우 비교본은 "
                  "3840×1144 검수본으로 골랐습니다. 녹색 신호 정상 통과 실험은 별개 차량·교차로 장면입니다.",
                  "원본 영상, 중간 인코딩, 같은 장면·형식의 구버전, 학습·램프 측정용 크롭은 수집 대상에서 제외했습니다. "
                  "누락·판독 보류·0건 대조 영상은 결과를 파일명에 표시했습니다."])
    (REVIEW / "영상목록.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print(DEST, len(rows), "개 SHA-256 일치", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action",choices=["inspect", "copy"])
    if cli.parse_args().action == "inspect":
        inspect()
    else:
        collect()

