export const featuredId = "board_A_20261125_220215_796447";

// A static host cannot enumerate outputs. List the checked-in report/image
// stems here and add original only when an exact source image is known.
const samples = new Map([
  ["board_A_20261125_220646_256013", {}],
  [featuredId, {}],
  ["board_A_20261125_203307_941974", {}],
  ["board_A_20261125_202605_644903", {}],
  ["board_A_20261125_202333_613422", {}],
]);

const outputs = new URL("../outputs/", import.meta.url);
const records = new Map();
const verdicts = new Set(["PASS", "FAIL", "REVIEW"]);

function validFinding(finding) {
  const box = finding?.bounding_box;
  return Boolean(
    box &&
      typeof finding.class_name === "string" &&
      typeof finding.severity === "string" &&
      Number.isFinite(finding.confidence) &&
      [box.x1, box.y1, box.x2, box.y2].every(Number.isFinite) &&
      box.x2 > box.x1 &&
      box.y2 > box.y1,
  );
}

function validReport(report) {
  const inspection = report?.inspection;
  return Boolean(
    inspection &&
      verdicts.has(inspection.status) &&
      typeof report.source_image === "string" &&
      report.source_image.trim() &&
      typeof report.timestamp === "string" &&
      Number.isFinite(Date.parse(report.timestamp)) &&
      Array.isArray(report.defects) &&
      report.defects.length === inspection.total_defects &&
      report.defects.every(validFinding) &&
      Array.isArray(report.review_candidates) &&
      report.review_candidates.length === inspection.total_review_candidates &&
      report.review_candidates.every(validFinding),
  );
}

async function loadRecord(id, sample) {
  const reportUrl = new URL(`reports/${id}.json`, outputs).href;
  const annotatedUrl = new URL(`annotated/${id}.png`, outputs).href;
  const [reportResponse, imageResponse] = await Promise.all([
    fetch(reportUrl),
    fetch(annotatedUrl, { method: "HEAD" }),
  ]).catch(() => {
    throw new Error("Could not load the sample. Serve the frontend from the repository root and try again.");
  });

  if (!reportResponse.ok) {
    throw new Error("The report for this sample inspection is unavailable.");
  }

  if (!imageResponse.ok || !imageResponse.headers.get("content-type")?.startsWith("image/")) {
    throw new Error("The annotated image for this sample inspection is unavailable.");
  }

  const report = await reportResponse.json().catch(() => {
    throw new Error("The saved inspection report could not be read.");
  });
  if (!validReport(report)) {
    throw new Error("The saved inspection report contains incomplete inspection data.");
  }

  return {
    id,
    filename: report.source_image.trim().split(/[\\/]/).pop(),
    timestamp: report.timestamp,
    report,
    reportUrl,
    annotatedUrl,
    originalUrl: sample.original ? new URL(sample.original, outputs).href : null,
  };
}

async function get(id) {
  if (!samples.has(id)) {
    throw new Error("This sample inspection could not be found.");
  }

  if (!records.has(id)) {
    const record = loadRecord(id, samples.get(id)).catch((error) => {
      records.delete(id);
      throw error;
    });
    records.set(id, record);
  }

  return records.get(id);
}

async function list() {
  const results = await Promise.allSettled([...samples.keys()].map(get));
  return results.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));
}

async function inspect(file) {
  const upload = new FormData();
  upload.append("image", file);
  const response = await fetch(new URL("../api/inspect", import.meta.url), {
    method: "POST",
    body: upload,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === "string"
      ? data.detail
      : "Inspection failed. Make sure the Python preview server is running.");
  }
  if (!validReport(data?.report) || !data.annotatedImage?.startsWith("data:image/png;base64,")) {
    throw new Error("The server returned an incomplete inspection.");
  }
  return {
    id: file.name.replace(/\.[^.]+$/, "") + "-inspection",
    filename: file.name,
    report: data.report,
    annotatedUrl: data.annotatedImage,
    reportUrl: "data:application/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data.report, null, 2)),
  };
}

export const inspectionData = { get, list, inspect };
