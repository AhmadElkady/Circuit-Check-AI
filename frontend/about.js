import { featuredId, inspectionData } from "./data.js";

const image = document.getElementById("about-image");
const status = document.getElementById("about-image-status");

try {
  const record = await inspectionData.get(featuredId);
  image.src = record.annotatedUrl;
  await image.decode();
  image.hidden = false;
  status.hidden = true;
} catch {
  status.textContent = "Sample image unavailable.";
}
