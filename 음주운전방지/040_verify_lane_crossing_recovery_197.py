# 040  추적이 끊겼다 돌아오는 구간의 집계 확인
# 기존 선택 로그를 복사해 새 ID와 추적 공백을 만들고 034의 MP4와 프레임 로그를 검사합니다.
# --baseline은 기존 006 선택 로그 폴더, --output은 이번 검증에 사용할 새 폴더입니다.
# 수정한 로그로 재현한 결과와 원본 추적 로그의 재실행 결과를 summary.json에 남깁니다.

"""006에서 저장한 추적 로그로 034의 복귀·보류·중복 집계를 확인합니다."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
BASELINE = ROOT / "output/lane_video_197_selected_20261120"
DAY = ROOT / "videos/비접촉_사고유발_영상_낮.mp4"
NIGHT = ROOT / "videos/비접촉_사고유발_영상_밤.mp4"
RECOVERY_HOLD = "crossing_unobserved_during_tracking_gap"


def verify_contact_intervals():
    """상자 하단과 경계의 위치만 통제하고, 실제 분석에 쓰는 집계기를 그대로 실행합니다."""
    from importlib import import_module
    lane = import_module("034_detect_lane_crossing_197")
    # L/R은 차체 전체가 경계 왼쪽/오른쪽, C는 하단이 걸친 상태입니다.
    cases = [
        ("연속 3초", "L"+"C"*91, [46, 91]),
        ("짧은 접촉 세 번", "L"+("C"*12+"L")*3, [13, 26, 39]),
        ("3초 후 복귀 두 번", "L"+("C"*90+"L")*2, [46, 91, 137, 182]),
        ("첫 장부터 연속 6초", "C"*181, [45, 90, 135, 180]),
        ("정확히 1.5초 후 복귀", "L"+"C"*45+"L", [46]),
        ("2초 후 복귀 두 번", "L"+("C"*60+"L")*2, [46, 107]),
        ("공백 전후 시간 분리", "L"+"C"*31+"?"+"C"*46, [78]),
        ("공백 건너 복귀", "L"+"C"*20+"?L", []),
        ("반대 차로 유지", "L"+"C"*6+"R"*40, []),
    ]
    results = []
    for name, positions, expected in cases:
        rows=[]
        for index, pos in enumerate(positions):
            box = {"L":[0,10,9,20],"C":[5,10,15,20],"R":[13,10,23,20],"?":None}[pos]
            rows.append(dict(frame=index+1,seconds=4+index/30,box=box,boundary=[[10,0],[10,25]],
                             status="observed" if box else "tracking_hold",track_id=2 if index<30 else 58))
        events=lane.analyze_contact_rows(rows,30)
        recorded=[e for e in events if e["label"]=="차선침범"]
        assert [e["frame"]-1 for e in recorded]==expected, (name, events)
        assert all(abs(e["time_s"]-(4+i/30))<1e-7 for e,i in zip(recorded,expected))
        if name=="반대 차로 유지":
            assert [e["label"] for e in events]==["차선변경"]
        results.append(dict(case=name,expected=len(expected),actual=len(recorded),frames=[i+1 for i in expected]))
    # VFR에서 프레임 수와 시각이 어긋날 때도 실제 PTS가 1.5초를 지난 첫 프레임에 표시합니다.
    state=lane.LaneBehavior(30)
    found=[]
    for n in range(41):
        found.extend(state.update(n+1, n*.041, "contact"))
    assert len(found)==1 and found[0]["time_s"]==1.5 and found[0]["frame"]==38
    return results


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_fixture(source, destination, first, last, final, new_id):
    data = load_json(source)
    data["frames"] = data["frames"][:final]
    for row in data["frames"][first - 1:]:
        if row["status"] != "confirmed":
            continue
        lost = row["frame"] <= last
        new = None if lost else new_id
        # 차선 모델 입력은 원본 영상입니다. 선택 상자의 추적 ID와 확정 상태만 바꿉니다.
        for vehicle in row["vehicles"]:
            if vehicle["id"] == row["id"] and vehicle["box"] == row["box"]:
                vehicle["id"] = new
        row["id"] = new
        if lost:
            row.update(status="tracking_hold", box=None)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(data, stream)
    return destination


def run_case(name, video, track, start, output, end=None, seed=None):
    destination = output / name
    command = [
        sys.executable, "-B", str(ROOT / "034_detect_lane_crossing_197.py"),
        "--video", str(video), "--selected-track", str(track),
        "--start-frame", str(start), "--output", str(destination),
    ]
    if end is not None:
        command.extend(["--end-frame", str(end)])
    if seed is not None:
        command.extend(["--seed-line", *map(str, seed)])
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    events = load_json(destination / "candidates.json")
    rows = [json.loads(line) for line in (destination / "frames.jsonl").read_text(encoding="utf-8").splitlines()]
    return events, {row["frame"]: row for row in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, out = args.baseline.resolve(), args.output.resolve()
    suv, white, night = (base / f"{name}_selected.json" for name in ("day_suv", "day_white", "night"))
    out.mkdir(parents=True, exist_ok=False)
    fixture_dir = out / "fixtures"
    fixture_dir.mkdir()
    # 공백을 넣는 프레임과 각 경우에 예상하는 후보 기록 프레임을 아래에 적습니다.
    scenarios = [
        ("01_new_id_then_cross", suv, 204, 208, 270, 10072, 185, [245]),
        ("02_opposite_after_gap", suv, 225, 239, 270, 10072, 185, []),
        ("03_return_after_count", suv, 251, 256, 280, 10072, 185, [245]),
        ("04_other_vehicle_crosses", white, 340, 354, 359, 10109, 224, []),
    ]
    jobs = {}
    expected = {}
    holes = {}
    for name, source, first, last, final, new_id, start, frames in scenarios:
        track = make_fixture(source, fixture_dir / f"{name}.json", first, last, final, new_id)
        jobs[name] = (DAY, track, start, out)
        expected[name] = frames
        holes[name] = (first, last, new_id)

    jobs.update(actual_day_suv=(DAY, suv, 185, out), actual_day_white=(DAY, white, 224, out),
                actual_night=(NIGHT, night, 510, out, 585, (1080, 620, 1345, 800)))
    expected.update(actual_day_suv=[245, 353], actual_day_white=[], actual_night=[])
    # 둘씩 재생해 검증 시간을 줄이고 한 번에 너무 많은 GPU 모델을 올리지 않습니다.
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {name: pool.submit(run_case, name, *job) for name, job in jobs.items()}
        results = {name: future.result() for name, future in pending.items()}
    summary = {}
    for name, (events, rows) in results.items():
        event_frames = [event["frame"] for event in events]
        assert event_frames == expected[name], (name, event_frames, expected[name])
        for event in events:
            end = event["frame"]
            begin = event["first_confirmable_opposite_frame"]
            assert end - begin + 1 == 6
            assert all(rows[f]["side"] == event["to_side"] for f in range(begin, end + 1))
        for frame in range(2, len(rows) + 1):
            assert rows[frame]["count"] - rows[frame - 1]["count"] == (frame in event_frames)
        if name in holes:
            first, last, new_id = holes[name]
            for frame in range(first, last + 1):
                row = rows[frame]
                assert row["status"] == "tracking_hold"
                assert row["target_id"] is None and row["stable_side"] is None
            assert rows[last + 1]["target_id"] == new_id
        summary[name] = dict(expected=expected[name], actual=event_frames, count=len(events),
                             recovery_hold_frames=[f for f, row in rows.items() if row["status"] == RECOVERY_HOLD])

    name = "01_new_id_then_cross"
    event = results[name][0][0]
    assert event["track_id"] == 10072 and event["last_origin_frame"] > holes[name][1]
    name = "02_opposite_after_gap"
    rows = results[name][1]
    assert summary[name]["recovery_hold_frames"] == list(range(240, 246))
    assert rows[239]["stable_side"] is None and rows[245]["stable_side"] == "left"
    assert rows[246]["status"] == "observed"
    name = "03_return_after_count"
    rows = results[name][1]
    assert rows[250]["count"] == rows[251]["count"] == rows[257]["count"] == rows[280]["count"] == 1
    assert not summary[name]["recovery_hold_frames"]
    name = "04_other_vehicle_crosses"
    other = load_json(jobs[name][1])["frames"][352]["vehicles"]
    assert any(vehicle["id"] == 72 for vehicle in other)
    assert results["actual_day_suv"][1][353]["count"] == 2
    assert all(results["actual_night"][1][f]["status"] == "tracking_hold" for f in range(529, 560))

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    (out / "summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
