

(function systemDocGenerator() {
  "use strict";

  // ──────────────────────────────────────────────────────────────────────
  //  CONFIGURATION — Edit these values to match your setup
  // ──────────────────────────────────────────────────────────────────────

  const INSPECTORBOT_API_URL = "http://127.0.0.1:8765/api/inspect/report";
  const INSPECTORBOT_PROGRESS_URL = "http://127.0.0.1:8765/api/inspect/progress";
  const AUTO_START       = true;
  const FRESH_RUN_ON_LOAD = true;
  const IFRAME_CRAWL     = true;

  // Maximum number of pages to scrape (safety limit)
  const MAX_PAGES         = 30;

  // How long (ms) to wait after navigation for the page to fully render
  const SETTLE_DELAY      = 3000;
  const FRAME_LOAD_TIMEOUT = 8000;

  // Screenshot settings
  const TAKE_SCREENSHOTS  = true;

  // LocalStorage keys
  const STATE_KEY         = "__sys_doc_gen_state__";
  const RUNNING_KEY       = "__sys_doc_gen_running__";

  // URL patterns to SKIP (regex). Prevents logging out, visiting
  // external sites, or entering destructive routes.
  const SKIP_PATTERNS     = [
    /\/logout/i,
    /\/signout/i,
    /\/delete/i,
    /\/remove/i,
    /mailto:/i,
    /tel:/i,
    /javascript:/i,
    /^#/,
  ];

  // URL patterns that ARE allowed even if they partially match a skip pattern
  const ALLOW_PATTERNS    = [
    // Add exceptions here if needed
  ];

  // ──────────────────────────────────────────────────────────────────────
  //  STATE
  // ──────────────────────────────────────────────────────────────────────

  let isRunning    = false;
  let observer     = null;
  let statusTimer  = null;

  // State persisted across navigations:
  // {
  //   phase: "idle" | "discovering" | "scraping" | "generating" | "done",
  //   pages: [{url, title, navLinks, forms, tables, buttons, headings, ...}],
  //   queue: ["/dashboard", "/users", ...],     // routes yet to visit
  //   visited: Set of absolute URLs visited,
  //   currentPage: string | null,               // current route being scraped
  //   startTime: ISO string,
  // }
  function loadState() {
    try {
      const raw = localStorage.getItem(STATE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }

  function saveState(state) {
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
  }

  function clearState() {
    localStorage.removeItem(STATE_KEY);
    localStorage.setItem(RUNNING_KEY, "false");
  }

  // ──────────────────────────────────────────────────────────────────────
  //  SAFE URL CHECKS
  // ──────────────────────────────────────────────────────────────────────

  /** Returns true if a URL should be skipped (not scraped). */
  function shouldSkipUrl(url) {
    if (!url || typeof url !== "string") return true;

    const normalized = normalizeUrl(url);
    if (!normalized) return true;

    try {
      const parsed = new URL(normalized);
      if (parsed.origin !== window.location.origin) return true;
    } catch {
      return true;
    }

    // Check allowlist first (overrides skip patterns)
    for (const pattern of ALLOW_PATTERNS) {
      if (pattern.test(normalized)) return false;
    }

    for (const pattern of SKIP_PATTERNS) {
      if (pattern.test(normalized)) return true;
    }

    return false;
  }

  /** Normalize a URL to an absolute string. */
  function normalizeUrl(href) {
    try {
      return new URL(href, window.location.origin).href;
    } catch {
      return null;
    }
  }

  /** Extract just the path portion (no query/hash) from a URL. */
  function getPath(url) {
    try {
      return new URL(url).pathname;
    } catch {
      return url;
    }
  }

  // ──────────────────────────────────────────────────────────────────────
  //  READ-ONLY PAGE EXTRACTION
  //  This function ONLY reads the DOM. It NEVER clicks, submits,
  //  modifies, or interacts with any element.
  // ──────────────────────────────────────────────────────────────────────

  function extractPageInfo(doc = document, win = window) {
    const url   = win.location.href;
    const title = doc.title;

    // Navigation links (navbar, sidebar, header, footer, breadcrumbs)
    const navLinks = [...doc.querySelectorAll(
      "nav a, header a, aside a, [role='navigation'] a, .breadcrumb a, " +
      "[class*='sidebar'] a, [class*='menu'] a, [class*='nav'] a"
    )]
      .map(a => {
        const href = a.href;
        const text = (a.innerText || "").trim();
        return { text, href, path: getPath(href) };
      })
      .filter(item => item.text && item.href && !shouldSkipUrl(item.href));

    // Remove duplicate paths (keep first occurrence)
    const seenPaths = new Set();
    const uniqueNavLinks = navLinks.filter(item => {
      if (seenPaths.has(item.path)) return false;
      seenPaths.add(item.path);
      return true;
    });

    // Forms (inspect structure only — NEVER submit)
    const forms = [...doc.querySelectorAll("form")].map(form => ({
      id:       form.id || "",
      action:   form.action,
      method:   (form.method || "GET").toUpperCase(),
      fields:   [...form.querySelectorAll("input, select, textarea, [contenteditable]")].map(f => ({
        type:        (f.type || f.tagName.toLowerCase()),
        name:        f.name || f.id || "",
        placeholder: f.placeholder || "",
        label:       findLabel(f),
        required:    f.required || false,
        disabled:    f.disabled || false,
        options:     extractSelectOptions(f),
      })),
      submitButtons: [...form.querySelectorAll(
        "button[type='submit'], input[type='submit'], button:not([type])"
      )].map(b => (b.innerText || b.value || "Submit").trim()),
    }));

    // Tables
    const tables = [...doc.querySelectorAll("table")].map(table => ({
      id:       table.id || "",
      headers:  [...table.querySelectorAll("th")].map(th => (th.innerText || "").trim()),
      rowCount: table.querySelectorAll("tbody tr, tr").length - (table.querySelector("thead") ? 1 : 0),
      caption:  (table.querySelector("caption") || {}).innerText || "",
    })).filter(t => t.headers.length > 0);

    // Buttons (inspect only — NEVER click)
    const buttons = [...doc.querySelectorAll(
      "button, [type='button'], [type='submit'], [role='button'], .btn, [class*='btn']"
    )]
      .map(b => ({
        text:    (b.innerText || b.value || b.getAttribute("aria-label") || "").trim(),
        type:    b.type || b.getAttribute("role") || "button",
        disabled: b.disabled || false,
        id:      b.id || "",
        classes: b.className || "",
      }))
      .filter(b => b.text)
      // Deduplicate by text
      .filter((b, i, arr) => arr.findIndex(x => x.text === b.text) === i);

    // Headings (h1-h6)
    const headings = [...doc.querySelectorAll("h1, h2, h3, h4, h5, h6")]
      .map(h => ({
        level: parseInt(h.tagName[1]),
        text:  (h.innerText || "").trim(),
        id:    h.id || "",
      }))
      .filter(h => h.text);

    // Cards / Panels / Widgets
    const cards = [...doc.querySelectorAll(
      ".card, .panel, .widget, [class*='card'], [class*='panel'], " +
      "[class*='widget'], [class*='stat'], [class*='metric'], [class*='info']"
    )]
      .slice(0, 20) // Cap at 20 to avoid bloating data
      .map(c => ({
        text:    (c.innerText || "").trim().slice(0, 200),
        classes: c.className || "",
      }))
      .filter(c => c.text);

    // Lists (ul, ol) — useful for feature lists, settings panels
    const lists = [...doc.querySelectorAll("ul, ol")]
      .slice(0, 15)
      .map(list => ({
        type: list.tagName.toLowerCase(),
        items: [...list.querySelectorAll("li")]
          .slice(0, 10)
          .map(li => (li.innerText || "").trim().slice(0, 150))
          .filter(Boolean),
      }))
      .filter(l => l.items.length > 0);

    // Modals / Dialogs (inspect structure only)
    const modals = [...doc.querySelectorAll(
      "[class*='modal'], [class*='dialog'], [class*='popup'], " +
      "[role='dialog'], [class*='overlay'], [class*='drawer']"
    )]
      .slice(0, 10)
      .map(m => ({
        text:    (m.innerText || "").trim().slice(0, 200),
        visible: m.offsetParent !== null || win.getComputedStyle(m).display !== "none",
        classes: m.className || "",
      }))
      .filter(m => m.text);

    // Tabs (inspect only)
    const tabs = [...doc.querySelectorAll(
      "[role='tablist'] [role='tab'], .nav-tabs .nav-link, [class*='tab']"
    )]
      .slice(0, 20)
      .map(t => ({
        text:     (t.innerText || "").trim(),
        active:   t.classList.contains("active") || t.getAttribute("aria-selected") === "true",
        href:     t.getAttribute("href") || "",
      }))
      .filter(t => t.text);

    // Breadcrumbs
    const breadcrumbs = [...doc.querySelectorAll(
      ".breadcrumb, [class*='breadcrumb'], [aria-label='breadcrumb']"
    )]
      .map(bc => [...bc.querySelectorAll("a, span, li")]
        .map(el => (el.innerText || "").trim())
        .filter(Boolean)
      )
      .filter(bc => bc.length > 0);

    // Footer content
    const footer = doc.querySelector("footer");
    const footerText = footer ? (footer.innerText || "").trim().slice(0, 300) : "";

    // Metadata (meta description, og tags, etc.)
    const metaDescription = (doc.querySelector('meta[name="description"]') || {}).content || "";
    const ogTitle        = (doc.querySelector('meta[property="og:title"]') || {}).content || "";

    // Page load timestamp
    const timestamp = new Date().toISOString();

    return {
      url, title, timestamp,
      metaDescription, ogTitle,
      navLinks:    uniqueNavLinks,
      forms,
      tables,
      buttons,
      headings,
      cards,
      lists,
      modals,
      tabs,
      breadcrumbs,
      footerText,
    };
  }

  // ──────────────────────────────────────────────────────────────────────
  //  EXTRACTION HELPERS (all read-only)
  // ──────────────────────────────────────────────────────────────────────

  /** Find the label text for a form element. */
  function findLabel(el) {
    if (el.id) {
      const label = document.querySelector(`label[for="${el.id}"]`);
      if (label) return (label.innerText || "").trim();
    }
    // Walk up to parent and find closest label
    const parent = el.closest("label");
    if (parent) {
      const clone = parent.cloneNode(true);
      clone.querySelectorAll("input, select, textarea").forEach(c => c.remove());
      return (clone.innerText || "").trim();
    }
    // Try aria-label
    if (el.getAttribute("aria-label")) return el.getAttribute("aria-label");
    // Try placeholder
    if (el.placeholder) return "";
    return "";
  }

  /** Extract options from a <select> element. */
  function extractSelectOptions(el) {
    if (el.tagName !== "SELECT") return [];
    return [...el.querySelectorAll("option")].map(opt => ({
      value:    opt.value,
      text:     (opt.innerText || "").trim(),
      selected: opt.selected,
    }));
  }

  // ──────────────────────────────────────────────────────────────────────
  //  SCREENSHOT (optional, read-only canvas capture)
  // ──────────────────────────────────────────────────────────────────────

  async function takeScreenshot(label) {
    if (!TAKE_SCREENSHOTS) return;
    try {
      if (typeof html2canvas === "undefined") {
        await new Promise((resolve, reject) => {
          const s = document.createElement("script");
          s.src = "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js";
          s.onload = resolve;
          s.onerror = () => reject(new Error("Failed to load html2canvas"));
          document.head.appendChild(s);
        });
      }
      const canvas = await html2canvas(document.body, {
        useCORS: true,
        allowTaint: true,
        logging: false,
      });
      const link = document.createElement("a");
      const safeLabel = label.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 50);
      link.download = `sysdoc_screenshot_${safeLabel}.png`;
      link.href = canvas.toDataURL("image/png");
      document.body.appendChild(link);
      link.click();
      setTimeout(() => document.body.removeChild(link), 200);
      log("OK", `Screenshot saved: sysdoc_screenshot_${safeLabel}.png`);
    } catch (err) {
      log("WARN", `Screenshot skipped: ${err.message}`);
    }
  }

  // ──────────────────────────────────────────────────────────────────────
  //  INSPECTORBOT API
  // ──────────────────────────────────────────────────────────────────────

  async function postInspectionReport(report) {
    log("INFO", `Sending inspection report to InspectorBot: ${INSPECTORBOT_API_URL}`);
    let res;

    if (typeof GM_xmlhttpRequest === "function") {
      res = await new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
          method:  "POST",
          url:     INSPECTORBOT_API_URL,
          headers: {
            "Content-Type":  "application/json",
          },
          data: JSON.stringify(report),
          onload:  r => (r.status >= 200 && r.status < 300)
                        ? resolve({ ok: true, status: r.status, json: () => JSON.parse(r.responseText) })
                        : reject(new Error(`InspectorBot ${r.status}: ${r.responseText}`)),
          onerror: e => reject(new Error(`Network error: ${e}`)),
          ontimeout: () => reject(new Error("Request timed out")),
        });
      });
    } else {
      res = await fetch(INSPECTORBOT_API_URL, {
        method:  "POST",
        headers: {
          "Content-Type":  "application/json",
        },
        body: JSON.stringify(report),
      });
    }

    if (!res.ok) {
      const errBody = await (typeof res.text === "function" ? res.text() : res.statusText);
      throw new Error(`InspectorBot ${res.status}: ${errBody}`);
    }

    return await res.json();
  }

  function postProgress(event, extra = {}) {
    const payload = {
      event,
      url: window.location.href,
      title: document.title,
      time: new Date().toISOString(),
      ...extra,
    };

    try {
      if (typeof GM_xmlhttpRequest === "function") {
        GM_xmlhttpRequest({
          method: "POST",
          url: INSPECTORBOT_PROGRESS_URL,
          headers: { "Content-Type": "application/json" },
          data: JSON.stringify(payload),
        });
        return;
      }

      fetch(INSPECTORBOT_PROGRESS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(() => {});
    } catch {
      // Progress pings are best-effort; the final report path still handles errors.
    }
  }

  // ──────────────────────────────────────────────────────────────────────
  //  FILE DOWNLOAD HELPERS
  // ──────────────────────────────────────────────────────────────────────

  function downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType || "text/plain;charset=utf-8" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 200);
  }

  // ──────────────────────────────────────────────────────────────────────
  //  CONSOLE LOGGER
  // ──────────────────────────────────────────────────────────────────────

  function log(tag, msg) {
    const colors = {
      INFO: "#2196F3",
      OK:   "#4CAF50",
      WARN: "#FF9800",
      ERR:  "#f44336",
      STEP: "#9C27B0",
    };
    const c = colors[tag] || "#999";
    console.log(`%c[SYS-DOC][${tag}] ${msg}`, `color:${c};font-weight:bold`);
  }

  // ──────────────────────────────────────────────────────────────────────
  //  CORE PIPELINE
  // ──────────────────────────────────────────────────────────────────────

  function ensureCrawlerFrame() {
    let frame = document.getElementById("sys-doc-crawler-frame");
    if (!frame) {
      frame = document.createElement("iframe");
      frame.id = "sys-doc-crawler-frame";
      frame.setAttribute("aria-hidden", "true");
      frame.style.cssText = `
        position: fixed;
        width: 1px;
        height: 1px;
        left: -9999px;
        top: -9999px;
        opacity: 0;
        pointer-events: none;
      `;
      document.body.appendChild(frame);
    }
    return frame;
  }

  function loadFrameUrl(frame, url) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        cleanup();
        reject(new Error(`Timed out loading ${url}`));
      }, Math.max(FRAME_LOAD_TIMEOUT, SETTLE_DELAY + 2000));

      function cleanup() {
        clearTimeout(timeout);
        frame.removeEventListener("load", onLoad);
        frame.removeEventListener("error", onError);
      }

      function onLoad() {
        cleanup();
        setTimeout(() => resolve(frame), SETTLE_DELAY);
      }

      function onError() {
        cleanup();
        reject(new Error(`Failed to load ${url}`));
      }

      frame.addEventListener("load", onLoad);
      frame.addEventListener("error", onError);
      frame.src = url;
    });
  }

  async function runIframeCrawler(state, origin) {
    log("STEP", "Using hidden iframe crawler so the pasted script survives page-to-page assessment.");

    const frame = ensureCrawlerFrame();
    const queued = new Set(state.queue.map(item => normalizeUrl(item)).filter(Boolean));
    const visited = new Set(state.visited || []);

    if (!visited.has(window.location.href) && !state.pages.some(page => page.url === window.location.href)) {
      const currentInfo = extractPageInfo();
      currentInfo.phase = "current-page-scrape";
      state.pages.push(currentInfo);
      state.visited.push(window.location.href);
      visited.add(window.location.href);
      log("OK", `Scraped current page: ${currentInfo.title || window.location.href}`);
      postProgress("scraped-current-page", {
        pageCount: state.pages.length,
        queueCount: state.queue.length,
        scrapedUrl: window.location.href,
      });

      for (const link of currentInfo.navLinks) {
        const absUrl = normalizeUrl(link.href);
        if (!absUrl || shouldSkipUrl(absUrl) || visited.has(absUrl) || queued.has(absUrl)) {
          continue;
        }
        state.queue.push(absUrl);
        queued.add(absUrl);
      }
    }

    state.phase = "scraping";
    saveState(state);

    while (isRunning && state.queue.length > 0 && state.pages.length < MAX_PAGES) {
      const nextItem = state.queue.shift();
      const nextUrl = normalizeUrl(nextItem);
      queued.delete(nextUrl);

      if (!nextUrl || visited.has(nextUrl) || shouldSkipUrl(nextUrl)) {
        saveState(state);
        continue;
      }

      updateStatusText(`Loading ${getPath(nextUrl)}...`);
      log("INFO", `Iframe loading: ${nextUrl}`);

      try {
        await loadFrameUrl(frame, nextUrl);
        const doc = frame.contentDocument;
        const win = frame.contentWindow;
        if (!doc || !win || win.location.origin !== origin) {
          throw new Error("Loaded page is not readable from the current origin");
        }

        const info = extractPageInfo(doc, win);
        info.phase = "iframe-scrape";
        state.pages.push(info);
        state.visited.push(nextUrl);
        visited.add(nextUrl);

        log("OK", `Scraped: ${info.title || nextUrl} (${info.headings.length} headings, ${info.forms.length} forms, ${info.tables.length} tables)`);
        postProgress("scraped-page", {
          pageCount: state.pages.length,
          queueCount: state.queue.length,
          scrapedUrl: nextUrl,
        });

        for (const link of info.navLinks) {
          const absUrl = normalizeUrl(link.href);
          if (!absUrl || shouldSkipUrl(absUrl) || visited.has(absUrl) || queued.has(absUrl)) {
            continue;
          }
          if (absUrl.startsWith(origin)) {
            state.queue.push(absUrl);
            queued.add(absUrl);
          }
        }
      } catch (err) {
        log("WARN", `Skipped ${nextUrl}: ${err.message}`);
        state.visited.push(nextUrl);
        visited.add(nextUrl);
        postProgress("skipped-page", {
          pageCount: state.pages.length,
          queueCount: state.queue.length,
          skippedUrl: nextUrl,
          error: err.message,
        });
      }

      saveState(state);
      updateUI();
    }

    state.phase = "generating";
    state.queue = [];
    saveState(state);
    updateUI();
    return runPipeline();
  }

  /**
   * Main pipeline. Resumable — call startGenerator() to begin or resume.
   * State persists in localStorage across page navigations.
   */
  async function runPipeline() {
    if (!isRunning) return;

    const origin = window.location.origin;
    let state = loadState();

    // ── Fresh start ────────────────────────────────────────────────────
    if (!state) {
      log("STEP", "Fresh start — initializing scraper");
      state = {
        phase:       "discovering",
        pages:       [],
        queue:       [],
        visited:     [],
        currentPage: window.location.href,
        startTime:   new Date().toISOString(),
      };
    } else {
      log("STEP", `Resuming — phase=${state.phase}, pages scraped=${state.pages.length}, queue remaining=${state.queue.length}`);
    }

    if (IFRAME_CRAWL && (state.phase === "discovering" || state.phase === "scraping")) {
      return runIframeCrawler(state, origin);
    }

    // ── Phase 1: Discover routes ───────────────────────────────────────
    if (state.phase === "discovering") {
      // Always scrape the current page first (it may be home)
      log("STEP", `Discovering routes from: ${window.location.href}`);

      // Wait for page to settle if we navigated here
      if (state.pages.length > 0) {
        log("INFO", `Waiting ${SETTLE_DELAY}ms for page to settle...`);
        await new Promise(r => setTimeout(r, SETTLE_DELAY));
      }

      // Extract page data
      const info = extractPageInfo();
      info.phase = "scrape";
      state.pages.push(info);

      // Track this URL as visited
      if (!state.visited.includes(window.location.href)) {
        state.visited.push(window.location.href);
      }

      log("OK", `Scraped: ${info.title} (${info.headings.length} headings, ${info.forms.length} forms, ${info.tables.length} tables, ${info.buttons.length} buttons)`);

      // Screenshot
      const pageSlug = getPath(window.location.href).replace(/\//g, "_") || "home";
      await takeScreenshot(pageSlug);

      // Collect new links from this page
      const newRoutes = [];
      for (const link of info.navLinks) {
        const absUrl = normalizeUrl(link.href);
        if (!absUrl) continue;
        if (absUrl.startsWith(origin) && !state.visited.includes(absUrl)) {
          const path = getPath(absUrl);
          if (!shouldSkipUrl(absUrl) && !state.queue.includes(path)) {
            newRoutes.push(path);
            state.queue.push(path);
          }
        }
      }

      if (newRoutes.length > 0) {
        log("INFO", `Discovered ${newRoutes.length} new route(s): ${newRoutes.join(", ")}`);
      }

      saveState(state);

      // Navigate to next route in queue
      if (state.queue.length > 0 && state.pages.length < MAX_PAGES) {
        const nextPath = state.queue.shift();
        const nextUrl  = new URL(nextPath, origin).href;
        state.currentPage = nextPath;
        state.phase = "scraping";
        saveState(state);
        log("INFO", `Navigating to: ${nextUrl} (${state.queue.length} routes remaining)`);
        updateUI();
        window.location.href = nextUrl;
        return; // context destroyed by navigation
      }

      // Queue empty — all discovered routes scraped
      state.phase = "generating";
      state.queue = [];
      saveState(state);
    }

    // ── Phase 2: Scrape remaining pages (same logic, different entry) ──
    if (state.phase === "scraping") {
      log("STEP", `Scraping page ${state.pages.length + 1} (max ${MAX_PAGES})`);

      log("INFO", `Waiting ${SETTLE_DELAY}ms for page to settle...`);
      await new Promise(r => setTimeout(r, SETTLE_DELAY));

      const info = extractPageInfo();
      info.phase = "scrape";
      state.pages.push(info);

      if (!state.visited.includes(window.location.href)) {
        state.visited.push(window.location.href);
      }

      log("OK", `Scraped: ${info.title} (${info.headings.length} headings, ${info.forms.length} forms, ${info.tables.length} tables)`);

      const pageSlug = getPath(window.location.href).replace(/\//g, "_") || "page_" + state.pages.length;
      await takeScreenshot(pageSlug);

      // Discover new links from this page too
      const newRoutes = [];
      for (const link of info.navLinks) {
        const absUrl = normalizeUrl(link.href);
        if (!absUrl) continue;
        if (absUrl.startsWith(origin) && !state.visited.includes(absUrl)) {
          const path = getPath(absUrl);
          if (!shouldSkipUrl(absUrl) && !state.queue.includes(path)) {
            newRoutes.push(path);
            state.queue.push(path);
          }
        }
      }
      if (newRoutes.length > 0) {
        log("INFO", `Discovered ${newRoutes.length} more route(s): ${newRoutes.join(", ")}`);
      }

      saveState(state);

      // Continue scraping or move to generation
      if (state.queue.length > 0 && state.pages.length < MAX_PAGES) {
        const nextPath = state.queue.shift();
        const nextUrl  = new URL(nextPath, origin).href;
        state.currentPage = nextPath;
        saveState(state);
        log("INFO", `Navigating to: ${nextUrl} (${state.queue.length} remaining)`);
        updateUI();
        window.location.href = nextUrl;
        return;
      }

      state.phase = "generating";
      state.queue = [];
      saveState(state);
    }

    // ── Phase 3: Send report to InspectorBot API ───────────────────────
    if (state.phase === "generating") {
      log("STEP", `All ${state.pages.length} pages scraped. Sending report to InspectorBot...`);
      updateUI();
      updateStatusText("Sending report to InspectorBot...");
      postProgress("submitting-report", {
        pageCount: state.pages.length,
        visitedCount: state.visited.length,
      });

      const report = {
        target: {
          origin,
          currentUrl: window.location.href,
          title: document.title,
          userAgent: navigator.userAgent,
        },
        metadata: {
          generatedBy: "browserscript.js",
          mode: "read-only-dom-assessment",
          maxPages: MAX_PAGES,
          startedAt: state.startTime,
          completedAt: new Date().toISOString(),
        },
        visited: state.visited,
        pages: state.pages,
      };

      let apiResponse;
      try {
        apiResponse = await postInspectionReport(report);
        log("OK", "InspectorBot generated a rebuild blueprint.");
        postProgress("report-complete", {
          pageCount: state.pages.length,
          reportPath: apiResponse.reportPath || "",
          blueprintPath: apiResponse.blueprintPath || "",
        });
      } catch (err) {
        log("ERR", `InspectorBot API call failed: ${err.message}`);
        postProgress("report-error", {
          pageCount: state.pages.length,
          error: err.message,
        });
        log("INFO", "Your data has been saved locally. Start inspectorbot.py and retry generation.");
        state.phase = "retry";
        saveState(state);
        downloadFile(
          `extracted_data_${timestamp()}.json`,
          JSON.stringify(report, null, 2),
          "application/json"
        );
        updateStatusText("InspectorBot error — data saved. Click to retry.");
        return;
      }

      // ── Download results ─────────────────────────────────────────────
      const ts = timestamp();
      const blueprint = apiResponse.blueprint || "# ISP System Rebuild Blueprint\n\nInspectorBot returned no blueprint content.";

      // Markdown document
      const docFilename = `system_design_${ts}.md`;
      downloadFile(docFilename, blueprint, "text/markdown;charset=utf-8");
      log("OK", `Design document saved: ${docFilename}`);

      // Raw JSON data
      const dataFilename = `extracted_data_${ts}.json`;
      downloadFile(dataFilename, JSON.stringify(report, null, 2), "application/json");
      log("OK", `Raw data saved: ${dataFilename}`);
      if (apiResponse.reportPath) log("OK", `InspectorBot report path: ${apiResponse.reportPath}`);
      if (apiResponse.blueprintPath) log("OK", `InspectorBot blueprint path: ${apiResponse.blueprintPath}`);

      // Summary
      const elapsed = ((Date.now() - new Date(state.startTime).getTime()) / 1000).toFixed(1);
      log("OK", `══════════════════════════════════════════════════`);
      log("OK", `  COMPLETE! ${state.pages.length} pages scraped in ${elapsed}s`);
      log("OK", `  Document: ${docFilename}`);
      log("OK", `  Data:     ${dataFilename}`);
      log("OK", `══════════════════════════════════════════════════`);

      // Mark done
      state.phase = "done";
      saveState(state);
      updateUI();
      speak("Documentation complete");
    }

    // ── Phase: retry (LLM failed, can retry from saved data) ───────────
    if (state.phase === "retry") {
      log("INFO", "Previous generation failed. Retrying from saved data...");
      state.phase = "generating";
      saveState(state);
      // Restart from generation phase
      if (state.currentPage !== null) {
        // Navigate back to origin to generate in a stable context
        window.location.href = origin;
        return;
      }
      // If we're already at origin, just continue
      runPipeline();
      return;
    }

    // ── Phase: done ─────────────────────────────────────────────────────
    if (state.phase === "done") {
      log("INFO", "Documentation already generated. Click the button to start fresh.");
    }
  }

  // ──────────────────────────────────────────────────────────────────────
  //  SPEECH UTILITY (optional audio feedback)
  // ──────────────────────────────────────────────────────────────────────

  function speak(message) {
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.rate  = 1.3;
      utterance.volume = 0.7;
      window.speechSynthesis.speak(utterance);
    }
  }

  // ──────────────────────────────────────────────────────────────────────
  //  TIMESTAMP HELPER
  // ──────────────────────────────────────────────────────────────────────

  function timestamp() {
    return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  }

  // ──────────────────────────────────────────────────────────────────────
  //  START / STOP CONTROLS
  // ──────────────────────────────────────────────────────────────────────

  function startGenerator() {
    if (isRunning) return;
    isRunning = true;
    localStorage.setItem(RUNNING_KEY, "true");
    log("INFO", "Documentation generator STARTED (read-only mode)");
    postProgress("started", { mode: IFRAME_CRAWL ? "iframe-crawl" : "navigation-crawl" });
    updateUI();
    runPipeline();
  }

  function stopGenerator() {
    isRunning = false;
    localStorage.setItem(RUNNING_KEY, "false");
    if (observer) observer.disconnect();
    log("INFO", "Documentation generator STOPPED");
    updateUI();
  }

  function resetGenerator() {
    stopGenerator();
    clearState();
    log("INFO", "Documentation generator RESET — all state cleared");
    updateUI();
    updateStatusText("Ready");
  }

  // ──────────────────────────────────────────────────────────────────────
  //  STATUS DISPLAY
  // ──────────────────────────────────────────────────────────────────────

  function updateStatusText(text) {
    const el = document.getElementById("sys-doc-status");
    if (el) el.textContent = text;
  }

  function refreshStatusDisplay() {
    if (!isRunning) return;
    const state = loadState();
    if (!state) return;

    const pageCount    = state.pages ? state.pages.length : 0;
    const queueCount   = state.queue  ? state.queue.length  : 0;
    const elapsed      = state.startTime
      ? `${((Date.now() - new Date(state.startTime).getTime()) / 1000).toFixed(0)}s`
      : "0s";

    const phaseLabels = {
      discovering: "Discovering",
      scraping:    "Scraping",
      generating:  "Generating doc",
      done:        "Complete",
      retry:       "Retry pending",
    };

    const label = phaseLabels[state.phase] || state.phase;
    const statusText = state.phase === "done"
      ? `Done — ${pageCount} pages documented`
      : `${label} — ${pageCount} pages, ${queueCount} queued (${elapsed})`;

    updateStatusText(statusText);
  }

  // ──────────────────────────────────────────────────────────────────────
  //  UI CONTROL BUTTON
  // ──────────────────────────────────────────────────────────────────────

  // Remove existing UI if present (handles re-injection)
  const existingUI = document.getElementById("sys-doc-control");
  if (existingUI) existingUI.remove();

  // Create container
  const container = document.createElement("div");
  container.id = "sys-doc-control";
  container.style.cssText = `
    position: fixed;
    bottom: 15px;
    right: 15px;
    z-index: 99999;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: flex-end;
  `;

  // Main toggle button
  const mainButton = document.createElement("button");
  mainButton.style.cssText = `
    padding: 10px 20px;
    font-family: inherit;
    font-size: 14px;
    font-weight: bold;
    color: white;
    border: none;
    border-radius: 50px;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    transition: background-color 0.3s ease, transform 0.1s ease;
    min-width: 130px;
  `;

  // Reset button (small)
  const resetButton = document.createElement("button");
  resetButton.textContent = "Reset";
  resetButton.style.cssText = `
    padding: 5px 14px;
    font-family: inherit;
    font-size: 11px;
    font-weight: bold;
    color: #666;
    background: #f0f0f0;
    border: 1px solid #ccc;
    border-radius: 50px;
    cursor: pointer;
    transition: all 0.2s ease;
    display: none;
  `;
  resetButton.addEventListener("mouseenter", () => {
    resetButton.style.background = "#e0e0e0";
  });
  resetButton.addEventListener("mouseleave", () => {
    resetButton.style.background = "#f0f0f0";
  });
  resetButton.addEventListener("click", (e) => {
    e.stopPropagation();
    resetGenerator();
  });

  // Status label
  const statusLabel = document.createElement("div");
  statusLabel.id = "sys-doc-status";
  statusLabel.style.cssText = `
    padding: 4px 12px;
    font-family: inherit;
    font-size: 11px;
    color: #333;
    background: rgba(255,255,255,0.9);
    border-radius: 20px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    max-width: 300px;
    text-align: right;
    backdrop-filter: blur(4px);
  `;

  // Compose UI
  container.appendChild(statusLabel);
  container.appendChild(mainButton);
  container.appendChild(resetButton);
  document.body.appendChild(container);

  // Update UI state
  function updateUI() {
    const state = loadState();
    const isDone = state && state.phase === "done";

    if (isRunning) {
      mainButton.textContent = "Running...";
      mainButton.style.backgroundColor = "#28a745";
      resetButton.style.display = "none";
    } else if (isDone) {
      mainButton.textContent = "Done ✓";
      mainButton.style.backgroundColor = "#17a2b8";
      resetButton.style.display = "block";
    } else {
      mainButton.textContent = "Start";
      mainButton.style.backgroundColor = "#dc3545";
      resetButton.style.display = state ? "block" : "none";
    }

    if (state && state.phase === "generating") {
      mainButton.textContent = "Generating...";
      mainButton.style.backgroundColor = "#6f42c1";
    }

    if (state && state.phase === "retry") {
      mainButton.textContent = "Retry";
      mainButton.style.backgroundColor = "#fd7e14";
    }

    refreshStatusDisplay();
  }

  // Main button click handler
  mainButton.addEventListener("click", () => {
    if (isRunning) {
      stopGenerator();
    } else {
      startGenerator();
    }
    updateUI();
  });

  // Status refresh timer
  function startStatusTimer() {
    if (statusTimer) clearInterval(statusTimer);
    statusTimer = setInterval(refreshStatusDisplay, 2000);
  }
  startStatusTimer();

  // ──────────────────────────────────────────────────────────────────────
  //  AUTO-RESUME ON PAGE LOAD
  //  If the script was running when the page navigated, it will
  //  automatically resume the pipeline.
  // ──────────────────────────────────────────────────────────────────────

  const wasRunning = localStorage.getItem(RUNNING_KEY) === "true";
  const existingState = loadState();
  const shouldStartFresh = AUTO_START && FRESH_RUN_ON_LOAD && !wasRunning;

  if (shouldStartFresh && existingState) {
    clearState();
  }

  if (wasRunning) {
    const state = loadState();
    if (state && (state.phase === "scraping" || state.phase === "discovering")) {
      log("INFO", "Auto-resuming after page navigation...");
      isRunning = true;
      updateUI();
      // Small delay to ensure DOM is ready
      setTimeout(() => runPipeline(), 500);
    } else if (state && state.phase === "generating") {
      log("INFO", "Resuming document generation...");
      isRunning = true;
      updateUI();
      setTimeout(() => runPipeline(), 500);
    } else if (state && state.phase === "retry") {
      log("INFO", "Retry phase detected. Ready to retry.");
      isRunning = false;
      updateUI();
    } else {
      isRunning = false;
      updateUI();
    }
  } else {
    updateUI();
    if (AUTO_START) {
      log("INFO", "Auto-start enabled. Beginning read-only assessment now...");
      setTimeout(() => startGenerator(), 500);
    }
  }

  // ──────────────────────────────────────────────────────────────────────
  //  CONSOLE EXPOSE (for manual control in DevTools)
  // ──────────────────────────────────────────────────────────────────────

  /**
   * Start or resume the documentation generator.
   */
  window.sysDocStart    = startGenerator;

  /**
   * Stop the documentation generator.
   */
  window.sysDocStop     = stopGenerator;

  /**
   * Reset all saved state and start fresh.
   */
  window.sysDocReset    = resetGenerator;

  /**
   * Show current scraper state (for debugging).
   */
  window.sysDocStatus   = function () {
    const s = loadState();
    if (!s) { log("INFO", "No state found. Click Start to begin."); return null; }
    log("INFO", JSON.stringify(s, null, 2));
    return s;
  };

  /**
   * Extract data from the current page only (no navigation).
   */
  window.sysDocExtract  = function () {
    const info = extractPageInfo();
    log("INFO", JSON.stringify(info, null, 2));
    return info;
  };

  // ──────────────────────────────────────────────────────────────────────
  //  UNLOAD SAFETY — ensure we record state before page closes
  // ──────────────────────────────────────────────────────────────────────

  window.addEventListener("beforeunload", () => {
    if (isRunning) {
      localStorage.setItem(RUNNING_KEY, "true");
    }
  });

  log("INFO", "System Documentation Generator v2.1 loaded (read-only auto-run mode).");
  log("INFO", "Assessment will start automatically and report back to InspectorBot.");

})();


