// 044 · 영상 시각과 선택 좌표를 서버에 전달하고 저장된 HUD와 사건을 재생합니다.
// 번호판 입력은 차량 선택과 분리해 나중에 음성 입력으로도 갱신할 수 있습니다.
const $ = id => document.getElementById(id);
const stage = $("preview");
const ctx = stage.getContext("2d");
const video = $("replay");
const state = { frame: null, image: null, selected: null, line: [], stopLine: [], boundaryMode: false, running: false, job: null, generation: 0 };

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
  $("stop-boundary").disabled = $("boundary").disabled;
  $("boundary").setAttribute("aria-pressed", String(state.boundaryMode === "line"));
  $("stop-boundary").setAttribute("aria-pressed", String(state.boundaryMode === "stopLine"));
  $("boundary").textContent = state.line.length === 4 ? "차선 경계 다시 지정" : "차선 경계 지정";
  $("stop-boundary").textContent = state.stopLine.length === 4 ? "정지선 다시 지정 · 실험" : "정지선 지정 · 실험";
  for (const id of ["source", "camera", "duration", "kind", "prev", "next", "timeline", "demo", "plate"]) {
    $(id).disabled = state.running || (!!state.job && ["prev", "next", "timeline"].includes(id));
  }
  $("fast-demo").disabled = state.running;
  $("camera").disabled ||= !/\.avi$/i.test($("source").value);
  $("vehicle-state").textContent = state.selected ? "타깃 지정됨" : "선택 대기";
}

let hudStyle;
function setCorners(info, verdict, prediction) {
  $("hud-color").textContent = info.color || "-";
  $("hud-type").textContent = info.vehicle_type || "-";
  $("preview-plate").textContent = info.plate || "차량번호: -";
  $("hud-brand").hidden = !("brand" in info || info.model_name);
  $("hud-brand").textContent = `브랜드 · 모델  ${info.brand || "-"} / ${info.model_name || "-"}`;
  $("hud-verdict").textContent = `판정: ${verdict || "-"}`;
  $("hud-prediction").textContent = `예측: ${prediction || "-"}`;
}
function previewPanels(visible) {
  $("preview-left").hidden = $("preview-right").hidden = !visible;
  const plate = state.selected && $("plate").value.trim();
  if (visible) setCorners({ plate });
  $("hud-event-lines").hidden = true;
}
$("plate").addEventListener("input", () => {
  if (!stage.hidden && state.image) previewPanels(true);
});

function drawSelection() {
  if (!state.image || !state.frame) return;
  const {width, height, boxes} = state.frame;
  ctx.drawImage(state.image, 0, 0, stage.width, stage.height);
  const sx = stage.width / width;
  const sy = stage.height / height;
  $("preview-time").textContent = clock(state.frame.at);
  $("preview-rec").hidden = false;
  previewPanels(true);
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
  for (const points of [state.line, state.stopLine]) {
    if (!points.length) continue;
    ctx.strokeStyle = ctx.fillStyle = "#50b7ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(points[0]*sx, points[1]*sy, 4, 0, 2*Math.PI);
    ctx.fill();
    if (points.length === 4) {
      ctx.beginPath();
      ctx.moveTo(points[0]*sx, points[1]*sy);
      ctx.lineTo(points[2]*sx, points[3]*sy);
      ctx.stroke();
    }
  }
}

function clearRun() {
  $("hud-fullscreen").hidden = true;
  video.pause();
  video.removeAttribute("src");
  video.load();
  video.hidden = true;
  stage.hidden = false;
  $("results").hidden = true;
  $("progress").hidden = true;
  $("progress-text").hidden = true;
  $("plate").value = "";
  state.job = null;
}

async function loadFrame(at) {
  if (state.running) return;
  if (state.job) clearRun();
  $("fast-demo").value = "";
  const generation = ++state.generation;
  state.frame = state.image = state.selected = null;
  $("preview-rec").hidden = true;
  previewPanels(false);
  state.line = [];
  state.stopLine = [];
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
  state.stopLine = [];
  message("선택한 차를 분석하거나, 차선 경계 또는 정지선 위에 두 점을 지정하세요.", "타깃 지정됨");
  refreshControls();
  drawSelection();
}

stage.addEventListener("click", event => {
  if (!state.frame || state.running) return;
  const rect = stage.getBoundingClientRect();
  const point = [(event.clientX-rect.left)*state.frame.width/rect.width, (event.clientY-rect.top)*state.frame.height/rect.height];
  if (!state.boundaryMode) { choose(point); return; }
  const isStop = state.boundaryMode === "stopLine";
  const points = state[state.boundaryMode];
  const dx = Math.abs(point[0]-points[0]), dy = Math.abs(point[1]-points[1]);
  if (points.length === 2 && (isStop ? dx<state.frame.width*25/960 || dy>dx*.50 : dx<8 || dy<10)) {
    if (isStop) { message("같은 흰 정지선 위에서 좌우로 떨어진 점을 찍으세요."); return; }
    message("같은 경계 위에서 가로·세로로 조금 더 떨어진 두 번째 점을 클릭하세요.");
    return;
  }
  points.push(...point);
  if (points.length === 4) state.boundaryMode = false;
  message(state.boundaryMode ? (isStop ? "같은 정지선의 반대쪽 점을 클릭하세요." : "같은 경계의 다른 높이에서 두 번째 점을 클릭하세요.")
    : (isStop ? "정지선이 지정됐습니다. 선택 차량 분석을 시작하세요." : "경계가 지정됐습니다. 선택 차량 분석을 시작하세요."));
  refreshControls();
  drawSelection();
});

function chooseBoundary(kind, prompt) {
  if (state.boundaryMode) state[state.boundaryMode] = [];
  state[kind] = [];
  state.boundaryMode = state.boundaryMode === kind ? false : kind;
  message(state.boundaryMode ? prompt : "선 지정을 취소했습니다.");
  refreshControls();
  drawSelection();
}
$("boundary").onclick = () => chooseBoundary("line", "따라볼 차선 경계 위에서 첫 점을 클릭하세요.");
$("stop-boundary").onclick = () => chooseBoundary("stopLine", "횡단보도 앞 흰 정지선의 한쪽 점을 클릭하세요.");

function startAt(name) {
  return ({"BB_20260111_125520.avi": 6.2, "BB_20261113_134044.avi": 6, "BB_20261113_141715.avi": 6,
    "BB_20261113_192304.avi": 12, "BB_20261122_141908.avi": 21, "BB_20261122_171859.avi": 25,
    "BB_20261122_172259.avi": 30.5, "BB_20261122_173905.avi": 27})[name] ?? 0;
}
function changeSource() {
  if (!$("source").value) return;
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
  $("result-info").textContent = `${info.color ?? "-"} · ${info.vehicle_type ?? "-"} · ${info.plate ?? "-"} · 추적 ${result.confirmed_frames}/${result.analyzed_frames}프레임`;
}

function showResult(job, result, cached = false) {
  const path = (cached ? "/demo-media/" : "/media/") + job;
  const start = (result.selection_frame-1)/result.fps;
  state.job = { id:job, result, start, domHud: !cached && !!result.hud_changes?.length };
  const currentJob = state.job;
  $("results").hidden = false;
  $("totals").hidden = true;
  $("total-count").textContent = "";
  $("event-types").hidden = true;
  $("events").replaceChildren();
  for (const event of result.events) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.textContent = `${clock(event.time_s)}  ${event.display_label ?? event.label}`;
    button.onclick = () => { video.currentTime = (event.frame - result.selection_frame + .35)/result.fps; };
    li.append(button);
    li.hidden = true;
    $("events").append(li);
  }
  $("mp4").href = path + "/hud.mp4";
  $("original").hidden = !cached;
  if (cached) $("original").href = path + "/original.mp4";
  $("save-plate").hidden = cached;
  if (cached) $("filename").textContent = result.demo_title;
  $("json").href = path + "/target.json";
  $("plate").value = result.vehicle_info.plate ?? "";
  resultInfo(result.vehicle_info, result);
  stage.hidden = true;
  $("preview-rec").hidden = true;
  previewPanels(false);
  video.hidden = false;
  $("hud-fullscreen").hidden = !currentJob.domHud;
  video.controlsList?.toggle("nofullscreen", currentJob.domHud);
  video.disablePictureInPicture = currentJob.domHud;
  video.src = path + (cached ? "/hud.mp4" : "/replay.webm");
  if (video.requestVideoFrameCallback) {
    const onFrame = (_, metadata) => {
      if (state.job !== currentJob) return;
      updatePlayback(metadata.mediaTime, true);
      video.requestVideoFrameCallback(onFrame);
    };
    video.requestVideoFrameCallback(onFrame);
  }
  updatePlayback(0);
  if (cached) {
    message("저장한 결과를 재생합니다. 이벤트를 누르면 해당 시각으로 이동합니다.", "빠른 시연");
    return;
  }
  message(result.stop_seed ? "정지선과 선택한 차량의 위치를 영상에서 확인하세요."
    : result.lane_status === "active" ? "영상 시각에 맞춰 HUD를 재생합니다. 이벤트를 누르면 해당 장면으로 이동합니다."
    : result.lane_status === "gpu_unavailable" ? "차량은 추적했고, GPU를 사용할 수 없어 차선 판정은 보류했습니다."
    : "차량 추적 결과입니다. 차선 집계를 하려면 다음 분석에서 경계를 지정하세요.", "분석 완료");
}

function updatePlayback(mediaTime, decodedFrame = false) {
  if (!state.job) return;
  const offset = mediaTime*state.job.result.fps;
  const frame = state.job.result.selection_frame + (decodedFrame ? Math.round(offset) : Math.floor(offset + 1e-6));
  const shownFrame = Math.min(frame, state.job.result.end_frame);
  const sourceTime = state.job.result.source_times?.[shownFrame - state.job.result.selection_frame];
  $("time-label").textContent = clock(sourceTime ?? (shownFrame-1)/state.job.result.fps);
  let count = 0;
  const counts = new Map();
  state.job.result.events.forEach((event, index) => {
    const passed = event.frame <= frame;
    $("events").children[index].hidden = !passed;
    if (passed) {
      count++;
      const label = event.display_label ?? event.label;
      counts.set(label, (counts.get(label) || 0) + 1);
    }
  });
  $("total-count").textContent = String(count);
  $("totals").hidden = count === 0;
  $("event-types").hidden = count === 0;
  // 같은 사건 목록에서 웹 패널과 결과 목록을 만듭니다. 재생·탐색 때 같은 프레임을 기준으로 합니다.
  if (state.job.domHud) {
    const change = state.job.result.hud_changes.findLast(item => item.frame <= shownFrame);
    if (change !== state.job.lastFields) {
      const fields = change?.fields ?? {};
      setCorners(fields.vehicle_info ?? {}, fields.verdict, fields.prediction);
      state.job.lastFields = change;
    }
    $("preview-left").hidden = $("preview-right").hidden = false;
  }
  // 같은 타깃의 사건은 시간순입니다. 같은 개수를 재생하는 동안에는 줄을 다시 만들지 않습니다.
  if (state.job.lastEventCount === count) return;
  state.job.lastEventCount = count;
  const lines = [...counts].map(([label, total]) => {
    const line = document.createElement("div");
    line.textContent = `${label}: ${total}회`;
    line.style.color = hudStyle.event_colors[label] ?? hudStyle.default_event_color;
    return line;
  });
  $("event-types").replaceChildren(...lines);
  if (state.job.domHud) {
    const copies = lines.map(line => line.cloneNode(true));
    if (copies.length) {
      const title = document.createElement("strong");
      title.textContent = "TOTAL  |  ";
      copies[0].prepend(title);
    }
    $("hud-event-lines").replaceChildren(...copies);
    $("hud-event-lines").hidden = !copies.length;
  }
}
$("hud-fullscreen").onclick = () => video.closest(".stage").requestFullscreen();
video.onloadedmetadata = () => {
  $("video-surface").style.setProperty("--video-ratio", String(video.videoWidth/video.videoHeight));
};
video.onseeked = () => updatePlayback(video.currentTime);
video.ontimeupdate = () => {
  if (!video.requestVideoFrameCallback || video.paused) updatePlayback(video.currentTime);
};
$("review-reset").onclick = () => {
  if ($("source").value) loadFrame(Number($("timeline").value));
  else {
    clearRun();
    $("fast-demo").value = "";
    message("실제로 분석할 원본을 선택하세요.", "선택 대기");
    refreshControls();
  }
};
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

const workStage = {
  preparing: "영상·모델 준비", analyzing: "프레임 분석", ocr: "번호판 OCR",
  encoding: "영상 인코딩 마무리", verifying: "저장 영상 검증",
  clips: "후보 근거 클립 저장", saving: "분석 JSON 저장", done: "분석 완료"
};

function showProgress(job) {
  $("progress").value = job.percent;
  const frames = job.total ? ` · ${job.frame}/${job.total} 프레임` : "";
  $("progress-text").textContent = `${job.percent}% · ${workStage[job.stage]}${frames}`;
}

$("analyze").onclick = async () => {
  if (!state.selected || !state.frame || state.running) return;
  if (state.boundaryMode) { message("선의 두 번째 점을 지정하거나 지정을 취소하세요."); return; }
  state.running = true;
  refreshControls();
  $("progress").hidden = false;
  $("progress-text").hidden = false;
  showProgress({percent: 0, stage: "preparing"});
  message("원본 프레임을 분석하고 HUD를 저장합니다.", "분석 중");
  try {
    const {job} = await api("/api/analyze", {
      video: $("source").value, at: state.frame.at, camera: $("camera").value,
      source_kind: $("kind").value, duration: Number($("duration").value),
      point: state.point, line: state.line.length === 4 ? state.line : null,
      stop_line: state.stopLine.length === 4 ? state.stopLine : null, plate: $("plate").value
    });
    for (;;) {
      await new Promise(resolve => setTimeout(resolve, 650));
      const current = await api("/api/jobs/" + job);
      if (current.state === "error") throw new Error(current.error);
      showProgress(current);
      if (current.state === "done") { showResult(job, current.result); break; }
    }
  } catch (error) {
    message(error.message, "분석 오류");
    $("progress").hidden = true;
    $("progress-text").textContent = "분석이 중단됐습니다.";
  } finally {
    state.running = false;
    refreshControls();
  }
};

$("fast-demo").onchange = async () => {
  const id = $("fast-demo").value;
  if (!id) return;
  const generation = ++state.generation;
  clearRun();
  state.frame = state.image = state.selected = null;
  state.boundaryMode = false;
  refreshControls();
  try {
    const result = await api("/api/demos/" + id);
    if (generation !== state.generation) return;
    showResult(id, result, true);
    refreshControls();
    video.play().catch(() => {});
  } catch (error) {
    if (generation === state.generation) message(error.message, "시연 오류");
  }
};

Promise.all([api("/api/videos"), api("/api/demos"), api("/api/hud-style")]).then(([files, demos, style]) => {
  hudStyle = style;
  document.documentElement.style.setProperty("--hud-background", `rgba(${style.panel_rgb.join(",")},${style.opacity})`);
  document.documentElement.style.setProperty("--hud-padding", `${style.padding}px`);
  $("source").add(new Option("분석할 원본 선택", ""));
  for (const name of files) $("source").add(new Option(name, name));
  for (const demo of demos) $("fast-demo").add(new Option(demo.title, demo.id));
  $("demo-picker").hidden = !demos.length;
  if (demos.length) message("빠른 시연을 고르거나 실제 분석에 사용할 원본을 선택하세요.", "선택 대기");
  else if (files.length) {
    $("source").value = files[0];
    changeSource();
  } else message("videos 폴더에 AVI 또는 MP4를 넣으세요.", "영상 없음");
}).catch(error => message(error.message, "연결 오류"));
