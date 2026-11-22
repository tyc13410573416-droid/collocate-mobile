/* Four views of three backend gate values: the browser never promotes a real review to pass. */
const genderDialog = document.getElementById("genderDialog");
let lastGateResult = null;

function setGateBusy(busy) {
  document.querySelector(".output-card").setAttribute("aria-busy", String(busy));
  document.querySelectorAll("[data-gate-demo], .sample-button, .asset-button, .quick-action").forEach((button) => { button.disabled = busy; });
  document.querySelectorAll("#analyzeForm input, #analyzeForm textarea, #analyzeForm select").forEach((input) => { input.disabled = busy; });
}

function openGenderDialog() {
  document.getElementById("clarificationGender").value = genderInput.value;
  if (!genderDialog.open) genderDialog.showModal();
  document.getElementById("clarificationGender").focus();
}

function renderResult(result) {
  // Render raw readings neutrally until the server permits a definitive interpretation.
  const gate = ["pass", "review", "abstain"].includes(result.decision_gate) ? result.decision_gate : "review";
  const view = { ...result, decision_gate: gate };
  if (gate !== "pass") {
    view.lab_results = (result.lab_results || result.items || []).map((item) => ({ ...item, status: "unknown" }));
    view.reasoning = [];
    view.answer = gate === "review" ? "以下为本次报告的原始读数，暂不作异常方向判定。请先完成上方复核。" : "";
  }
  renderReportDetails(view);
  lastGateResult = result;
  resultPanel.dataset.gate = gate;
  document.querySelector("[data-gate-content]").hidden = gate === "abstain";
  const passOnly = [".reasoning-block", "#openGraph", ".retrieval-block", ".evidence-block"];
  passOnly.forEach((selector) => { document.querySelector(selector).hidden = gate !== "pass"; });
  const missingGender = gate === "review" && (result.evidence_status === "missing_info" || result.clarification?.field === "gender");
  const conflict = gate === "review" && result.evidence_status === "conflict";
  document.getElementById("decisionGate").className = `decision-gate ${gate}`;
  document.getElementById("gateSymbol").textContent = ({ pass: "✓", review: "!", abstain: "×" })[gate];
  document.getElementById("gateTitle").textContent = gate === "pass" ? "门控判定：通过" : gate === "abstain" ? "知识库未收录，无法提供解读" : missingGender ? "缺少关键信息" : "门控判定：需人工复核";
  const labels = { found: "证据已找到", consistent: "证据一致", conflict: "证据冲突", missing_info: "信息待补充", low_confidence: "数值待核对", missing: "依据不足" };
  document.getElementById("gateBadge").textContent = labels[result.evidence_status] || "待复核";
  document.getElementById("gateAction").textContent = gate === "abstain" ? (result.next_action || "当前没有可用检验依据，请咨询专业人员。") : conflict ? "来源参考区间不一致，请人工确认适用依据后再继续。" : (result.next_action || "请核对报告与来源依据。");
  document.getElementById("clarificationBox").classList.toggle("hidden", !missingGender);
  document.getElementById("clarificationPrompt").textContent = "该指标区分男女，请补充性别后重新解读。";
  document.getElementById("confidenceAlert").classList.toggle("hidden", result.evidence_status !== "low_confidence");
  document.getElementById("disclaimer").textContent = result.disclaimer || "本结果仅供辅助参考，不构成任何临床诊断或用药建议。医学决策请务必以执业医师意见为准。";
  document.querySelectorAll(".status-chip.unknown").forEach((tag) => { tag.textContent = "待复核"; });
  const container = document.getElementById("gateConflicts");
  container.replaceChildren();
  if (conflict) (result.conflicts || []).forEach((item) => renderConflict(item, result, container));
  document.getElementById("auditPanel").open = false;
  document.getElementById("auditMode").textContent = window.MEDTRACE_CONFIG.mode === "demo" || result.request_id?.startsWith("mock-") ? "演示判定记录" : "接口判定记录";
  // Do not flash a stale sex prompt after the user corrected it.
  if (missingGender) openGenderDialog();
}

function renderConflict(conflict, result, container) {
  const card = document.createElement("article");
  card.className = "conflict-comparison";
  const title = document.createElement("h4");
  title.textContent = conflict.synthetic ? "合成数据 · 参考区间差异" : "参考区间差异";
  const columns = document.createElement("div");
  columns.className = "conflict-columns";
  ["a", "b"].forEach((side, index) => {
    const sourceId = conflict[`source_${side}`] || conflict.sources?.[index] || `来源 ${side.toUpperCase()}`;
    const citation = (result.citations || []).find((entry) => entry.source_id === sourceId);
    const panel = document.createElement("div");
    panel.className = "conflict-source";
    const source = document.createElement("span");
    source.textContent = `来源 ${side.toUpperCase()} · ${sourceId}`;
    const range = document.createElement("strong");
    range.textContent = conflict[`range_${side}`] || citation?.range_display || citation?.reference_range || "区间见差异详情";
    const version = document.createElement("small");
    version.textContent = citation?.version ? `版本 ${citation.version}` : (conflict.synthetic ? "演示规则，非正式医学标准" : "请核对原始来源版本");
    panel.append(source, range, version);
    columns.append(panel);
  });
  const note = document.createElement("p");
  note.className = "conflict-note";
  note.textContent = conflict.detail || "两个来源给出的区间不同，当前停止确定性解读。";
  card.append(title, columns, note);
  container.append(card);
}

document.querySelectorAll("[data-gate-demo]").forEach((button) => {
  button.addEventListener("click", () => {
    if (submitButton.disabled) return;
    document.querySelectorAll("[data-gate-demo]").forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
    loadSample(button.dataset.gateDemo);
    form.requestSubmit();
  });
});
document.getElementById("applyGender").addEventListener("click", openGenderDialog);
document.getElementById("genderDialogForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const value = document.getElementById("clarificationGender").value;
  if (!value || submitButton.disabled) return;
  genderInput.value = value;
  genderDialog.close();
  form.requestSubmit();
});
["closeGenderDialog", "deferGender"].forEach((id) => document.getElementById(id).addEventListener("click", () => genderDialog.close()));
// Opening a reference must also open the collapsed source list.
document.getElementById("answerCitations").addEventListener("click", (event) => {
  if (event.target.closest("a")) document.querySelector(".sources-block").open = true;
});
// An edited input no longer describes the previous result.
[rawTextInput, medicationsInput, genderInput].forEach((input) => input.addEventListener("input", () => {
  if (!lastGateResult) return;
  resultPanel.classList.add("hidden");
  emptyState.classList.remove("hidden");
  emptyState.querySelector("strong").textContent = "输入已更新";
  emptyState.querySelector("span").textContent = "点击生成，按本次输入重新核对。";
}));
