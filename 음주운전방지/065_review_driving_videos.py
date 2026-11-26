# 065  주행 영상 재검토. 원본별 지문과 표본을 저장하고 새 파일만 추가합니다.
# 비교 기준은 055 실험의 영상 목록입니다. 다음 066에서 채택한 구간을 실제 프레임에 그립니다.
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
VIDEOS = ROOT / "videos"
DEFAULT = ROOT / "output/mvp_review_20261126"
EXT = {".mp4",".avi",".mov",".mkv",".mts",".m4v",".ts",".wmv",".webm",".m2ts",".mpg",".mpeg",".3gp"}

def inventory(out):
    out.mkdir(exist_ok=True, parents=True)
    index = out / "inventory.json"
    old = json.loads(index.read_text(encoding="utf8")) if index.exists() else {}
    previous = {r["name"] for r in json.loads((ROOT/"output/lamp_cv/inventory.json").read_text(encoding="utf8"))}
    rows = {}
    scanned=[]
    sheets = out / "samples"
    sheets.mkdir(exist_ok=True)
    for path in sorted(VIDEOS.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXT:
            continue
        key = path.relative_to(VIDEOS).as_posix()
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        thumb = sheets/(digest+".jpg")
        if old.get(key,{}).get("sha256")==digest and thumb.exists():
            rows[key]=old[key]
            continue
        scanned.append(key)
        cap = cv2.VideoCapture(str(path))
        fps=cap.get(5)
        n=int(cap.get(7))
        row=dict(sha256=digest, size=path.stat().st_size, frames=n, fps=fps,
                 resolution=[int(cap.get(3)),int(cap.get(4))], previously_listed=key in previous,
                 source="로컬 블랙박스" if key.startswith("BB_") else "사용자 제공 · 원출처/이용 조건 미확인")
        frames = sorted({max(1,min(n,round(n*r))) for r in [.03,.17,.32,.47,.62,.77,.93]})
        tiles=[]
        try:
            for f in frames:
                cap.set(1,f-1)
                ok,im=cap.read()
                if not ok:
                    break
                tile=cv2.resize(im,(176,100))
                cv2.putText(tile,str(f),(2,97),0,.42,(255,255,255),1)
                tiles.append(tile)
        finally:
            cap.release()
        row["sample_frames"]=frames[:len(tiles)]
        row["status"]="표본 확인" if len(tiles)==len(frames) and fps>0 else "읽기 오류"
        if tiles:
            cv2.imencode(".jpg",np.hstack(tiles))[1].tofile(thumb)
        rows[key]=row
    tmp=index.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding="utf8")
    tmp.replace(index)
    for i in range(0,len(rows),7):
        tiles=[]
        for k,(key,r) in enumerate(list(rows.items())[i:i+7],i+1):
            photo=sheets/(r["sha256"]+".jpg")
            if not photo.exists():continue
            pic=cv2.imdecode(np.fromfile(photo,np.uint8),1)
            cv2.putText(pic,f"{k:02}",(5,23),0,.75,(0,250,255),2)
            tiles.append(pic)
        if tiles and len({a.shape for a in tiles})==1:
            cv2.imencode(".jpg",np.vstack(tiles))[1].tofile(out/f"sheet_{i+1:02}.jpg")
    notes_file=out/"review_notes.json"
    notes=json.loads(notes_file.read_text(encoding="utf8")) if notes_file.exists() else {}
    lines=["# 주행 영상 검토 목록","",
           "파일마다 전방 또는 기본 스트림의 일곱 시점을 열었습니다. 표본에서 보류한 행동은 전 구간에서 행동이 없었다는 뜻으로 사용하지 않습니다.",
           "온라인 자료는 사용자가 로컬 과제에 모두 활용 가능하다고 확인했습니다. 로컬 MP4의 원 게시자·URL·별도 라이선스는 미확인입니다.",
           "이전 055 목록과의 신규 비교는 상대 파일명을 기준으로 합니다. 이번부터 내용이 바뀐 파일은 SHA-256으로 구분합니다.","",
           "| 영상 | 길이(초) | 확인 프레임 | 이전 055 목록 | 결과 | 출처 |","|---|---:|---|---|---|---|"]
    for key,row in rows.items():
        verdict=notes.get(row["sha256"],"새 파일 · 표본 생성 후 사건·권리 확인 대기")
        seconds=row["frames"]/row["fps"] if row["fps"] else 0
        lines.append(f"| {key} | {seconds:.2f} | {row['sample_frames']} | {'기존' if row['previously_listed'] else '신규'} | {verdict} | {row['source']} |")
    (out/"영상별_검토.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    changes=dict(inspected=scanned,new_paths=sorted(set(rows)-set(old)),removed=sorted(set(old)-set(rows)),
                 changed=[k for k in scanned if k in old and old[k]["sha256"]!=rows[k]["sha256"]])
    (out/"last_scan.json").write_text(json.dumps(changes,ensure_ascii=False,indent=1),encoding="utf8")
    print(len(rows), "previously unlisted",sum(not r["previously_listed"] for r in rows.values()))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=DEFAULT)
    inventory(p.parse_args().output)

