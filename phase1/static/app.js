const form = document.getElementById("analyzeForm");
const submitButton = document.getElementById("submitButton");
const transportStatus = document.getElementById("transportStatus");
const emptyState = document.getElementById("emptyState");
const loadingState = document.getElementById("loadingState");
const resultPanel = document.getElementById("resultPanel");
const errorBanner = document.getElementById("errorBanner");
const reportIdInput = document.getElementById("reportId");
const rawTextInput = document.getElementById("rawText");
const medicationsInput = document.getElementById("currentMedications");
const fileInput = document.getElementById("reportFile");
const fileName = document.getElementById("fileName");
const dropZone = document.getElementById("dropZone");
const agentTimeline = document.getElementById("agentTimeline");
const graphModal = document.getElementById("graphModal");

function resizeTextarea(element) {
  if (!element) return;
  element.style.height = "auto";
  element.style.height = `${element.scrollHeight}px`;
  element.style.overflowY = "hidden";
}

function resizeInputTextareas() {
  resizeTextarea(rawTextInput);
  resizeTextarea(medicationsInput);
}

const sampleTexts = {
  R001: `合成检验单 R001\nALT 68 IU/L（参考范围 0—40）\nAST 35 U/L（参考范围 0—40）\n血红蛋白 11.8 g/dL（参考范围 120—160 g/L）\n白细胞 6.2 ×10^9/L（参考范围 4—10）\n空腹血糖 5.4 mmol/L（参考范围 3.9—6.1）`,
  R002: `合成检验单 R002\nALT 32 U/L（参考范围 0—40）\nAST 45 IU/L（参考范围 0—40）\n血红蛋白 132 g/L（参考范围 120—160）\n白细胞 3.7 10^9/L（参考范围 4—10）\n空腹血糖 6.4 mmol/L（参考范围 3.9—6.1）`,
  R003: `合成检验单 R003\nALT 40 U/L（参考范围 0—40）\nAST 38 U/L（参考范围 0—40）\n血红蛋白 145 g/L（参考范围 120—160）\n白细胞 7.1 10^9/L（参考范围 4—10）\n空腹血糖 4.8 mmol/L（参考范围 3.9—6.1）`,
  R004: `患者男，45岁。今日查血化验结果显示：丙氨酸氨基转移酶（ALT）为 68 U/L，参考范围是 9-50 U/L；天门冬氨酸氨基转移酶（AST）为 35 U/L，参考范围是 15-40 U/L。患者自述目前正在规律服用阿托伐他汀钙片。`,
  R005: `患者女，52岁。来源冲突测试：丙氨酸氨基转移酶（ALT）为 68 U/L，参考范围是 9-50 U/L。知识库中两份演示标准对该指标参考范围存在冲突。患者目前未提供用药信息。`,
  R012: `患者男，45岁。谷丙转氨酶（ALT）为 200 U/L，参考范围是 9-50 U/L。`,
};
const sampleMedications = {
  R001: "阿托伐他汀 10 mg（合成演示用药）",
  R002: "二甲双胍 500 mg（合成演示用药）",
  R003: "",
  R004: "",
  R005: "",
  R012: "",
};

function escapeText(value) {
  return String(value ?? "");
}

function statusLabel(status) {
  return ({ high: "偏高", low: "偏低", normal: "正常", unknown: "待核查" })[status] || status || "待核查";
}

function traceStatusLabel(status) {
  return ({ done: "完成", success: "完成", running: "运行中", failed: "失败", error: "失败" })[status] || status || "完成";
}

function loadSample(reportId) {
  const id = sampleTexts[reportId] ? reportId : "R001";
  reportIdInput.value = id;
  rawTextInput.value = sampleTexts[id];
  medicationsInput.value = sampleMedications[id] || "";
  resizeInputTextareas();
  fileName.textContent = `已载入合成样例 ${id}`;
  document.querySelectorAll(".sample-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.report === id);
  });
}

document.querySelectorAll(".sample-button").forEach((button) => {
  button.addEventListener("click", () => loadSample(button.dataset.report));
});

document.getElementById("quickUpload")?.addEventListener("click", () => fileInput?.click());
document.getElementById("quickText")?.addEventListener("click", () => {
  rawTextInput?.scrollIntoView({ behavior: "smooth", block: "center" });
  rawTextInput?.focus();
});
document.getElementById("quickCase")?.addEventListener("click", () => {
  loadSample("R004");
  rawTextInput?.scrollIntoView({ behavior: "smooth", block: "center" });
});

document.getElementById("clearInput")?.addEventListener("click", () => {
  reportIdInput.value = "";
  rawTextInput.value = "";
  medicationsInput.value = "";
  resizeInputTextareas();
  fileInput.value = "";
  fileName.textContent = "也可以直接粘贴下方报告文本";
  document.querySelectorAll(".sample-button").forEach((button) => button.classList.remove("active"));
});

fileInput?.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  const match = file.name.match(/R00[1-5]/i);
  const reportId = match ? match[0].toUpperCase() : "R001";
  loadSample(reportId);
  fileName.textContent = `${file.name} · 已载入演示文本`;
});

["dragenter", "dragover"].forEach((eventName) => dropZone?.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropZone.classList.add("dragover");
}));
["dragleave", "drop"].forEach((eventName) => dropZone?.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragover");
}));
dropZone?.addEventListener("drop", (event) => {
  const file = event.dataTransfer?.files?.[0];
  if (!file) return;
  fileInput.files = event.dataTransfer.files;
  fileInput.dispatchEvent(new Event("change"));
});

[rawTextInput, medicationsInput].forEach((element) => {
  element?.addEventListener("input", () => resizeTextarea(element));
});
resizeInputTextareas();

function renderResult(result) {
  emptyState.classList.add("hidden");
  loadingState.classList.add("hidden");
  errorBanner.classList.add("hidden");
  resultPanel.classList.remove("hidden");
  document.getElementById("requestId").textContent = result.request_id || "已生成";
  document.getElementById("answer").textContent = result.answer || "未返回摘要";
  document.getElementById("disclaimer").textContent = result.disclaimer || "";

  const answerCitations = document.getElementById("answerCitations");
  answerCitations.replaceChildren();
  (result.citations || []).slice(0, 4).forEach((citation) => {
    const link = document.createElement("a");
    link.href = `#source-${escapeText(citation.source_id)}`;
    link.textContent = citation.id || "来源";
    link.title = citation.excerpt || "查看来源";
    answerCitations.append(link);
  });

  const schemaSummary = document.getElementById("schemaSummary");
  const patientFields = document.getElementById("patientFields");
  const medicationsSummary = document.getElementById("medicationsSummary");
  const confidenceBadge = document.getElementById("confidenceBadge");
  const confidenceAlert = document.getElementById("confidenceAlert");
  const patientInfo = result.patient_info || {};
  const medicationList = Array.isArray(result.medications) ? result.medications : [];
  const confidenceValue = Number((result.metadata || {}).extraction_confidence);
  patientFields?.replaceChildren();
  medicationsSummary?.replaceChildren();
  const hasPatientSchema = patientInfo.age != null || (patientInfo.gender && patientInfo.gender !== "未知") || medicationList.length > 0;
  if (hasPatientSchema) {
    schemaSummary?.classList.remove("hidden");
    [["年龄", patientInfo.age == null ? "未提取" : `${patientInfo.age} 岁`], ["性别", patientInfo.gender || "未知"]].forEach(([label, value]) => {
      const field = document.createElement("span");
      field.className = "patient-field";
      field.textContent = `${label}：${value}`;
      patientFields?.append(field);
    });
    medicationList.forEach((medication) => {
      const tag = document.createElement("span");
      tag.className = "medication-tag";
      tag.textContent = medication.drug_name || medication.drug || "未命名药物";
      medicationsSummary?.append(tag);
    });
    if (!medicationList.length) {
      const emptyMedication = document.createElement("span");
      emptyMedication.className = "patient-field muted-field";
      emptyMedication.textContent = "当前用药：未提取";
      medicationsSummary?.append(emptyMedication);
    }
  } else {
    schemaSummary?.classList.add("hidden");
  }
  if (Number.isFinite(confidenceValue)) {
    const percent = Math.round(confidenceValue * 100);
    confidenceBadge.textContent = `提取置信度 ${percent}%`;
    confidenceBadge.className = `confidence-badge ${confidenceValue < 0.8 ? "low" : "good"}`;
    if (confidenceValue < 0.8) {
      confidenceAlert.textContent = `提取置信度 ${percent}% 低于 80%，需人工核对患者信息、检验项目和用药名称。`;
      confidenceAlert.classList.remove("hidden");
    } else {
      confidenceAlert.classList.add("hidden");
    }
  } else {
    confidenceBadge?.classList.add("hidden");
    confidenceAlert?.classList.add("hidden");
  }

  const decisionGate = document.getElementById("decisionGate");
  const gateBadge = document.getElementById("gateBadge");
  const gateAction = document.getElementById("gateAction");
  const gateConflicts = document.getElementById("gateConflicts");
  const gate = result.decision_gate;
  if (gate && decisionGate) {
    const gateLabels = { pass: "通过", review: "需人工复核", abstain: "暂不输出" };
    const evidenceLabels = { consistent: "证据一致", conflict: "检测到来源冲突", missing: "证据不完整" };
    decisionGate.className = `decision-gate ${gate}`;
    gateBadge.textContent = `${gateLabels[gate] || gate} · ${evidenceLabels[result.evidence_status] || result.evidence_status || "待判断"}`;
    gateAction.textContent = result.next_action || "请结合原始报告和专业人员意见复核。";
    gateConflicts.replaceChildren();
    (result.conflicts || []).forEach((conflict) => {
      const item = document.createElement("div");
      item.className = "gate-conflict";
      item.textContent = `${conflict.field || "字段"}：${conflict.detail || "来源存在差异"}`;
      gateConflicts.append(item);
    });
  } else {
    decisionGate?.classList.add("hidden");
  }

  const warningsBlock = document.getElementById("warningsBlock");
  const warnings = document.getElementById("warnings");
  warnings.replaceChildren();
  if ((result.warnings || []).length) {
    warningsBlock.classList.remove("hidden");
    result.warnings.forEach((warning) => {
      const card = document.createElement("div");
      card.className = "warning-card";
      const drug = document.createElement("div");
      drug.className = "warning-drug";
      drug.textContent = `当前用药：${escapeText(warning.drug)}`;
      const reason = document.createElement("div");
      reason.className = "warning-reason";
      reason.textContent = warning.risk || "需要进一步核查";
      const source = document.createElement("div");
      source.className = "warning-source";
      const sourceText = warning.source || (Array.isArray(warning.sources) ? warning.sources.join("、") : "待补充来源");
      source.textContent = `依据：${sourceText}`;
      card.append(drug, reason, source);
      warnings.append(card);
    });
  } else {
    warningsBlock.classList.add("hidden");
  }

  const normalizationBlock = document.getElementById("normalizationBlock");
  const normalizationRows = document.getElementById("normalizationRows");
  normalizationRows?.replaceChildren();
  const normalizationItems = Array.isArray(result.normalization) ? result.normalization : [];
  if (normalizationItems.length && normalizationBlock) {
    normalizationBlock.classList.remove("hidden");
    normalizationItems.forEach((item) => {
      const row = document.createElement("div");
      row.className = `normalization-row ${item.status === "review" ? "review" : ""}`;
      const detail = document.createElement("span");
      const original = item.original_value == null ? "—" : `${item.original_value} ${item.original_unit || ""}`;
      const converted = item.value == null ? (item.message || "待人工核对") : `${item.value} ${item.unit || ""}`;
      const indicator = document.createElement("strong");
      indicator.textContent = item.indicator || "指标";
      detail.append(indicator, document.createTextNode(` · ${original} → ${converted}`));
      const status = document.createElement("span");
      status.className = "normalization-status";
      status.textContent = item.status === "pass" ? "已标准化" : "需核对";
      row.append(detail, status);
      normalizationRows.append(row);
    });
  } else {
    normalizationBlock?.classList.add("hidden");
  }

  const metrics = document.getElementById("metrics");
  metrics.replaceChildren();
  const labResults = Array.isArray(result.lab_results) ? result.lab_results : (result.items || []);
  labResults.forEach((item) => {
    const card = document.createElement("div");
    card.className = "metric";
    const name = document.createElement("div");
    name.className = "metric-name";
    name.textContent = `${escapeText(item.test_name || item.indicator_name)} · ${escapeText(item.abbreviation || item.indicator_code)}`;
    const value = document.createElement("div");
    value.className = `metric-value ${escapeText(item.status)}`;
    const reading = document.createElement("span");
    reading.className = "metric-reading";
    reading.textContent = escapeText(item.value);
    const unit = document.createElement("span");
    unit.className = "metric-unit";
    unit.textContent = escapeText(item.unit);
    const status = document.createElement("span");
    status.className = `status-chip ${escapeText(item.status)}`;
    status.textContent = statusLabel(item.status);
    const reference = document.createElement("div");
    reference.className = "metric-reference";
    const range = item.reference_range;
    const rangeText = typeof range === "string" ? range : (range && range.low != null && range.high != null ? `${range.low}—${range.high}` : "未提供");
    reference.textContent = `参考范围：${rangeText}`;
    value.append(reading, unit, status);
    card.append(name, value, reference);
    metrics.append(card);
  });

  const reasoning = document.getElementById("reasoning");
  reasoning.replaceChildren();
  (result.reasoning || []).forEach((step) => {
    const card = document.createElement("div");
    card.className = "reasoning-step";
    const index = document.createElement("div");
    index.className = "reasoning-index";
    index.textContent = step.step || "01";
    const title = document.createElement("div");
    title.className = "reasoning-title";
    title.textContent = step.title || "处理步骤";
    const detail = document.createElement("div");
    detail.className = "reasoning-detail";
    detail.textContent = step.detail || "";
    card.append(index, title, detail);
    reasoning.append(card);
  });

  const retrievalSummary = document.getElementById("retrievalSummary");
  const retrievalSources = document.getElementById("retrievalSources");
  retrievalSummary.replaceChildren();
  retrievalSources.replaceChildren();
  const retrieval = result.retrieval || {};
  [[retrieval.vector_hits, "向量召回"], [retrieval.keyword_hits, "关键词召回"], [retrieval.reranked, "重排后引用"]].forEach(([value, label]) => {
    const stat = document.createElement("div");
    stat.className = "retrieval-stat";
    const number = document.createElement("b");
    number.textContent = value ?? "—";
    const caption = document.createElement("span");
    caption.textContent = label;
    stat.append(number, caption);
    retrievalSummary.append(stat);
  });
  (retrieval.sources || []).forEach((source) => {
    const row = document.createElement("div");
    row.className = "retrieval-source";
    const label = document.createElement("span");
    label.textContent = source.title || "来源文档";
    const track = document.createElement("div");
    track.className = "score-track";
    const score = document.createElement("span");
    score.style.width = `${Math.round(Number(source.score || 0) * 100)}%`;
    track.append(score);
    row.append(label, track);
    retrievalSources.append(row);
  });

  const evidence = result.knowledge_evidence || {};
  document.getElementById("rawJsonEvidence").textContent = evidence.raw_json || "暂无抽取证据";
  document.getElementById("evidenceNote").textContent = evidence.review_note || "";
  const checkedFields = document.getElementById("checkedFields");
  checkedFields.replaceChildren();
  (evidence.checked_fields || []).forEach((field) => {
    const item = document.createElement("li");
    item.textContent = field;
    checkedFields.append(item);
  });
  renderGraph(result.graph || { nodes: [], edges: [] });
  agentTimeline?.querySelectorAll(".agent-step").forEach((step) => step.classList.add("done"));

  const trace = document.getElementById("trace");
  trace.replaceChildren();
  const traceSteps = result.trace_log || result.trace || [];
  traceSteps.forEach((step) => {
    const li = document.createElement("li");
    if (typeof step === "object" && step !== null) {
      const tool = step.tool || step.name || "工具调用";
      const status = step.status || "done";
      const elapsed = step.elapsed_ms == null ? "" : ` · ${step.elapsed_ms} ms`;
      li.textContent = `${tool} · ${traceStatusLabel(status)}${elapsed}`;
    } else {
      li.textContent = step;
    }
    trace.append(li);
  });

  const meta = result.meta || {};
  const modelMeta = document.getElementById("modelMeta");
  if (modelMeta) {
    const pieces = [];
    if (meta.llm_model) pieces.push(`LLM ${meta.llm_model}`);
    if (meta.embedding_model) pieces.push(`向量 ${meta.embedding_model}`);
    if (meta.rag_config_count != null) pieces.push(`RAG ${meta.rag_config_count} 条`);
    modelMeta.textContent = pieces.join("  ·  ");
    modelMeta.classList.toggle("hidden", pieces.length === 0);
  }

  const sources = document.getElementById("sources");
  sources.replaceChildren();
  (result.citations || []).forEach((citation) => {
    const card = document.createElement("article");
    card.className = "source-card";
    card.id = `source-${escapeText(citation.source_id)}`;
    const title = document.createElement("div");
    title.className = "source-title";
    const anchor = document.createElement("a");
    anchor.href = `#source-${escapeText(citation.source_id)}`;
    anchor.textContent = citation.id || "来源";
    const label = document.createElement("span");
    label.textContent = citation.title || "合成样本";
    title.append(anchor, label);
    const excerpt = document.createElement("p");
    excerpt.className = "source-excerpt";
    excerpt.textContent = citation.excerpt || "";
    card.append(title, excerpt);
    sources.append(card);
  });
}

function resetAgentTimeline() {
  agentTimeline?.querySelectorAll(".agent-step").forEach((step) => step.classList.remove("active", "done"));
}

function animateAgentTimeline() {
  resetAgentTimeline();
  const steps = Array.from(agentTimeline?.querySelectorAll(".agent-step") || []);
  steps.forEach((step, index) => {
    setTimeout(() => {
      step.classList.add("active");
      if (index > 0) steps[index - 1].classList.remove("active");
      if (index > 0) steps[index - 1].classList.add("done");
    }, index * 650);
  });
}

function renderGraph(graph) {
  const svg = document.getElementById("graphSvg");
  if (!svg) return;
  svg.replaceChildren();
  const ns = "http://www.w3.org/2000/svg";
  const positions = { indicator: [130, 135], reference: [360, 70], medication: [590, 155] };
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));
  edges.forEach((edge) => {
    const source = positions[edge.source] || [130, 135];
    const target = positions[edge.target] || [590, 155];
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", source[0]); line.setAttribute("y1", source[1]);
    line.setAttribute("x2", target[0]); line.setAttribute("y2", target[1]);
    line.setAttribute("class", "graph-edge");
    svg.append(line);
    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", (source[0] + target[0]) / 2);
    text.setAttribute("y", (source[1] + target[1]) / 2 - 7);
    text.setAttribute("class", "graph-edge-label");
    text.textContent = edge.label || "关联";
    svg.append(text);
  });
  nodes.forEach((node) => {
    const [x, y] = positions[node.id] || [360, 135];
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", x); circle.setAttribute("cy", y); circle.setAttribute("r", 38);
    circle.setAttribute("class", `graph-node ${node.id}`);
    svg.append(circle);
    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", x); text.setAttribute("y", y + 4);
    text.setAttribute("class", "graph-node-label");
    text.textContent = node.label || byId[node.id]?.kind || node.id;
    svg.append(text);
  });
}

document.getElementById("openGraph")?.addEventListener("click", () => graphModal?.classList.remove("hidden"));
document.getElementById("closeGraph")?.addEventListener("click", () => graphModal?.classList.add("hidden"));
graphModal?.addEventListener("click", (event) => { if (event.target === graphModal) graphModal.classList.add("hidden"); });
document.querySelectorAll('a[href="#openGraph"]').forEach((link) => {
  link.addEventListener("click", () => setTimeout(() => document.getElementById("openGraph")?.click(), 0));
});

async function requestAnalysis(payload) {
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.error || `HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    const staticResults = window.MEDTRACE_STATIC_RESULTS || {};
    const staticResult = staticResults[payload.report_id];
    if (staticResult) {
      return { ...staticResult, transport: "github-pages-demo" };
    }
    throw error;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  submitButton.querySelector(".button-label").innerHTML = '<span class="button-spinner"></span>正在联调…';
  transportStatus.textContent = "请求处理中";
  transportStatus.className = "status-pill busy";
  resultPanel.classList.add("hidden");
  emptyState.classList.add("hidden");
  errorBanner.classList.add("hidden");
  loadingState.classList.remove("hidden");
  animateAgentTimeline();
  try {
    const result = await requestAnalysis({
      report_id: reportIdInput.value.trim(),
      raw_text: rawTextInput.value,
      medications: medicationsInput.value,
      options: { include_trace: true, include_retrieval: true, include_graph: true },
    });
    renderResult(result);
    transportStatus.textContent = result.transport === "nexent-http" ? "Nexent API 已联通" : (result.transport === "mock-nexent-http" ? "Mock API 已联通" : (result.transport === "github-pages-demo" ? "GitHub Pages 演示模式" : "本地演示模式"));
    transportStatus.className = "status-pill ready";
  } catch (error) {
    loadingState.classList.add("hidden");
    resultPanel.classList.add("hidden");
    emptyState.classList.add("hidden");
    errorBanner.textContent = `联调失败：${error.message}`;
    errorBanner.classList.remove("hidden");
    transportStatus.textContent = `请求失败：${error.message}`;
    transportStatus.className = "status-pill";
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector(".button-label").textContent = "生成带来源解读";
  }
});
