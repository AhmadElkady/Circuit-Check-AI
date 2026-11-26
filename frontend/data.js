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
const api = new URL("../api/", import.meta.url);
const sampleRecords = new Map();
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

function readRecord(record) {
  if (!validReport(record?.report) || typeof record.id !== "string" || !record.id ||
      ![record.annotatedUrl, record.reportUrl, record.pdfUrl].every((url) => typeof url === "string" && url) ||
      (record.originalUrl !== null && (typeof record.originalUrl !== "string" || !record.originalUrl))) {
    return null;
  }
  return {
    ...record,
    filename: record.report.source_image.trim().split(/[\\/]/).pop(),
    timestamp: record.report.timestamp,
    sample: samples.has(record.id),
  };
}

async function loadCatalog() {
  const records = new Map();
  try {
    const response = await fetch(new URL("inspections", api), { cache: "no-store" });
    const catalog = response.ok ? await response.json() : null;
    if (Array.isArray(catalog?.records)) {
      for (const item of catalog.records) {
        const record = readRecord(item);
        if (record) records.set(record.id, record);
      }
      const featured = records.get(catalog.featuredId);
      if (featured) featured.sample = true;
      return { records, featured, available: true };
    }
  } catch {
    // Samples can also be served by a static HTTP server.
  }
  return { records, featured: null, available: false };
}

async function loadSample(id, sample) {
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
    sample: true,
  };
}

async function getSample(id, catalogAvailable) {
  if (!samples.has(id)) {
    throw new Error("This inspection could not be found.");
  }

  if (!sampleRecords.has(id)) {
    const record = loadSample(id, samples.get(id)).catch((error) => {
      sampleRecords.delete(id);
      throw error;
    });
    sampleRecords.set(id, record);
  }
  const record = await sampleRecords.get(id);
  const pdfUrl = catalogAvailable ? new URL(`reports/${id}.pdf`, api).href : null;
  return { ...record, pdfUrl };
}

async function get(id) {
  const catalog = await loadCatalog();
  const targetId = id || catalog.featured?.id || featuredId;
  return catalog.records.get(targetId) ?? getSample(targetId, catalog.available);
}

async function list() {
  const catalog = await loadCatalog();
  const archivedIds = [...samples.keys()].filter((id) => !catalog.records.has(id));
  const archived = await Promise.allSettled(archivedIds.map((id) => getSample(id, catalog.available)));
  const records = [...catalog.records.values(), ...archived.flatMap((result) =>
    result.status === "fulfilled" ? [result.value] : [])];
  return records.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
}

async function inspect(file) {
  const upload = new FormData();
  upload.append("image", file);
  const response = await fetch(new URL("inspect", api), {
    method: "POST",
    body: upload,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === "string"
      ? data.detail
      : "Inspection failed. Make sure the Python preview server is running.");
  }
  const record = readRecord(data);
  if (!record?.originalUrl) {
    throw new Error("The server returned an incomplete inspection.");
  }
  return record;
}

export const inspectionData = { get, list, inspect };
