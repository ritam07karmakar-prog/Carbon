const $ = (id) => document.getElementById(id);

const video = $("video");
const canvas = $("canvas");
const cameraPlaceholder = $("camera-placeholder");
const preview = $("preview");
const previewContainer = $("preview-container");
const fileInput = $("file-input");
const startCameraBtn = $("start-camera");
const captureBtn = $("capture-btn");
const uploadBtn = $("upload-btn");
const retakeBtn = $("retake-btn");
const latInput = $("lat-input");
const lonInput = $("lon-input");
const detectLocationBtn = $("detect-location");
const calibrationInput = $("calibration-input");
const analyzeBtn = $("analyze-btn");
const loading = $("loading");
const locationSection = $("location-section");
const resultsSection = $("results-section");
const newTestBtn = $("new-test-btn");
const downloadReportBtn = $("download-report-btn");

let capturedBlob = null;
let stream = null;

function show(el) { el.style.display = ""; }
function hide(el) { el.style.display = "none"; }

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    video.srcObject = stream;
    hide(cameraPlaceholder);
    show(video);
    captureBtn.disabled = false;
    hide(startCameraBtn);
  } catch (e) {
    alert("Camera access denied. Use upload instead.");
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
  hide(video);
  show(cameraPlaceholder);
  captureBtn.disabled = true;
  show(startCameraBtn);
}

function capturePhoto() {
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  canvas.toBlob((blob) => {
    capturedBlob = blob;
    preview.src = URL.createObjectURL(blob);
    show(previewContainer);
    stopCamera();
    show(locationSection);
    analyzeBtn.disabled = false;
  }, "image/jpeg", 0.9);
}

function handleFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  capturedBlob = file;
  preview.src = URL.createObjectURL(file);
  show(previewContainer);
  show(locationSection);
  analyzeBtn.disabled = false;
}

startCameraBtn.addEventListener("click", startCamera);
captureBtn.addEventListener("click", capturePhoto);
uploadBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", handleFileUpload);

retakeBtn.addEventListener("click", () => {
  capturedBlob = null;
  hide(previewContainer);
  hide(resultsSection);
  hide(locationSection);
  analyzeBtn.disabled = true;
  show(startCameraBtn);
});

detectLocationBtn.addEventListener("click", () => {
  if (!navigator.geolocation) {
    alert("Geolocation not supported on this device.");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      latInput.value = pos.coords.latitude.toFixed(4);
      lonInput.value = pos.coords.longitude.toFixed(4);
    },
    () => alert("Could not detect location. Enter manually.")
  );
});

analyzeBtn.addEventListener("click", async () => {
  if (!capturedBlob) return;
  hide(resultsSection);
  show(loading);
  analyzeBtn.disabled = true;

  const form = new FormData();
  form.append("image", capturedBlob, "soil.jpg");
  if (latInput.value) form.append("lat", parseFloat(latInput.value));
  if (lonInput.value) form.append("lon", parseFloat(lonInput.value));
  form.append("calibration", parseFloat(calibrationInput.value) || 1.0);

  try {
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).error || "Server error");
    const data = await res.json();
    renderResults(data);
    show(resultsSection);
    resultsSection.scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    alert("Analysis failed: " + e.message);
  } finally {
    hide(loading);
    analyzeBtn.disabled = false;
  }
});

function renderResults(data) {
  const a = data.analysis;

  $("som-value").textContent = a.som_percent + "%";
  $("som-rating").textContent = a.som_rating;
  $("carbon-value").textContent = a.carbon_stock_percent + "%";
  $("co2-value").textContent = a.co2e_per_ha_estimate + " t/ha";
  $("moisture-value").textContent = a.moisture_index.toFixed(2);
  $("moisture-label").textContent = a.moisture_index > 0.6 ? "Moist" : a.moisture_index > 0.3 ? "Moderate" : "Dry";
  $("texture-value").textContent = a.texture_roughness.toFixed(2);
  $("biomass-value").textContent = a.biomass_metrics.ndi_index.toFixed(3);

  const cm = a.color_metrics;
  const colorPanel = $("color-metrics");
  const colorBars = $("color-bars");
  show(colorPanel);
  colorBars.innerHTML = [
    { label: "Red", val: cm.mean_bgr.r, max: 255, color: "#e76f51" },
    { label: "Green", val: cm.mean_bgr.g, max: 255, color: "#2d6a4f" },
    { label: "Blue", val: cm.mean_bgr.b, max: 255, color: "#219ebc" },
    { label: "Darkness", val: cm.darkness_index * 100, max: 100, color: "#5e3c28" },
  ].map(
    (c) =>
      `<div class="color-bar-item">
        <div class="color-bar-label">${c.label}</div>
        <div class="color-bar-track"><div class="color-bar-fill" style="width:${(c.val / c.max) * 100}%;background:${c.color}"></div></div>
        <div style="font-size:0.75rem">${c.val.toFixed(c.val > 10 ? 0 : 2)}</div>
      </div>`
  ).join("");

  const sat = data.satellite;
  const satPanel = $("satellite-panel");
  const satData = $("satellite-data");
  if (sat && sat.mean_temp_c != null) {
    show(satPanel);
    satData.innerHTML = `
      <strong>Source:</strong> ${sat.data_source || "ERA5/NASA"}<br/>
      <strong>Mean Temp:</strong> ${sat.mean_temp_c} &deg;C<br/>
      <strong>Precipitation:</strong> ${sat.mean_precipitation_mm ?? "N/A"} mm<br/>
      <strong>Soil Moisture:</strong> ${sat.mean_soil_moisture ?? sat.mean_profile_moisture ?? "N/A"}<br/>
      <strong>Confidence:</strong> ${sat.confidence}
    `;
  } else {
    hide(satPanel);
  }

  const bio = data.biome;
  const bioPanel = $("biome-panel");
  const bioData = $("biome-data");
  if (bio) {
    show(bioPanel);
    bioData.innerHTML = `
      <strong>Biome:</strong> ${bio.biome.replace("_", " ")}<br/>
      <strong>Regional Avg SOM:</strong> ${bio.avg_som}%<br/>
      <strong>Deviation:</strong> ${(a.som_percent - bio.avg_som) > 0 ? "+" : ""}${(a.som_percent - bio.avg_som).toFixed(2)}%
    `;
  } else {
    hide(bioPanel);
  }
}

newTestBtn.addEventListener("click", () => {
  capturedBlob = null;
  hide(resultsSection);
  hide(locationSection);
  hide(previewContainer);
  analyzeBtn.disabled = true;
  show(startCameraBtn);
});

downloadReportBtn.addEventListener("click", () => {
  const som = $("som-value").textContent;
  const carbon = $("carbon-value").textContent;
  const co2 = $("co2-value").textContent;
  const moisture = $("moisture-value").textContent;
  const lines = [
    "========================================",
    "  SoilSense - Carbon Verification Report",
    "========================================",
    "",
    `Soil Organic Matter: ${som}`,
    `Carbon Stock: ${carbon}`,
    `CO2e per Hectare: ${co2}`,
    `Moisture Index: ${moisture}`,
    `Texture Roughness: ${$("texture-value").textContent}`,
    `Biomass NDI: ${$("biomass-value").textContent}`,
    "",
    `Date: ${new Date().toISOString().split("T")[0]}`,
    `Lat: ${latInput.value || "N/A"}  Lon: ${lonInput.value || "N/A"}`,
    "",
    "Powered by SoilSense (opencv + satellite verification)",
    "========================================",
  ].join("\n");
  const blob = new Blob([lines], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `soilsense-report-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
});
