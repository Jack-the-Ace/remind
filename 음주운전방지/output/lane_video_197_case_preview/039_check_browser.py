# 039  실제 브라우저에서 사건 화면 점검하기
# 파일 경로와 버튼이 연결됐는지 사용자 동작을 재현해 확인합니다.
# 프로젝트에서 Chrome, websocket 모듈, 후보 JSON과 원본 클립을 사용합니다.
# 재생·탐색·복사·다운로드를 검사하고 desktop.png와 mobile.png를 저장합니다.

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

import websocket

root = Path.cwd()
out = root / "output/lane_video_197_case_preview"
origin = "http://127.0.0.1:8766"
flags = subprocess.CREATE_NO_WINDOW
chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def read_json(url):
    return json.load(urlopen(url, timeout=3))


def until(predicate, timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(.15)
    raise RuntimeError("Timeout")


with tempfile.TemporaryDirectory(dir=out) as temp:
    profile = Path(temp) / "profile"
    downloads = Path(temp) / "downloads"
    server = subprocess.Popen([sys.executable, "035_serve_redbox_case.py", "--port", "8766"], creationflags=flags)
    chrome = None
    try:
        data = until(lambda: read_json(origin + "/case-data.json"))
        chrome = subprocess.Popen([chrome_path, "--headless=new", "--no-first-run",
                                   "--remote-allow-origins=http://localhost:9337", "--remote-debugging-port=9337",
                                   "--user-data-dir=" + str(profile), origin], creationflags=flags)
        targets = until(lambda: read_json("http://127.0.0.1:9337/json/list"))
        page = next(t for t in targets if t["type"] == "page")
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost:9337", timeout=8)
        counter = 0

        def call(method, params=None):
            global counter
            counter += 1
            ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
            while True:
                reply = json.loads(ws.recv())
                if reply.get("id") == counter:
                    if "error" in reply:
                        raise RuntimeError(reply["error"])
                    return reply["result"]

        def script(src):
            response = call("Runtime.evaluate", {"expression": src, "returnByValue": True,
                                                  "awaitPromise": True, "userGesture": True})
            if "exceptionDetails" in response:
                raise RuntimeError(response["exceptionDetails"])
            return response["result"].get("value")

        def viewport(width, height, mobile=False):
            call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                 "deviceScaleFactor": 1, "mobile": mobile})

        def screenshot(name):
            metrics = call("Page.getLayoutMetrics")["cssContentSize"]
            png = call("Page.captureScreenshot", {"captureBeyondViewport": True, "clip": {
                "x": 0, "y": 0, "width": metrics["width"], "height": metrics["height"], "scale": 1
            }})["data"]
            (out / f"{name}.png").write_bytes(base64.b64decode(png))

        viewport(1400, 900)
        until(lambda: script("document.querySelector('#clip')?.readyState >= 2"))
        assert script("document.querySelector('#clip-time').textContent") == "00:03.00"
        assert script("document.querySelector('#original-time').textContent") == "6.30초"
        assert script("document.querySelector('#track-id').textContent") == "ID 4"
        assert script("[...document.querySelectorAll('.field label,.field h3')].map(e=>e.textContent)") == [
            "신고 유형", "사진·동영상", "발생지역", "내용", "차량번호", "발생일자", "발생시각"
        ]
        assert script("['location','plate','incident-date','incident-time'].map(id=>document.getElementById(id).value)") == ["확인 필요"] * 4
        assert script("document.querySelectorAll('[data-copy]').length") == 6
        playback = script("""(async()=>{const v=document.querySelector('#clip');await v.play();
            await new Promise(r=>setTimeout(r,320));v.pause();return v.currentTime})()""")
        assert playback > .15
        jumped = script("""new Promise(resolve=>{const v=document.querySelector('#clip');
            v.addEventListener('seeked',()=>resolve(v.currentTime),{once:true});
            document.querySelector('#jump').click()})""")
        assert abs(jumped - 3) < .04
        print("browser playback, duration and seek", playback, script("document.querySelector('#clip').duration"), jumped, flush=True)
        script("document.querySelector('#feedback').hidden = true")
        screenshot("desktop")
        viewport(390, 844, True)
        assert script("document.documentElement.scrollWidth === innerWidth")
        screenshot("mobile")
        viewport(1400, 900)
        call("Browser.grantPermissions", {"origin": origin, "permissions": ["clipboardReadWrite","clipboardSanitizedWrite"]})
        clip = script("""(async()=>{document.querySelector('#description').value='검증용으로 수정한 문장';
            document.querySelector('[data-copy=description]').click();
            await new Promise(r=>setTimeout(r,200));return navigator.clipboard.readText()})()""")
        assert clip == "검증용으로 수정한 문장", clip
        assert script("document.querySelector('#feedback').textContent").endswith("복사했습니다.")
        for key in ("report-type", "location", "plate", "incident-date", "incident-time"):
            copied = script(f"""(async()=>{{const field=document.getElementById('{key}');
                field.value='수정 '+field.id;document.querySelector('[data-copy={key}]').click();
                await new Promise(r=>setTimeout(r,150));return navigator.clipboard.readText()}})()""")
            assert copied == "수정 " + key, copied
        print("edited values copied to clipboard for all six fields", flush=True)
        call("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
        script("document.querySelector('#save').click()")
        saved = until(lambda: (downloads / data["downloadName"]).is_file() and downloads / data["downloadName"])
        evidence = next(root.glob("output/lane_video_197_other_sources/uturn_paint_verified/original_clips/*.mp4"))
        assert hashlib.sha256(saved.read_bytes()).digest() == hashlib.sha256(evidence.read_bytes()).digest()
        print("download matches original SHA256", flush=True)
        url = script("document.querySelector('#open-report').href")
        assert url == "https://www.safetyreport.go.kr/html/portal/safereportn/safeReportn3.html"
        script("document.querySelector('#open-report').click()")
        external = until(lambda: next((x["url"] for x in read_json("http://127.0.0.1:9337/json/list")
                                       if x.get("url", "").startswith("https://www.safetyreport.go.kr/")), None))
        print("official portal opened in new tab", external, flush=True)
        ws.close()
    finally:
        if chrome is not None:
            chrome.terminate()
            chrome.wait(timeout=8)
        server.terminate()
        server.wait(timeout=8)
