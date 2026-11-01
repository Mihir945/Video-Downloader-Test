/**
 * Video Downloader - Frontend JavaScript
 * Connects with FastAPI backend, polls real backend progress,
 * and handles UI state updates and actual file transfer to the client.
 */

// Configure Backend API base URL
// Automatically detects if running on backend origin or standalone server (e.g. Live Server)
const getApiBase = () => {
  if (window.location.origin && window.location.origin !== "null" && !window.location.origin.startsWith("file:")) {
    if (window.location.port === "8000") {
      return "";
    }
    const host = window.location.hostname || "127.0.0.1";
    return `${window.location.protocol}//${host}:8000`;
  }
  return "http://127.0.0.1:8000";
};
const API_BASE = getApiBase();

// DOM Elements
const alertBox = document.getElementById("alertBox");
const fetchForm = document.getElementById("fetchForm");
const videoUrlInput = document.getElementById("videoUrl");
const fetchBtn = document.getElementById("fetchBtn");
const fetchBtnText = fetchBtn.querySelector(".btn-text");
const fetchBtnSpinner = fetchBtn.querySelector(".btn-spinner");

const previewCard = document.getElementById("previewCard");
const videoThumbnail = document.getElementById("videoThumbnail");
const videoDuration = document.getElementById("videoDuration");
const videoTitle = document.getElementById("videoTitle");
const videoUploader = document.getElementById("videoUploader");
const qualitySelect = document.getElementById("qualitySelect");
const downloadBtn = document.getElementById("downloadBtn");

const progressSection = document.getElementById("progressSection");
const statusLabel = document.getElementById("statusLabel");
const progressPercent = document.getElementById("progressPercent");
const progressBar = document.getElementById("progressBar");
const downloadAction = document.getElementById("downloadAction");
const manualDownloadLink = document.getElementById("manualDownloadLink");

// Application State
let currentVideoData = null;
let activePollInterval = null;
let activeBlobUrl = null;

/**
 * Display an error or info message in the UI alert box.
 */
function showAlert(message, type = "danger") {
  alertBox.textContent = message;
  alertBox.className = `alert alert-${type}`;
  alertBox.classList.remove("hidden");
}

/**
 * Hide the alert box.
 */
function hideAlert() {
  alertBox.classList.add("hidden");
  alertBox.textContent = "";
}

/**
 * Update the UI state of the Fetch Video button.
 */
function setFetchLoading(isLoading) {
  fetchBtn.disabled = isLoading;
  if (isLoading) {
    fetchBtnText.textContent = "Fetching...";
    fetchBtnSpinner.classList.remove("hidden");
  } else {
    fetchBtnText.textContent = "Fetch Video";
    fetchBtnSpinner.classList.add("hidden");
  }
}

/**
 * Reset and clear any existing progress polling and file states.
 */
function resetProgressTracking() {
  if (activePollInterval) {
    clearInterval(activePollInterval);
    activePollInterval = null;
  }
  if (activeBlobUrl) {
    try {
      window.URL.revokeObjectURL(activeBlobUrl);
    } catch (_) {}
    activeBlobUrl = null;
  }
  progressBar.style.width = "0%";
  progressPercent.textContent = "0%";
  statusLabel.textContent = "Initializing...";
  downloadAction.classList.add("hidden");
}

/**
 * Handle form submission to fetch video information.
 */
fetchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideAlert();
  resetProgressTracking();

  const url = videoUrlInput.value.trim();
  if (!url) {
    showAlert("Please enter a valid video URL.", "danger");
    return;
  }

  setFetchLoading(true);
  previewCard.classList.add("hidden");
  progressSection.classList.add("hidden");

  try {
    const response = await fetch(`${API_BASE}/fetch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Failed to fetch video details.");
    }

    // Populate video metadata
    currentVideoData = data;
    videoTitle.textContent = data.title;
    videoUploader.textContent = `Published by ${data.uploader}`;
    videoDuration.textContent = data.duration_formatted;
    videoThumbnail.src = data.thumbnail || "";
    videoThumbnail.alt = data.title;

    // Populate format dropdown
    qualitySelect.innerHTML = "";
    if (data.formats && data.formats.length > 0) {
      data.formats.forEach((fmt) => {
        const option = document.createElement("option");
        option.value = fmt.format_id;
        option.textContent = fmt.label;
        qualitySelect.appendChild(option);
      });
    } else {
      const option = document.createElement("option");
      option.value = "best";
      option.textContent = "Best Available Quality (MP4)";
      qualitySelect.appendChild(option);
    }

    // Show preview card
    previewCard.classList.remove("hidden");
  } catch (err) {
    console.error("Fetch error:", err);
    showAlert(err.message || "Network error. Please ensure the backend server is running.", "danger");
  } finally {
    setFetchLoading(false);
  }
});

/**
 * Trigger download and begin polling backend progress.
 */
downloadBtn.addEventListener("click", async () => {
  if (!currentVideoData || !currentVideoData.url) {
    showAlert("No video selected for download.", "danger");
    return;
  }

  hideAlert();
  resetProgressTracking();

  const selectedFormatId = qualitySelect.value;
  downloadBtn.disabled = true;
  qualitySelect.disabled = true;
  progressSection.classList.remove("hidden");
  statusLabel.textContent = "Requesting download from server...";

  try {
    const response = await fetch(`${API_BASE}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: currentVideoData.url,
        format_id: selectedFormatId
      })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Failed to initiate download.");
    }

    const downloadId = data.download_id;
    startProgressPolling(downloadId);

  } catch (err) {
    console.error("Download trigger error:", err);
    showAlert(err.message || "Failed to start download.", "danger");
    downloadBtn.disabled = false;
    qualitySelect.disabled = false;
    progressSection.classList.add("hidden");
  }
});

/**
 * Poll the backend periodically for real download and FFmpeg merging progress.
 */
function startProgressPolling(downloadId) {
  let failureCount = 0;

  activePollInterval = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE}/progress/${downloadId}`);
      if (!response.ok) {
        throw new Error("Unable to read progress status from server.");
      }

      const info = await response.json();
      failureCount = 0; // Reset network failure count

      const status = info.status;
      const progress = Math.min(Math.max(info.progress || 0, 0), 99);

      if (status === "downloading") {
        // Real stream download progress from yt-dlp
        progressBar.style.width = `${progress}%`;
        progressPercent.textContent = `${Math.round(progress)}%`;
        statusLabel.textContent = `Downloading stream: ${progress.toFixed(1)}%`;

      } else if (status === "merging") {
        // FFmpeg postprocessing and merging
        progressBar.style.width = "96%";
        progressPercent.textContent = "96%";
        statusLabel.textContent = "Merging video & audio with FFmpeg into MP4...";

      } else if (status === "completed") {
        // Backend preparation is finished: stop polling and start file transfer to browser
        clearInterval(activePollInterval);
        activePollInterval = null;

        // Note: We do NOT set 100% or "Complete!" yet, because the actual file transfer
        // to the user's computer must complete first.
        progressBar.style.width = "98%";
        progressPercent.textContent = "98%";
        statusLabel.textContent = "Transferring MP4 to your computer...";

        // Begin the real file transfer to browser
        await transferFileToComputer(downloadId, info.filename);

      } else if (status === "failed") {
        clearInterval(activePollInterval);
        activePollInterval = null;

        const errorMsg = info.error || "The download failed during processing.";
        statusLabel.textContent = "Download failed.";
        showAlert(errorMsg, "danger");

        downloadBtn.disabled = false;
        qualitySelect.disabled = false;
      }
    } catch (err) {
      console.warn("Polling retry error:", err);
      failureCount++;
      if (failureCount >= 5) {
        clearInterval(activePollInterval);
        activePollInterval = null;
        showAlert("Lost connection to the backend server while tracking progress.", "danger");
        downloadBtn.disabled = false;
        qualitySelect.disabled = false;
      }
    }
  }, 750); // Poll every 750ms
}

/**
 * Transfers the completed MP4 from FastAPI backend to the user's computer.
 * Tracks actual bytes transferred and only marks progress 100% when complete.
 */
async function transferFileToComputer(downloadId, serverFilename) {
  const fileUrl = `${API_BASE}/download/file/${downloadId}`;
  const defaultFilename = serverFilename || "video.mp4";

  // Pre-configure the fallback download link
  manualDownloadLink.href = fileUrl;
  manualDownloadLink.setAttribute("download", defaultFilename);

  try {
    const response = await fetch(fileUrl);
    if (!response.ok) {
      let errorMsg = `Server error (${response.status})`;
      try {
        const errorJson = await response.json();
        errorMsg = errorJson.detail || errorMsg;
      } catch (_) {
        try {
          const errorText = await response.text();
          if (errorText) errorMsg = errorText;
        } catch (_) {}
      }
      throw new Error(errorMsg);
    }

    // Extract genuine filename from Content-Disposition header if available
    let filename = defaultFilename;
    const disposition = response.headers.get("Content-Disposition");
    if (disposition) {
      // RFC 5987 / RFC 6266 UTF-8 encoded filename
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match && utf8Match[1]) {
        try {
          filename = decodeURIComponent(utf8Match[1]);
        } catch (_) {}
      } else {
        const simpleMatch = disposition.match(/filename="?([^";]+)"?/i);
        if (simpleMatch && simpleMatch[1]) {
          filename = simpleMatch[1];
        }
      }
    }

    // Stream download chunks to track real transfer progress
    const contentLength = response.headers.get("Content-Length");
    const totalBytes = contentLength ? parseInt(contentLength, 10) : 0;

    let blob;
    if (response.body && totalBytes > 0 && typeof response.body.getReader === "function") {
      const reader = response.body.getReader();
      const chunks = [];
      let receivedBytes = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        receivedBytes += value.length;

        // Calculate transfer percentage
        const pct = Math.min(99.9, (receivedBytes / totalBytes) * 100);
        const mbReceived = (receivedBytes / (1024 * 1024)).toFixed(1);
        const mbTotal = (totalBytes / (1024 * 1024)).toFixed(1);
        statusLabel.textContent = `Saving to computer: ${mbReceived} MB / ${mbTotal} MB (${Math.round(pct)}%)...`;
        progressBar.style.width = `${Math.round(pct)}%`;
        progressPercent.textContent = `${Math.round(pct)}%`;
      }
      blob = new Blob(chunks, { type: "video/mp4" });
    } else {
      // Direct blob fallback if streaming reader is not available
      blob = await response.blob();
    }

    // Create object URL to trigger actual browser file save
    activeBlobUrl = window.URL.createObjectURL(blob);

    // Update manual download link to local blob URL for instant re-download
    manualDownloadLink.href = activeBlobUrl;
    manualDownloadLink.setAttribute("download", filename);

    // Automatically trigger browser file download into Downloads folder
    const downloadAnchor = document.createElement("a");
    downloadAnchor.style.display = "none";
    downloadAnchor.href = activeBlobUrl;
    downloadAnchor.download = filename;
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();

    setTimeout(() => {
      downloadAnchor.remove();
    }, 1000);

    // Fallback: If blob URL expires after 5 minutes, restore direct server URL
    setTimeout(() => {
      manualDownloadLink.href = fileUrl;
      manualDownloadLink.setAttribute("download", filename);
    }, 300000);

    // ONLY NOW that the actual file transfer is complete and the download is triggered:
    progressBar.style.width = "100%";
    progressPercent.textContent = "100%";
    statusLabel.textContent = "Complete! Download ready.";
    downloadAction.classList.remove("hidden");

  } catch (err) {
    console.error("File download error:", err);
    statusLabel.textContent = "Download failed.";
    showAlert(`Download transfer failed: ${err.message || "Could not save file to computer."}`, "danger");

    // Make the fallback download link visible and pointing to direct server URL
    manualDownloadLink.href = fileUrl;
    manualDownloadLink.setAttribute("download", defaultFilename);
    downloadAction.classList.remove("hidden");

  } finally {
    downloadBtn.disabled = false;
    qualitySelect.disabled = false;
  }
}
