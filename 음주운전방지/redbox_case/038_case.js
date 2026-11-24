/*
 * 038  사건 정보와 신고 초안 버튼 연결하기
 * 사용자가 고친 값을 그대로 복사하고 후보가 기록된 장면을 바로 찾게 합니다.
 * 로컬 서버의 /case-data.json과 HTML의 입력칸·재생기를 사용합니다.
 * 클립 탐색, 원본 저장, 항목 복사와 안전신문고 페이지 열기를 화면에 연결합니다.
 */

const video = document.querySelector("#clip");
const seekButton = document.querySelector("#jump");
const feedback = document.querySelector("#feedback");
let feedbackTimer;

function showFeedback(message, persistent = false) {
  clearTimeout(feedbackTimer);
  feedback.textContent = message;
  feedback.hidden = false;
  if (!persistent) feedbackTimer = setTimeout(() => { feedback.hidden = true; }, 2900);
}

function clipTime(seconds) {
  const centiseconds = Math.round(seconds * 100);
  const mins = Math.floor(centiseconds / 6000);
  const secs = (centiseconds % 6000) / 100;
  return `${String(mins).padStart(2, "0")}:${secs.toFixed(2).padStart(5, "0")}`;
}

function markUnconfirmed(field) {
  field.classList.toggle("needs-review", field.value.trim() === "확인 필요");
}

async function copyField(button) {
  const field = document.getElementById(button.dataset.copy);
  if (!field.value) {
    showFeedback("복사할 값을 입력하세요.");
    return;
  }
  try {
    // 화면에 현재 입력된 값을 복사하므로 사용자가 고친 내용도 반영됩니다.
    await navigator.clipboard.writeText(field.value);
    showFeedback(`${field.labels[0].textContent}을(를) 복사했습니다.`);
  } catch {
    field.focus();
    field.select();
    showFeedback("복사 권한이 없어 값을 선택했습니다. Ctrl+C로 복사하세요.");
  }
}

async function loadCase() {
  const response = await fetch("/case-data.json");
  if (!response.ok) throw new Error("사건 데이터를 읽지 못했습니다.");
  const data = await response.json();
  document.querySelector("#case-label").textContent = ["차선변경", "차선침범", "정지선 위반"].includes(data.label) ? data.label : "주행 기록";
  document.querySelector("#source-video").textContent = data.sourceVideo;
  document.querySelector("#original-time").textContent = `${data.originalTime.toFixed(2)}초`;
  document.querySelector("#track-id").textContent = `ID ${data.trackId}`;
  document.querySelector("#clip-time").textContent = clipTime(data.clipTime);
  document.querySelector("#clip-name").textContent = data.downloadName;
  document.querySelector("#clip-details").textContent =
    `원본 MP4 · ${data.clipDuration.toFixed(2)}초 · ${(data.sizeBytes / 1e6).toFixed(1)} MB`;

  for (const [id, value] of Object.entries(data.draft)) {
    const field = document.getElementById(id);
    field.value = value;
    markUnconfirmed(field);
    field.addEventListener("input", () => markUnconfirmed(field));
  }
  for (const button of document.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", () => copyField(button));
  }
  const save = document.querySelector("#save");
  save.download = data.downloadName;
  save.hidden = false;
  document.querySelector("#draft-fields").disabled = false;
  video.addEventListener("loadedmetadata", () => { seekButton.disabled = false; }, { once: true });
  video.addEventListener("error", () => showFeedback("클립을 재생할 수 없습니다. 영상 저장으로 원본을 열 수 있습니다.", true));
  seekButton.addEventListener("click", () => {
    video.currentTime = data.clipTime;
    showFeedback(`클립 ${clipTime(data.clipTime)} 위치로 이동했습니다.`);
  });
  video.poster = "/poster.jpg";
  video.src = "/clip.webm";
}

loadCase().catch(() => showFeedback("사건 데이터를 불러오지 못했습니다. 로컬 서버와 후보 파일을 확인하세요.", true));
