// 044 · 영상 시각과 선택 좌표를 서버에 전달하고 저장된 HUD와 사건을 재생합니다.
// 번호판 입력은 차량 선택과 분리해 나중에 음성 입력으로도 갱신할 수 있습니다.
const $ = id => document.getElementById(id);
const stage = $("preview");
const ctx = stage.getContext("2d");
const video = $("replay");
const floatingEvent = $("event-float");
const floatingSeconds = 1.2;
const state = { frame: null, image: null, selected: null, line: [], boundaryMode: false, running: false, job: null, generation: 0 };

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error ?? "요청을 처리하지 못했습니다.");
  return result;
}

function clock(t) {
  const hundredths = Math.max(0, Math.round(t * 100));
  return String(Math.floor(hundredths / 6000)).padStart(2, "0") + ":" +
    ((hundredths % 6000) / 100).toFixed(2).padStart(5, "0");
}

function message(text, status) {
  $("instruction").textContent = text;
  if (status) $("stage-status").textContent = status;
}

function refreshControls() {
  $("analyze").disabled = state.running || !state.selected || !!state.job;
  $("boundary").disabled = state.running || !state.selected || !!state.job;
  $("boundary").setAttribute("aria-pressed", String(state.boundaryMode));
  $("boundary").textContent = state.line.length === 4 ? "차선 경계 다시 지정" : "차선 경계 지정";
  for (const id of ["source", "camera", "duration", "kind", "prev", "next", "timeline", "demo", "plate"]) {
    $(id).disabled = state.running || (!!state.job && ["prev", "next", "timeline"].includes(id));
  }
  $("camera").disabled ||= !/\.avi$/i.test($("source").value);
  $("vehicle-state").textContent = state.selected ? "타깃 지정됨" : "선택 대기";
}

function drawSelection() {
  if (!state.image || !state.frame) return;
  const {width, height, boxes} = state.frame;
  ctx.drawImage(state.image, 0, 0, stage.width, stage.height);
  const sx = stage.width / width;
  const sy = stage.height / height;
  $("preview-time").textContent = clock(state.frame.at);
  $("preview-rec").hidden = false;
  for (const box of state.selected ? [state.selected] : boxes) {
    const [x, y, a, b] = box;
    ctx.lineWidth = state.selected ? 2 : 1.5;
    ctx.strokeStyle = state.selected ? "#ff374d" : "#50b7ff";
    ctx.strokeRect(x*sx, y*sy, (a-x)*sx, (b-y)*sy);
    if (state.selected) {
      const center = (x+a)*sx/2;
      ctx.fillStyle = "#ff374d";
      ctx.beginPath();
      const markerY = Math.max(10, y*sy-5);
      ctx.moveTo(center-7, markerY-10);
      ctx.lineTo(center+7, markerY-10);
      ctx.lineTo(center, markerY);
      ctx.fill();
    }
  }
  if (state.line.length) {
    ctx.strokeStyle = ctx.fillStyle = "#50b7ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(state.line[0]*sx, state.line[1]*sy, 4, 0, 2*Math.PI);
    ctx.fill();
    if (state.line.length === 4) {
      ctx.beginPath();
      ctx.moveTo(state.line[0]*sx, state.line[1]*sy);
      ctx.lineTo(state.line[2]*sx, state.line[3]*sy);
      ctx.stroke();
    }
  }
}

function clearRun() {
  video.pause();
  video.removeAttribute("src");
  video.load();
  video.hidden = true;
  floatingEvent.hidden = true;
  stage.hidden = false;
  $("results").hidden = true;
  $("plate").value = "";
  state.job = null;
}

async function loadFrame(at) {
  if (state.running) return;
  if (state.job) clearRun();
  const generation = ++state.generation;
  state.frame = state.image = state.selected = null;
  $("preview-rec").hidden = true;
  state.line = [];
  state.boundaryMode = false;
  stage.style.opacity = ".45";
  $("filename").textContent = $("source").value;
  refreshControls();
  message("차량 상자를 찾고 있습니다.", "미리보기");
  try {
    const data = await api("/api/preview", { video: $("source").value, at, camera: $("camera").value });
    const image = new Image();
    image.src = "data:image/jpeg;base64," + data.image;
    await image.decode();
    if (generation !== state.generation) return;
    state.frame = data;
    state.image = image;
    stage.height = Math.round(stage.width * data.height / data.width);
    stage.style.opacity = "1";
    $("timeline").max = Math.max(0, data.duration - .10);
    $("timeline").value = data.at;
    $("time-label").textContent = clock(data.at);
    message(data.boxes.length ? "영상에서 분석할 차량을 클릭하세요." : "이 프레임에 선택할 차량이 없습니다. 다른 시각을 확인하세요.", "선택 대기");
    drawSelection();
  } catch (error) {
    if (generation === state.generation) message(error.message, "미리보기 오류");
  }
}

function choose(point) {
  const candidate = state.frame.boxes.filter(([x,y,a,b]) => x<=point[0] && point[0]<=a && y<=point[1] && point[1]<=b)
    .sort((a,b) => (a[2]-a[0])*(a[3]-a[1]) - (b[2]-b[0])*(b[3]-b[1]))[0];
  if (!candidate) { message("차량 상자 안쪽을 클릭하세요."); return; }
  state.selected = candidate;
  state.point = point;
  state.line = [];
  message("선택한 차를 분석하거나, 차선 경계 위에 두 점을 지정하세요.", "타깃 지정됨");
  refreshControls();
  drawSelection();
}

stage.addEventListener("click", event => {
  if (!state.frame || state.running) return;
  const rect = stage.getBoundingClientRect();
  const point = [(event.clientX-rect.left)*state.frame.width/rect.width, (event.clientY-rect.top)*state.frame.height/rect.height];
  if (!state.boundaryMode) { choose(point); return; }
  if (state.line.length === 2 && (Math.abs(point[0]-state.line[0])<8 || Math.abs(point[1]-state.line[1])<10)) {
    message("같은 경계 위에서 가로·세로로 조금 더 떨어진 두 번째 점을 클릭하세요.");
    return;
  }
  state.line.push(...point);
  state.boundaryMode = state.line.length < 4;
  message(state.boundaryMode ? "같은 경계의 다른 높이에서 두 번째 점을 클릭하세요." : "경계가 지정됐습니다. 선택 차량 분석을 시작하세요.");
  refreshControls();
  drawSelection();
});

$("boundary").onclick = () => {
  state.line = [];
  state.boundaryMode = !state.boundaryMode;
  message(state.boundaryMode ? "따라볼 차선 경계 위에서 첫 점을 클릭하세요." : "경계 지정을 취소했습니다.");
  refreshControls();
  drawSelection();
};

function startAt(name) {
  return ({"BB_20260111_125520.avi": 6.2, "BB_20261113_134044.avi": 6, "BB_20261113_141715.avi": 6,
    "BB_20261113_192304.avi": 12, "BB_20261122_141908.avi": 21, "BB_20261122_171859.avi": 25,
    "BB_20261122_172259.avi": 30.5, "BB_20261122_173905.avi": 27})[name] ?? 0;
}
function changeSource() {
  $("camera").value = $("source").value === "BB_20261113_134044.avi" ? "rear" : "front";
  loadFrame(startAt($("source").value));
}
$("source").onchange = changeSource;
$("camera").onchange = () => loadFrame(Number($("timeline").value));
$("timeline").oninput = () => $("time-label").textContent = clock(Number($("timeline").value));
$("timeline").onchange = () => loadFrame(Number($("timeline").value));
function step(delta) {
  loadFrame(Math.min(Number($("timeline").max), Math.max(0, Number($("timeline").value) + delta)));
}
$("prev").onclick = () => step(-1);
$("next").onclick = () => step(1);
$("demo").onclick = async () => {
  const sample = "비접촉_사고유발_영상_낮.mp4";
  if (![...$("source").options].some(option => option.value === sample)) return;
  $("source").value = sample;
  $("camera").value = "front";
  $("duration").value = "7";
  await loadFrame(184/30);
  if (!state.frame) return;
  choose([1408,503]);
  if (state.selected) {
    state.line = [770,340,1140,637];
    drawSelection();
    message("검증 영상의 검은 SUV와 흰 점선이 지정됐습니다. 분석을 시작하세요.");
  }
};

function resultInfo(info, result) {
  const label = info.plate_source === "manual" ? "직접 입력" : info.plate_source === "ocr_candidate" ? "OCR 후보" : "확인 필요";
  $("result-info").textContent = `${info.color ?? "-"} · ${info.vehicle_type ?? "-"} · ${info.plate ?? "-"} (${label}) · 추적 ${result.confirmed_frames}/${result.analyzed_frames}프레임`;
}

function showResult(job, result) {
  const path = "/media/" + job;
  const start = (result.selection_frame-1)/result.fps;
  state.job = { id:job, result, start };
  $("results").hidden = false;
  $("totals").hidden = true;
  $("total-count").textContent = "";
  $("events").replaceChildren();
  for (const event of result.events) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.textContent = `${clock(event.time_s)}  ${event.label}`;
    button.onclick = () => { video.currentTime = Math.max(0, event.time_s - start + .35/result.fps); };
    li.append(button);
    li.hidden = true;
    $("events").append(li);
  }
  $("mp4").href = path + "/hud.mp4";
  $("json").href = path + "/target.json";
  $("plate").value = result.vehicle_info.plate ?? "";
  resultInfo(result.vehicle_info, result);
  stage.hidden = true;
  $("preview-rec").hidden = true;
  floatingEvent.hidden = true;
  video.hidden = false;
  video.src = path + "/replay.webm";
  if (video.requestVideoFrameCallback) {
    const onFrame = (_, metadata) => {
      if (state.job?.id !== job) return;
      updatePlayback(metadata.mediaTime, true);
      video.requestVideoFrameCallback(onFrame);
    };
    video.requestVideoFrameCallback(onFrame);
  }
  message(result.lane_status === "active" ? "영상 시각에 맞춰 HUD를 재생합니다. 이벤트를 누르면 해당 장면으로 이동합니다."
    : result.lane_status === "gpu_unavailable" ? "차량은 추적했고, GPU를 사용할 수 없어 차선 판정은 보류했습니다."
    : "차량 추적 결과입니다. 차선 집계를 하려면 다음 분석에서 경계를 지정하세요.", "분석 완료");
}

function updatePlayback(mediaTime, decodedFrame = false) {
  if (!state.job) return;
  const offset = mediaTime*state.job.result.fps;
  const frame = state.job.result.selection_frame + (decodedFrame ? Math.round(offset) : Math.floor(offset + .025));
  const shownFrame = Math.min(frame, state.job.result.end_frame);
  $("time-label").textContent = clock((shownFrame-1)/state.job.result.fps);
  let count = 0;
  let latest = null;
  state.job.result.events.forEach((event, index) => {
    const passed = event.frame <= frame;
    $("events").children[index].hidden = !passed;
    if (passed) {
      count++;
      latest = event;
    }
  });
  $("total-count").textContent = String(count);
  $("totals").hidden = count === 0;
  // 영상 시간에서 진행률을 구해 일시정지하거나 되감아도 글자가 같은 위치에 뜹니다.
  const elapsed = latest ? mediaTime - (latest.frame-state.job.result.selection_frame) / state.job.result.fps : floatingSeconds;
  const phase = elapsed / floatingSeconds;
  const anchor = latest?.hud_anchor;
  floatingEvent.hidden = !anchor || phase < -.025 || phase >= 1;
  if (!floatingEvent.hidden) {
    const progress = Math.max(0, phase);
    floatingEvent.textContent = `+ ${latest.label} 1`;
    floatingEvent.dataset.align = anchor.align;
    floatingEvent.style.left = `${anchor.x*100}%`;
    floatingEvent.style.top = `${anchor.y*100}%`;
    floatingEvent.style.setProperty("--rise", `${progress*-1.65}em`);
    floatingEvent.style.opacity = String(1-progress**2);
  }
}
video.ontimeupdate = () => {
  if (!video.requestVideoFrameCallback || video.paused) updatePlayback(video.currentTime);
};
$("review-reset").onclick = () => loadFrame(Number($("timeline").value));
$("save-plate").onclick = async () => {
  const job = state.job;
  if (!job) return;
  try {
    const info = await api("/api/jobs/" + job.id + "/plate", { plate: $("plate").value });
    if (state.job !== job) return;
    resultInfo(info, job.result);
    message("차량번호를 JSON에 저장했습니다. 이미 생성한 MP4에는 분석 당시 값이 표시됩니다.");
  } catch (error) { message(error.message); }
};

$("analyze").onclick = async () => {
  if (!state.selected || !state.frame || state.running) return;
  if (state.boundaryMode) { message("차선 경계의 두 번째 점을 지정하거나 경계 지정을 취소하세요."); return; }
  state.running = true;
  refreshControls();
  $("progress").hidden = false;
  $("progress").value = 0;
  message("원본 프레임을 분석하고 HUD를 저장합니다.", "분석 중");
  try {
    const {job} = await api("/api/analyze", {
      video: $("source").value, at: state.frame.at, camera: $("camera").value,
      source_kind: $("kind").value, duration: Number($("duration").value),
      point: state.point, line: state.line.length === 4 ? state.line : null, plate: $("plate").value
    });
    for (;;) {
      await new Promise(resolve => setTimeout(resolve, 650));
      const current = await api("/api/jobs/" + job);
      if (current.state === "error") throw new Error(current.error);
      if (current.state === "done") { showResult(job, current.result); break; }
      if (current.total) $("progress").value = 100 * current.frame / current.total;
    }
  } catch (error) {
    message(error.message, "분석 오류");
  } finally {
    state.running = false;
    $("progress").hidden = true;
    refreshControls();
  }
};

api("/api/videos").then(files => {
  for (const name of files) $("source").add(new Option(name, name));
  if (files.length) changeSource();
  else message("videos 폴더에 AVI 또는 MP4를 넣으세요.", "영상 없음");
}).catch(error => message(error.message, "연결 오류"));
