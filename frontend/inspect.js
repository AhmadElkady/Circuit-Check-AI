import { featuredId, inspectionData } from "./data.js";

const byId = (id) => document.getElementById(id);
const fileInput = byId("pcb-file");
const chooseImage = byId("choose-image");
const openSample = byId("open-sample");
const download = byId("download-report");
const error = byId("inspection-error");
const syncZoom = byId("sync-zoom");
const zoom = byId("zoom-level");
const fitBoard = byId("fit-board");
const findings = byId("findings");
const previous = byId("previous-finding");
const next = byId("next-finding");
const highlight = byId("active-box");
const map = byId("board-map");
const mapMarkers = byId("map-markers");
const runButton = byId("run-inspection");
const verdictTones = { PASS: [523.25, 698.46], FAIL: [293.66, 196] };
const fit = { x: 0.5, y: 0.5, zoom: 1 };

const original = {
  stage: byId("original-stage"),
  layer: byId("original-layer"),
  image: byId("original-image"),
  empty: byId("original-empty"),
  board: null,
  view: { ...fit },
};
const analysis = {
  stage: byId("analysis-stage"),
  layer: byId("analysis-layer"),
  image: byId("annotated-image"),
  empty: byId("analysis-empty"),
  board: null,
  view: { ...fit },
};

let revision = 0;
let objectUrl = null;
let entries = [];
let active = -1;
let audioContext;
let cueGain;
let uploadedFile = null;
let running = false;
let readingUpload = false;

function notify(message = "") {
  error.textContent = message;
  error.hidden = !message;
}

async function readImage(url) {
  const image = new Image();
  image.src = url;
  await image.decode();
  return { url, width: image.naturalWidth, height: image.naturalHeight };
}

function setBoard(pane, board) {
  pane.board = board;
  pane.view = { ...fit };
  pane.layer.hidden = !board;
  pane.empty.hidden = Boolean(board);
  if (board) {
    pane.image.src = board.url;
    pane.layer.style.width = board.width + "px";
    pane.layer.style.height = board.height + "px";
  } else {
    pane.image.removeAttribute("src");
  }
}

function setFileLabel(filename, canReplace) {
  const name = byId("file-name");
  name.textContent = filename;
  name.title = filename;
  chooseImage.textContent = canReplace ? "Replace image" : "Choose image";
}

function clearObjectUrl() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
}

function recordInUrl(id) {
  const url = new URL(location.href);
  url.searchParams.delete("new");
  if (id) {
    url.searchParams.set("inspection", id);
  } else {
    url.searchParams.delete("inspection");
    url.searchParams.set("new", "1");
  }
  history.replaceState(null, "", url);
}

function prepareControls() {
  const originalUnavailable = Boolean(analysis.board && !original.board);
  byId("original-message").textContent = originalUnavailable ? "Original image unavailable" : "Drop a PCB image here";
  byId("original-hint").hidden = originalUnavailable;
  byId("original-placeholder-icon").hidden = originalUnavailable;
  updateRunButton();
  syncZoom.disabled = !(original.board && analysis.board);
  syncZoom.checked = !syncZoom.disabled;
  zoom.disabled = !original.board && !analysis.board;
  fitBoard.disabled = zoom.disabled;
  zoom.value = "1";
  byId("finding-zoom").hidden = true;
}

function findingNumber(index) {
  return String(index + 1).padStart(2, "0");
}

function displayName(value) {
  const name = value.replaceAll("_", " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function updateFindingNavigation() {
  previous.disabled = active <= 0;
  next.disabled = active >= entries.length - 1;
  byId("finding-position").textContent = active >= 0
    ? (active + 1) + " of " + entries.length
    : entries.length + (entries.length === 1 ? " finding" : " findings");
}

function renderFindings(report) {
  entries = [
    ...report.defects.map((item) => ({ ...item, kind: "confirmed" })),
    ...report.review_candidates.map((item) => ({ ...item, kind: "review" })),
  ];
  active = -1;
  findings.replaceChildren();
  mapMarkers.replaceChildren();

  entries.forEach((entry, index) => {
    const row = document.createElement("li");
    const button = document.createElement("button");
    const badge = entry.kind === "review" ? "Review" : displayName(entry.severity);
    button.type = "button";
    button.className = "finding-row";
    button.dataset.kind = entry.kind;
    button.dataset.severity = entry.severity;
    button.setAttribute("aria-pressed", "false");
    button.title = displayName(entry.severity) + " · " + (entry.confidence * 100).toFixed(1) + "% confidence";
    for (const [className, content] of [
      ["finding-number", findingNumber(index)],
      ["finding-name", displayName(entry.class_name)],
      ["finding-badge", badge],
    ]) {
      const span = document.createElement("span");
      span.className = className;
      span.textContent = content;
      button.append(span);
    }
    button.addEventListener("click", () => chooseFinding(index));
    row.append(button);
    findings.append(row);
    const marker = document.createElement("span");
    marker.className = "map-marker";
    marker.textContent = findingNumber(index);
    const box = entry.bounding_box;
    marker.style.left = ((box.x1 + box.x2) / 2 / analysis.board.width) * 100 + "%";
    marker.style.top = ((box.y1 + box.y2) / 2 / analysis.board.height) * 100 + "%";
    mapMarkers.append(marker);
  });

  byId("no-findings").hidden = entries.length > 0;
  byId("finding-nav").hidden = !entries.length;
  updateFindingNavigation();
}

function silenceVerdictCue() {
  cueGain?.disconnect();
  cueGain = null;
}

function unlockAudio() {
  if (!window.AudioContext) return;
  try {
    audioContext ??= new AudioContext();
    return audioContext.state === "running" ? Promise.resolve() : audioContext.resume().catch(() => {});
  } catch {
    // Audio availability never changes the inspection result.
  }
}

function playVerdictCue(status) {
  silenceVerdictCue();
  const notes = verdictTones[status];
  if (!notes || audioContext?.state !== "running") return;

  let gain;
  try {
    gain = audioContext.createGain();
    cueGain = gain;
    gain.connect(audioContext.destination);

    const tone = audioContext.createOscillator();
    tone.type = "sine";
    tone.connect(gain);
    const start = audioContext.currentTime + .01;
    notes.forEach((frequency, index) => {
      const time = start + index * .13;
      tone.frequency.setValueAtTime(frequency, time);
      gain.gain.setValueAtTime(.0001, time);
      gain.gain.exponentialRampToValueAtTime(.065, time + .018);
      gain.gain.exponentialRampToValueAtTime(.0001, time + .12);
    });
    tone.addEventListener("ended", () => {
      if (cueGain === gain) silenceVerdictCue();
    }, { once: true });
    tone.start(start);
    tone.stop(start + .26);
  } catch {
    if (cueGain === gain) silenceVerdictCue();
  }
}

function renderVerdictBadge(badge, status, feedback = false) {
  badge.classList.remove("is-feedback");
  badge.textContent = status;
  badge.dataset.status = status;
  if (!feedback) return;

  // A repeat inspection can return the same verdict.
  void badge.offsetWidth;
  badge.classList.add("is-feedback");
}

function renderVerdict(record, { feedback = false, sample = true } = {}) {
  const verdict = byId("verdict");
  const confirmed = byId("confirmed-total");
  const { status, total_defects, total_review_candidates } = record.report.inspection;
  confirmed.textContent = total_defects + (total_defects === 1 ? " confirmed defect" : " confirmed defects");
  confirmed.dataset.status = status;
  byId("review-total").textContent = total_review_candidates +
    (total_review_candidates === 1 ? " review candidate" : " review candidates");

  byId("verdict-empty").hidden = true;
  byId("verdict-results").hidden = false;
  byId("sample-tag").hidden = !sample;
  download.href = record.reportUrl;
  download.download = record.id + ".json";
  download.hidden = false;
  renderFindings(record.report);
  renderVerdictBadge(verdict, status, feedback);
}

async function showInspection(id) {
  const request = ++revision;
  notify();
  running = false;
  readingUpload = false;
  silenceVerdictCue();
  openSample.setAttribute("aria-busy", "true");
  updateRunButton();
  try {
    const record = await inspectionData.get(id);
    const annotatedBoard = await readImage(record.annotatedUrl);
    const originalBoard = record.originalUrl ? await readImage(record.originalUrl).catch(() => null) : null;
    if (request !== revision) return;

    clearObjectUrl();
    uploadedFile = null;
    setFileLabel(record.filename, true);
    setBoard(original, originalBoard);
    setBoard(analysis, annotatedBoard);
    byId("map-image").src = annotatedBoard.url;
    prepareControls();
    renderVerdict(record);
    recordInUrl(record.id);
    draw();
  } catch (problem) {
    if (request === revision) notify(problem.message || "Could not open the sample inspection.");
  } finally {
    if (request === revision) {
      openSample.removeAttribute("aria-busy");
      updateRunButton();
    }
  }
}

function clearInspection() {
  entries = [];
  active = -1;
  setBoard(analysis, null);
  byId("map-image").removeAttribute("src");
  findings.replaceChildren();
  mapMarkers.replaceChildren();
  byId("verdict-empty").hidden = false;
  byId("verdict-results").hidden = true;
  byId("sample-tag").hidden = true;
  download.hidden = true;
  download.removeAttribute("href");
}

async function showUpload(file) {
  if (!file) return;
  if (!/\.(jpe?g|png)$/i.test(file.name) ||
      (file.type && !["image/jpeg", "image/png"].includes(file.type))) {
    notify("Unsupported file type. Choose a JPG or PNG image.");
    return;
  }
  const request = ++revision;
  openSample.removeAttribute("aria-busy");
  running = false;
  readingUpload = true;
  silenceVerdictCue();
  updateRunButton();
  notify();
  const url = URL.createObjectURL(file);
  try {
    const signature = new Uint8Array(await file.slice(0, 8).arrayBuffer());
    const png = [137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => signature[index] === value);
    const jpg = signature[0] === 255 && signature[1] === 216 && signature[2] === 255;
    if (!png && !jpg) throw new Error("Invalid image signature");
    const board = await readImage(url);
    if (request !== revision) return;
    clearObjectUrl();
    objectUrl = url;
    uploadedFile = file;
    setFileLabel(file.name, true);
    setBoard(original, board);
    clearInspection();
    prepareControls();
    recordInUrl(null);
    draw();
  } catch {
    if (request === revision) notify("Could not read this image. Choose a valid JPG or PNG.");
  } finally {
    if (objectUrl !== url) URL.revokeObjectURL(url);
    if (request === revision) {
      readingUpload = false;
      updateRunButton();
    }
  }
}

function updateRunButton() {
  runButton.disabled = !uploadedFile || readingUpload || running || openSample.hasAttribute("aria-busy");
  runButton.textContent = running ? "Running inspection…" : "Run inspection";
  byId("live-explanation").textContent = uploadedFile ? "" : "Upload a PCB photo to run an inspection.";
}

async function runInspection() {
  if (runButton.disabled) return;
  const audioReady = unlockAudio();
  silenceVerdictCue();
  const request = ++revision;
  const source = original.board;
  running = true;
  notify();
  clearInspection();
  prepareControls();
  draw();
  try {
    const record = await inspectionData.inspect(uploadedFile);
    const annotatedBoard = await readImage(record.annotatedUrl);
    if (request !== revision) return;
    setBoard(original, source);
    setBoard(analysis, annotatedBoard);
    byId("map-image").src = annotatedBoard.url;
    prepareControls();
    renderVerdict(record, { feedback: true, sample: false });
    void audioReady?.then(() => {
      if (request === revision) playVerdictCue(record.report.inspection.status);
    });
    draw();
  } catch (problem) {
    if (request === revision) notify(problem.message || "Could not run inspection.");
  } finally {
    if (request === revision) {
      running = false;
      updateRunButton();
    }
  }
}

function fitScale(pane) {
  return Math.min(pane.stage.clientWidth / pane.board.width, pane.stage.clientHeight / pane.board.height);
}

function chooseFinding(index) {
  if (!analysis.board || index < 0 || index >= entries.length) return;
  const fit = fitScale(analysis);
  if (fit <= 0) return;
  active = index;
  const { x1, y1, x2, y2 } = entries[index].bounding_box;
  const board = analysis.board;
  // Keep the surrounding PCB visible and limit pixel enlargement in this automatic view.
  const detailZoom = Math.min(
    2.7,
    1.35 / fit,
    analysis.stage.clientWidth / (1.6 * (x2 - x1) * fit),
    analysis.stage.clientHeight / (1.6 * (y2 - y1) * fit),
  );

  analysis.view = {
    x: (x1 + x2) / 2 / board.width,
    y: (y1 + y2) / 2 / board.height,
    zoom: Math.max(1, detailZoom),
  };
  if (syncZoom.checked) original.view = { ...analysis.view };
  byId("finding-zoom").hidden = false;
  zoom.value = "detail";

  Array.from(findings.children).forEach((row, position) => {
    row.firstElementChild.setAttribute("aria-pressed", String(position === active));
    mapMarkers.children[position].classList.toggle("is-active", position === active);
  });
  updateFindingNavigation();
  if (findings.scrollHeight > findings.clientHeight) {
    const row = findings.children[index].getBoundingClientRect();
    const list = findings.getBoundingClientRect();
    if (row.top < list.top + 4) findings.scrollTop += row.top - list.top - 4;
    else if (row.bottom > list.bottom - 4) findings.scrollTop += row.bottom - list.bottom + 4;
  }
  draw();
}

function offset(frame, extent, focus) {
  if (extent <= frame) return (frame - extent) / 2;
  return Math.min(0, Math.max(frame - extent, frame / 2 - extent * focus));
}

function drawPane(pane) {
  if (!pane.board) return null;
  const width = pane.stage.clientWidth;
  const height = pane.stage.clientHeight;
  const scale = fitScale(pane) * pane.view.zoom;
  const x = offset(width, pane.board.width * scale, pane.view.x);
  const y = offset(height, pane.board.height * scale, pane.view.y);
  pane.layer.style.transform = "translate(" + x + "px, " + y + "px) scale(" + scale + ")";
  return { width, height, x, y, scale };
}

function draw() {
  drawPane(original);
  const view = drawPane(analysis);
  highlight.hidden = !view || active < 0;
  map.hidden = !view;
  if (!view) return;
  const { width, height, x, y, scale } = view;
  if (!highlight.hidden) {
    const { x1, y1, x2, y2 } = entries[active].bounding_box;
    highlight.style.left = x + x1 * scale + "px";
    highlight.style.top = y + y1 * scale + "px";
    highlight.style.width = (x2 - x1) * scale + "px";
    highlight.style.height = (y2 - y1) * scale + "px";
    byId("active-box-label").textContent = findingNumber(active);
  }
  if (!map.hidden) {
    const imageWidth = analysis.board.width * scale;
    const imageHeight = analysis.board.height * scale;
    const indicator = byId("map-view");
    indicator.style.left = Math.max(0, -x / imageWidth) * 100 + "%";
    indicator.style.top = Math.max(0, -y / imageHeight) * 100 + "%";
    indicator.style.width = Math.min(1, width / imageWidth) * 100 + "%";
    indicator.style.height = Math.min(1, height / imageHeight) * 100 + "%";
  }
}

function resetZoom() {
  original.view = { ...fit };
  analysis.view = { ...fit };
  zoom.value = "1";
  draw();
}

chooseImage.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  showUpload(fileInput.files[0]);
  fileInput.value = "";
});
for (const target of [original.stage, byId("file-control")]) {
  target.addEventListener("dragover", (event) => {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    target.classList.add("is-dragging");
  });
  target.addEventListener("dragleave", (event) => {
    if (!target.contains(event.relatedTarget)) target.classList.remove("is-dragging");
  });
  target.addEventListener("drop", (event) => {
    event.preventDefault();
    target.classList.remove("is-dragging");
    if (event.dataTransfer.files.length > 1) {
      notify("Choose one image at a time.");
    } else {
      showUpload(event.dataTransfer.files[0]);
    }
  });
}
openSample.addEventListener("click", () => showInspection(featuredId));
previous.addEventListener("click", () => chooseFinding(active - 1));
next.addEventListener("click", () => chooseFinding(active + 1));
fitBoard.addEventListener("click", resetZoom);
zoom.addEventListener("change", () => {
  if (zoom.value === "1") {
    resetZoom();
  } else if (zoom.value === "detail") {
    chooseFinding(active);
  } else {
    const pane = analysis.board ? analysis : original;
    pane.view.zoom = Number(zoom.value);
    if (syncZoom.checked) original.view = { ...analysis.view };
    draw();
  }
});
syncZoom.addEventListener("change", () => {
  if (syncZoom.checked) original.view = { ...analysis.view };
  draw();
});
const resize = new ResizeObserver(draw);
resize.observe(original.stage);
resize.observe(analysis.stage);

window.addEventListener("pagehide", silenceVerdictCue);
runButton.addEventListener("click", runInspection);

const params = new URLSearchParams(location.search);
if (params.has("inspection") || !params.has("new")) {
  showInspection(params.get("inspection") || featuredId);
}
