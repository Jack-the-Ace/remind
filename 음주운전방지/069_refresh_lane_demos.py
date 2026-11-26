# 069  이전 빠른 시연의 원본과 관측을 재사용해 현재 규칙의 재생 캐시를 만듭니다.
# 068의 졸음운전 영상과 사건 JSON도 같은 목록에 등록합니다.
# 새 디렉터리에서 전부 검증한 다음 웹에서 읽을 이름으로 옮깁니다.
import argparse
from collections import Counter
from importlib import import_module
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image


builder = import_module("049_build_redbox_demo")
review = import_module("067_render_driving_review")
drowsy = import_module("068_render_drowsy_demo")
mvp = review.mvp
rule = mvp.crossing_module.LANE_RULE_VERSION


def write_rows(path, rows):
    with path.open("x", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False)+"\n")


def migrate(old, dest):
    dest.mkdir()
    meta = review.read(old/"target.json")
    rows = [json.loads(s) for s in (old/"frames.jsonl").read_text(encoding="utf-8").splitlines()]
    # 049의 원본 클립은 원본 영상의 선택 프레임부터 시작합니다.
    shutil.copyfile(old/"original.mp4",dest/"original.mp4")
    reader = cv2.VideoCapture(str(dest/"original.mp4"))
    w,h = int(reader.get(3)), int(reader.get(4))
    with mvp.capture(mvp.source_path(meta["video"]),meta["camera"]) as source:
        source.set(1,meta["selection_frame"]-1)
        for row in rows:
            if not source.grab():
                raise ValueError("원본 시각 읽기 실패")
            row["seconds"]=mvp.crossing_module.source_seconds(source,row["frame"],meta["fps"])
    events = builder.prepare_events(rows,meta,{},(w,h))
    events.extend(e.copy() for e in meta["events"] if e["event_source"]=="manual_demo" and e["label"]!="차선침범")
    events.sort(key=lambda e:e["frame"])
    for index,event in enumerate(events):
        event.setdefault("incident_id",f"{old.name}-{event['frame']}-{index+1}")
        mvp.set_float_slot(event, events[:index])
    written=[]
    enc = review.writer(dest/"hud.mp4",meta["fps"],(w,h))
    try:
        for row in rows:
            ok,frame=reader.read()
            if not ok:
                raise ValueError("빠른 시연 원본 누락")
            arrived=[e for e in events if e["frame"]<=row["frame"]]
            counts=dict(Counter(e["label"] for e in arrived))
            new=any(e["frame"]==row["frame"] for e in arrived)
            row.update(count=len(arrived),event_counts=counts,new_event=new,demo_event_counts=counts,demo_new_event=new)
            if meta.get("reviewed_stop_line"):
                line=meta["reviewed_stop_line"]
                row["stop_line"]={"line":[line[:2],line[2:]]}
                row["status_text"]="타깃 추적 중" if row["box"] else "추적 보류"
            layer=mvp.draw_hud(frame,row,meta["source_kind"],overlay_only=True)
            mvp.draw_event_floats(layer,arrived,row["seconds"])
            image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).convert("RGBA")
            image.alpha_composite(layer.resize((w,h), Image.Resampling.BILINEAR))
            hud=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGBA2BGR)
            written.append(review.signature(hud))
            enc.write(hud)
    finally:
        reader.release()
        enc.release()
    review.verify(dest/"hud.mp4",written,(w,h),meta["fps"])
    if old.name=="lane-day":
        meta["demo_title"]="낮 영상 · 검은 SUV 차선 행동"
    meta.update(events=events,event_total=len(events),event_counts=rows[-1]["event_counts"],lane_rule_version=rule)
    review.save(dest/"target.json",meta)
    write_rows(dest/"frames.jsonl",rows)


def register_drowsy(render, dest):
    dest.mkdir()
    settings = review.read(render/"검증기록"/"07_졸음운전_시연설정.json")
    report = review.read(render/"검증기록"/"07_졸음운전_검증.json")
    if settings["lane_rule_version"]!=rule or settings["events"]!=report["events"]:
        raise ValueError("068 사건 기록과 설정을 확인하세요.")
    if report["mp4_sha256"]!=drowsy.digest(render/drowsy.NAME):
        raise ValueError("068 검증 후 영상이 변경되었습니다.")
    shutil.copyfile(render/drowsy.NAME,dest/"hud.mp4")
    shutil.copyfile(drowsy.SOURCE,dest/"original.mp4")
    rows=report["automatic_track_rows"]
    meta=dict(demo_title="회색 승용차 · 차선침범과 졸음운전 예측 시연",source_kind="recorded",
              source_sha256=settings["source_sha256"],video=settings["video"],selection_frame=1,
              end_frame=rows[-1]["frame"],analyzed_frames=len(rows),confirmed_frames=sum(bool(r["box"]) for r in rows),
              fps=report["encoded_video"]["fps"],events=settings["events"],event_counts=settings["counts"],
              event_total=len(settings["events"]),vehicle_info=settings["vehicle_info"],event_vocabulary=2,
              manual_prediction=settings["manual_prediction"],lane_rule_version=rule,playback_mode="prerendered")
    review.save(dest/"target.json",meta)
    write_rows(dest/"frames.jsonl",rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old",type=Path,default=mvp.OUTPUT/"demo_terms_20261130")
    parser.add_argument("--out",type=Path,default=mvp.OUTPUT/"demo_contact_v1")
    parser.add_argument("--drowsy",type=Path,default=review.ROOT/"output/mvp_review_contact/drowsy")
    args=parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    controlled=import_module("040_verify_lane_crossing_recovery_197").verify_contact_intervals()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=args.out.parent) as tmp:
        stage=Path(tmp)/"catalog"
        stage.mkdir()
        for old in sorted(args.old.iterdir()):
            if (old/"target.json").is_file():
                migrate(old,stage/old.name)
        register_drowsy(args.drowsy,stage/"drowsy-2")
        catalog=mvp.load_demos(stage)
        expected={p.name for p in args.old.iterdir() if (p/"target.json").is_file()} | {"drowsy-2"}
        if set(catalog)!=expected:
            raise ValueError("빠른 시연 목록이 불완전합니다.")
        review.save(stage/"검증결과.json",dict(controlled=controlled,
                    cached={k:d["event_counts"] for k,(_,d) in catalog.items()}))
        stage.rename(args.out)


if __name__=="__main__":
    main()
