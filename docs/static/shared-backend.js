/* Fixed Pages entry; the runtime branch contains only a public OCR URL. */
window.MEDTRACE_SHARED = (() => {
  const config = window.MEDTRACE_CONFIG || {};
  const enabled = config.mode === "demo" && (config.sharedDiscovery === true ||
    (location.hostname === "tyc13410573416-droid.github.io" && location.pathname.startsWith("/collocate-mobile/")));
  const cacheKey = "medtrace.sharedBackend.v1";
  const registry = [
    "https://raw.githubusercontent.com/tyc13410573416-droid/collocate-mobile/codex/ocr-runtime/backend.json",
    "https://api.github.com/repos/tyc13410573416-droid/collocate-mobile/contents/backend.json?ref=codex%2Focr-runtime",
  ];
  let lastCheck = 0, pending = null;
  const offlineText = "识图服务暂离线，演示案例仍可查看。服务恢复后可重新提交图片。";

  function validate(record) {
    if (!record || record.version !== 1 || typeof record.active !== "boolean") throw new Error("Invalid connection record");
    if (record.active && !/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(record.image_api_base)) throw new Error("Invalid OCR address");
    return record;
  }
  function manual() { return Boolean(config.imageManualBase); }
  function announce(state) {
    if (manual()) return;
    config.sharedImageStatus = state;
    window.dispatchEvent(new Event("medtrace-image-backend-change"));
    const input = document.getElementById("imageServiceUrl");
    if (input) input.value = config.imageApiBase || "";
    const label = document.getElementById("imageServiceStatus");
    if (label) label.textContent = state === "online" ? "团队识图服务已连接，地址变化会自动更新。" : state === "checking" ? "正在连接团队识图服务…" : offlineText;
  }
  async function jsonRequest(url, timeout) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { signal: controller.signal, credentials: "omit", cache: "no-store" });
      if (!response.ok) throw new Error("Service unavailable");
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  async function discover() {
    let cached = null;
    try { cached = validate(JSON.parse(localStorage.getItem(cacheKey))); } catch (_) {}
    for (const source of registry) {
      try {
        const separator = source.includes("?") ? "&" : "?";
        const body = await jsonRequest(source + separator + "t=" + Math.floor(Date.now() / 30000), 4000);
        const record = validate(body.content && body.encoding === "base64" ? JSON.parse(atob(body.content.replace(/\s/g, ""))) : body);
        try { localStorage.setItem(cacheKey, JSON.stringify(record)); } catch (_) {}
        return record;
      } catch (_) { /* Try the second public endpoint, then validated local cache. */ }
    }
    return cached;
  }
  async function refresh(force = false) {
    if (!enabled || manual()) return;
    if (pending) return pending;
    if (!force && Date.now() - lastCheck < 45000) return;
    lastCheck = Date.now();
    pending = (async () => {
      announce("checking");
      const record = await discover();
      if (manual()) return;
      if (!record || !record.active) {
        config.imageApiBase = "";
        announce("offline");
        return;
      }
      config.imageApiBase = record.image_api_base;
      try {
        const status = await jsonRequest(record.image_api_base + "/api/image-status", 6000);
        if (status.configured !== true) throw new Error("OCR not ready");
        announce("online");
      } catch (_) { announce("offline"); }
    })().finally(() => { pending = null; });
    return pending;
  }
  async function ensureReady() {
    if (!enabled || manual()) return;
    await refresh(config.sharedImageStatus !== "online");
    if (config.sharedImageStatus !== "online") throw new Error(offlineText);
  }
  if (enabled) setTimeout(() => refresh(true), 0);
  return { enabled, refresh, ensureReady };
})();
