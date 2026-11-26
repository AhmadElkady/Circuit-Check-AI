import { inspectionData } from "./data.js";

const byId = (id) => document.getElementById(id);
const table = byId("history-table");
const rows = byId("history-rows");
const search = byId("filename-search");
const filter = byId("verdict-filter");
const preview = byId("history-image");
const previewStatus = byId("preview-status");
const openInspection = byId("open-inspection");
const download = byId("history-download");
const reset = byId("reset-filters");
const params = new URLSearchParams(location.search);

let records = [];
let visibleRecords = [];
let selectedId = params.get("inspection");
search.value = params.get("q") ?? "";
filter.value = params.get("verdict") ?? "";
if (filter.selectedIndex === -1) filter.value = "";

function updateUrl(record) {
  const url = new URL(location.href);
  for (const [key, value] of [
    ["q", search.value.trim()],
    ["verdict", filter.value],
    ["inspection", record?.id],
  ]) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  history.replaceState(null, "", url);
}

function showSelected(record) {
  selectedId = record?.id;
  for (const row of rows.rows) {
    const selected = row.dataset.id === selectedId;
    row.classList.toggle("is-selected", selected);
    row.querySelector("button").setAttribute("aria-pressed", String(selected));
  }

  byId("preview-actions").hidden = !record;
  byId("preview-heading").textContent = record?.filename ?? "Inspection preview";
  if (record) {
    preview.src = record.annotatedUrl;
    preview.hidden = false;
    previewStatus.hidden = true;
    const url = new URL("./index.html", location.href);
    url.searchParams.set("inspection", record.id);
    openInspection.href = url.href;
    if (record.pdfUrl) download.href = record.pdfUrl;
    else download.removeAttribute("href");
    download.download = record.id + ".pdf";
    download.hidden = !record.pdfUrl;
  } else {
    preview.removeAttribute("src");
    preview.hidden = true;
    previewStatus.textContent = "Select an inspection to preview its board.";
    previewStatus.hidden = false;
    openInspection.removeAttribute("href");
    download.removeAttribute("href");
  }
  updateUrl(record);
}

function makeRow(record) {
  const row = document.createElement("tr");
  row.dataset.id = record.id;
  const file = row.insertCell();
  const button = document.createElement("button");
  button.className = "history-file";
  button.type = "button";
  button.setAttribute("aria-pressed", "false");
  button.title = record.id;
  const icon = document.createElement("span");
  icon.className = "icon icon-image";
  icon.setAttribute("aria-hidden", "true");
  const label = document.createElement("span");
  label.className = "history-file-label";
  const filename = document.createElement("span");
  filename.textContent = record.filename;
  const reportName = document.createElement("small");
  reportName.textContent = record.id;
  label.append(filename, reportName);
  button.append(icon, label);
  file.append(button);

  const time = document.createElement("time");
  time.dateTime = record.timestamp;
  time.textContent = record.timestamp.replace("T", " ").slice(0, 16);
  row.insertCell().append(time);

  const inspection = record.report.inspection;
  const badge = document.createElement("strong");
  badge.className = "verdict";
  badge.dataset.status = inspection.status;
  badge.textContent = inspection.status;
  row.insertCell().append(badge);

  row.insertCell().textContent = inspection.total_defects;
  return row;
}

function renderHistory() {
  const query = search.value.toLowerCase().trim();
  visibleRecords = records.filter((record) => {
    const searchable = [record.filename, record.id + ".json", record.id + ".png", record.id + ".pdf"].join(" ").toLowerCase();
    return searchable.includes(query) && (!filter.value || record.report.inspection.status === filter.value);
  });
  rows.replaceChildren(...visibleRecords.map(makeRow));
  const noResults = visibleRecords.length === 0;
  table.hidden = noResults;
  byId("history-empty").hidden = !noResults;
  byId("history-status").textContent = records.length
    ? "No inspections match your filters."
    : "No saved report and annotated image pairs are available.";
  reset.hidden = !(records.length && (query || filter.value));
  showSelected(visibleRecords.find((record) => record.id === selectedId) ?? visibleRecords[0]);
}

rows.addEventListener("click", (event) => {
  const row = event.target.closest("tr");
  const record = visibleRecords.find((item) => item.id === row?.dataset.id);
  if (record) showSelected(record);
});
reset.addEventListener("click", () => {
  search.value = "";
  filter.value = "";
  renderHistory();
  search.focus();
});
preview.addEventListener("error", () => {
  preview.hidden = true;
  previewStatus.textContent = "The annotated preview could not be loaded.";
  previewStatus.hidden = false;
});

records = await inspectionData.list();
search.addEventListener("input", renderHistory);
filter.addEventListener("change", renderHistory);
renderHistory();
