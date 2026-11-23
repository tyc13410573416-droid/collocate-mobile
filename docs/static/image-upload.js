/* Image bytes go only to our configured backend; Nexent credentials stay there. */
window.MEDTRACE_IMAGES = (() => {
  const maxBytes = 10 * 1024 * 1024;
  const stageLabels = {
    uploading: "正在上传到识别服务…",
    uploaded: "附件已上传，正在提交给 Agent…",
    agent_submitted: "已交给 Agent，等待图片识别与证据核查…",
    vision_reading: "图片理解工具正在读取本次检验单…",
    checking_evidence: "正在核对本次读数的参考依据…",
    complete: "已收到结构化识别结果",
  };
  function endpoint() {
    const config = window.MEDTRACE_CONFIG || {};
    if (config.imageApiBase) {
      const base = new URL(config.imageApiBase, location.href);
      if (base.protocol !== "https:" && base.origin !== location.origin) {
        throw new Error("公网图片接口需要 HTTPS 地址，请由部署人员检查配置。");
      }
      return `${base.href.replace(/\/$/, "")}/api/analyze-image`;
    }
    if (config.mode === "api") return "/api/analyze-image";
    throw new Error("共享页的图片识别服务尚未接通，当前文件仅在本机预览。可在“关于本演示”填写团队后端地址，或使用演示样本。");
  }
  function validate(file) {
    if (!file.size) throw new Error("文件为空，请重新选择。");
    if (file.size > maxBytes) throw new Error("单个文件不能超过 10 MB。");
    if (!/\.(png|jpe?g|webp|pdf)$/i.test(file.name) || (file.type && !["image/png", "image/jpeg", "image/webp", "application/pdf"].includes(file.type))) {
      throw new Error("请选择 JPG、PNG、WebP 图片或 PDF 文件。");
    }
  }
  function checkResult(result) {
    if (!result || !["pass", "review", "abstain"].includes(result.decision_gate) ||
        typeof result.answer !== "string" || !Array.isArray(result.citations) ||
        !Array.isArray(result.lab_results || result.items) || !Array.isArray(result.trace_log) ||
        !Number.isFinite(result.confidence) || result.confidence < 0 || result.confidence > 1 ||
        !result.metadata || !Array.isArray(result.conflicts) || !result.source_versions ||
        typeof result.next_action !== "string" || typeof result.evidence_status !== "string") {
      throw new Error("图片接口未返回完整的结构化门控结果，暂不显示解读。");
    }
  }
  async function analyze(file, payload, onStage) {
    validate(file);
    const url = endpoint(); // Fail before sending any bytes if not configured.
    const data = new FormData();
    // Avoid forwarding a patient name from the local filename to the proxy.
    const extension = file.name.split(".").pop().toLowerCase();
    data.append("file", file, `report.${extension}`);
    data.append("raw_text", payload.raw_text || "");
    data.append("medications", payload.medications || "");
    data.append("gender", payload.patient_info?.gender || "未知");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 150000);
    let reader;
    try {
      const response = await fetch(url, { method: "POST", body: data, signal: controller.signal, credentials: "omit" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || `图片接口请求失败（HTTP ${response.status}）。`);
      }
      if (!response.headers.get("content-type")?.includes("application/x-ndjson") || !response.body) {
        throw new Error("图片接口返回协议不正确，请后端检查配置。");
      }
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "", received = 0;
      function consume(line) {
        if (!line.trim()) return null;
        const event = JSON.parse(line);
        if (event.type === "error") throw new Error(event.error || "图片识别失败，请稍后重试。");
        if (event.type === "stage" && stageLabels[event.stage]) onStage(event.stage, stageLabels[event.stage]);
        if (event.type === "result") {
          checkResult(event.result);
          onStage("complete", stageLabels.complete);
          return event.result;
        }
        return null;
      }
      while (true) {
        const { done, value } = await reader.read();
        if (value) received += value.byteLength;
        if (received > 2 * 1024 * 1024) throw new Error("图片接口返回数据过大，请后端检查。");
        pending += decoder.decode(value || new Uint8Array(), { stream: !done });
        let end;
        while ((end = pending.indexOf("\n")) !== -1) {
          const result = consume(pending.slice(0, end));
          pending = pending.slice(end + 1);
          if (result) return result;
        }
        if (done) {
          const result = consume(pending);
          if (result) return result;
          throw new Error("连接已结束，但没有收到识别结果。文件已保留，可重试。");
        }
      }
    } catch (error) {
      if (error.name === "AbortError") throw new Error("图片识别等待超时，文件已保留，可稍后重试。");
      if (error instanceof TypeError) throw new Error("无法连接图片服务，请检查网络与后端跨域配置。文件已保留。");
      if (error instanceof SyntaxError) throw new Error("图片接口返回了无法解析的数据，请后端核对协议。");
      throw error;
    } finally {
      clearTimeout(timeout);
      if (reader) await reader.cancel().catch(() => {});
    }
  }
  return { validate, analyze };
})();
