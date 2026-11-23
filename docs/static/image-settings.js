/* Only a public proxy URL is stored here. API keys remain in Nexent/backend. */
(() => {
  const config = window.MEDTRACE_CONFIG;
  const form = document.getElementById("imageServiceForm");
  const input = document.getElementById("imageServiceUrl");
  const status = document.getElementById("imageServiceStatus");
  const storageKey = "medtrace.imageApiBase.v1";
  const originalBase = config.imageApiBase || "";
  function normalized(value) {
    if (!value.trim()) return "";
    const url = new URL(value);
    if (url.username || url.password || url.search || url.hash || (url.protocol !== "https:" && url.origin !== location.origin)) {
      throw new Error("请填写 HTTPS 后端地址，不包含密钥、查询参数或页面锚点。");
    }
    return url.href.replace(/\/$/, "");
  }
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) { config.imageApiBase = normalized(saved); config.imageManualBase = true; }
  } catch (_) { /* Storage may be disabled; configuration still works this visit. */ }
  input.value = config.imageApiBase || "";
  if (config.imageApiBase) status.textContent = "已恢复本机保存的后端地址，点击检查连接后再使用。";
  else if (config.mode === "api") status.textContent = "本地页面使用同一服务器的图片接口。";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    const controls = Array.from(form.querySelectorAll("button, input"));
    try {
      const base = normalized(input.value);
      config.imageApiBase = base;
      config.imageManualBase = Boolean(base);
      try { if (base) localStorage.setItem(storageKey, base); else localStorage.removeItem(storageKey); } catch (_) {}
      window.dispatchEvent(new Event("medtrace-image-backend-change"));
      if (!base && config.mode !== "api") {
        if (window.MEDTRACE_SHARED?.enabled) { await window.MEDTRACE_SHARED.refresh(true); return; }
        status.textContent = "已清除本机地址，当前使用图片预览与样本演示。";
        return;
      }
      controls.forEach((control) => { control.disabled = true; });
      status.textContent = "正在检查后端连接…";
      const response = await fetch(`${base}/api/image-status`, { signal: controller.signal, credentials: "omit", cache: "no-store" });
      if (!response.ok) throw new Error(`后端检查失败（HTTP ${response.status}）。`);
      const body = await response.json();
      if (typeof body.configured !== "boolean") throw new Error("此地址不是 MedTrace 图片后端，请核对地址。");
      status.textContent = body.configured ? "后端可访问，Nexent 参数已配置；仍需用真实图片验证识别效果。" : (body.message || "后端可访问，但尚未配置 Nexent 地址和 Agent。");
    } catch (error) {
      status.textContent = error.name === "AbortError" ? "连接检查超时，请检查后端网络。" : error instanceof TypeError ? "地址无效或后端不可访问，请检查 HTTPS 和跨域配置。" : error.message;
    } finally {
      clearTimeout(timer);
      controls.forEach((control) => { control.disabled = Boolean(document.getElementById("submitButton")?.disabled); });
    }
  });
  document.getElementById("resetImageService").addEventListener("click", () => {
    config.imageApiBase = originalBase;
    config.imageManualBase = false;
    input.value = originalBase;
    try { localStorage.removeItem(storageKey); } catch (_) {}
    status.textContent = "已恢复网页默认配置。";
    window.dispatchEvent(new Event("medtrace-image-backend-change"));
    window.MEDTRACE_SHARED?.refresh(true);
  });
})();
