/**
 * Google AdSense Modular Integration
 *
 * This module manages Google AdSense initialization and ad slot rendering.
 * It is completely decoupled from the Video Downloader business logic.
 *
 * Advertisements are DISABLED by default until you receive official site approval
 * from Google AdSense and update the configuration below.
 */

const ADSENSE_CONFIG = {
  // 1. MASTER SWITCH: Set to true ONLY AFTER your website is approved by Google AdSense
  ENABLED: false,

  // 2. PUBLISHER ID: Replace with your actual AdSense Publisher ID (e.g., "ca-pub-1234567890123456")
  PUBLISHER_ID: "ca-pub-XXXXXXXXXXXXXXXX",

  // 3. AD UNIT SLOTS: Replace with your actual Ad Unit IDs created in Google AdSense dashboard
  // Policy Notice: Ad containers are placed in compliant top/bottom positions, strictly
  // isolated from download controls, quality selectors, and action buttons.
  SLOTS: {
    TOP_BANNER: "XXXXXXXXXX",     // Responsive display ad (Top Header Banner)
    BOTTOM_BANNER: "XXXXXXXXXX",  // Responsive display ad (Bottom Content Banner)
  },

  // 4. TEST MODE: Set to true while testing layout before going live to request test ads
  TEST_MODE: false
};

/**
 * Initializes Google AdSense if enabled and properly configured.
 */
function initAdSense() {
  // Safety check: Exit immediately if ads are disabled
  if (!ADSENSE_CONFIG.ENABLED) {
    hideAllAdContainers();
    return;
  }

  // Safety check: Do not load if Publisher ID is still the default placeholder
  if (!ADSENSE_CONFIG.PUBLISHER_ID || ADSENSE_CONFIG.PUBLISHER_ID === "ca-pub-XXXXXXXXXXXXXXXX") {
    console.warn("[AdSense] Ads are enabled but PUBLISHER_ID is not configured. Keeping ads hidden.");
    hideAllAdContainers();
    return;
  }

  // 1. Inject the official Google AdSense script into <head>
  loadAdSenseScript(ADSENSE_CONFIG.PUBLISHER_ID);

  // 2. Render compliant ad slots in designated containers
  renderAdSlot("ad-top-banner", ADSENSE_CONFIG.SLOTS.TOP_BANNER);
  renderAdSlot("ad-bottom-banner", ADSENSE_CONFIG.SLOTS.BOTTOM_BANNER);
}

/**
 * Dynamically loads the official Google AdSense script in <head>.
 * This ensures no requests to Google ad servers are made when ads are disabled.
 */
function loadAdSenseScript(publisherId) {
  // Prevent duplicate script injection
  if (document.querySelector('script[src*="pagead2.googlesyndication.com"]')) {
    return;
  }

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(publisherId)}`;
  script.crossOrigin = "anonymous";
  document.head.appendChild(script);
}

/**
 * Renders an ad slot inside a container element if configured.
 *
 * @param {string} containerId - The DOM ID of the container element.
 * @param {string} slotId - The Google Ad Unit ID for this slot.
 */
function renderAdSlot(containerId, slotId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Do not display if slot ID is still a placeholder
  if (!slotId || slotId === "XXXXXXXXXX") {
    container.classList.add("hidden");
    return;
  }

  // Ensure container is visible
  container.classList.remove("hidden");

  const slotWrapper = container.querySelector(".ad-content");
  if (!slotWrapper) return;

  // Create standard responsive Google AdSense <ins> tag
  const ins = document.createElement("ins");
  ins.className = "adsbygoogle";
  ins.style.display = "block";
  ins.setAttribute("data-ad-client", ADSENSE_CONFIG.PUBLISHER_ID);
  ins.setAttribute("data-ad-slot", slotId);
  ins.setAttribute("data-ad-format", "auto");
  ins.setAttribute("data-full-width-responsive", "true");

  if (ADSENSE_CONFIG.TEST_MODE) {
    ins.setAttribute("data-adtest", "on");
  }

  slotWrapper.innerHTML = "";
  slotWrapper.appendChild(ins);

  // Safely trigger AdSense rendering for this tag
  try {
    (window.adsbygoogle = window.adsbygoogle || []).push({});
  } catch (err) {
    console.warn(`[AdSense] Could not render slot ${slotId}:`, err);
  }
}

/**
 * Hides all ad containers from the DOM layout when ads are disabled.
 */
function hideAllAdContainers() {
  const adContainers = document.querySelectorAll(".ad-container");
  adContainers.forEach((container) => {
    container.classList.add("hidden");
  });
}

// Initialize AdSense on DOMContentLoaded without interfering with other scripts
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAdSense);
} else {
  initAdSense();
}

