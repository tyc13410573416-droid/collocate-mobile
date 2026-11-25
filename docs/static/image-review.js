/* Review always asks the backend to re-evaluate confirmed fields. */
window.MEDTRACE_REVIEW = (() => {
  let current = null, busy = false;
  const editor = document.getElementById("imageReviewEditor");
  const rows = document.getElementById("imageReviewRows");
  const tooltip = document.getElementById("metricSourceTooltip");
  const sourceDialog = document.getElementById("metricSourceDialog");
  let activeSource = null;
  function hideTooltip() { activeSource = null; tooltip.classList.add("hidden"); }
  function node(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }
  function render(result) {
    current = result;
    editor.classList.add("hidden");
    const isImage = result.transport === "nexent-image-http";
    document.querySelector(".gate-demo-picker").hidden = isImage;
    const canEdit = Boolean(result.review_context?.token && result.lab_results?.length);
    document.getElementById("gateReviewActions").classList.toggle("hidden", !isImage || result.decision_gate === "abstain");
    document.getElementById("editImageValues").textContent = canEdit ? "手动核对数值" : "重新选择清晰图片";
    const hasInfoIssue = result.review_issues?.some(item => ["gender", "report_conditions"].includes(item.field)) || result.evidence_status === "missing_info";
    document.getElementById("completeImageInfo").classList.toggle("hidden", !hasInfoIssue && result.decision_gate === "pass");
    const list = document.getElementById("gateReviewIssues");
    list.replaceChildren();
    const issues = result.review_issues || (result.image_transcription?.uncertain_fields || []).map(detail => ({detail}));
    if (result.decision_gate === "review") issues.forEach(issue => list.append(node("li", "", issue.detail)));
    if (isImage && result.decision_gate === "review" && result.evidence_status === "low_confidence") {
      result.review_message = "部分指标读数、单位或关键信息尚未确认，系统已触发安全拦截，暂不作确定性异常方向判定。请核对下列项目后重新提交。";
    }
    const scope = document.getElementById("reviewScopeNote");
    scope.classList.toggle("hidden", !result.review_summary);
    if (result.review_summary) {
      const info = result.review_summary;
      const excluded = info.excluded_indicators?.length ? `未纳入：${info.excluded_indicators.join("、")}。` : "";
      scope.textContent = `人工核对已提交 · 本次仅核查 ${info.selected_count} 项。${excluded}原图其他项目仍需核对，原始识别记录已保留。`;
    }
  }
  function openEditor(info = false) {
    if (busy || !current) return;
    if (!current.review_context?.token || !current.lab_results?.length) {
      if (info) { openGenderDialog(); return; }
      fileInput.click(); return;
    }
    rows.replaceChildren();
    document.getElementById("reviewGender").value = current.patient_info?.gender || "未知";
    document.getElementById("reviewConditions").value = current.metadata?.report_conditions || "unknown";
    document.getElementById("reviewScopeConfirmed").checked = Boolean(current.metadata?.human_verified);
    document.getElementById("reviewQuickGender").classList.toggle("hidden", current.patient_info?.gender === "男" || current.patient_info?.gender === "女");
    document.getElementById("imageReviewError").classList.add("hidden");
    (current.review_candidates || current.lab_results).forEach((item, index) => {
      const row = node("fieldset", "image-review-row"); row.dataset.code = item.abbreviation;
      const legend = node("legend", "", `${item.abbreviation} · ${item.test_name}`);
      const fields = node("div", "review-row-fields");
      const compareLabel = node("label", "", "不等号");
      const compare = node("select"); compare.dataset.field = "comparator";
      [["","无"],["<","<"],[">",">"],["≤","≤"],["≥","≥"]].forEach(([value,text]) => {const option=node("option","",text); option.value=value; compare.append(option);});
      compare.value = item.value_comparator || ""; compareLabel.append(compare);
      const valueLabel = node("label", "", "读数");
      const value = node("input"); value.type="number"; value.step="any"; value.inputMode="decimal"; value.value=item.value ?? ""; value.dataset.field="value"; valueLabel.append(value);
      const unitLabel = node("label", "", "原单单位");
      const unit = node("input"); unit.type="text"; unit.maxLength=32; unit.value=item.unit || ""; unit.dataset.field="unit"; unitLabel.append(unit);
      fields.append(compareLabel,valueLabel,unitLabel);
      const confirm = node("label", "review-row-confirm");
      const checkbox = node("input"); checkbox.type="checkbox"; checkbox.dataset.field="confirmed"; checkbox.id=`reviewConfirm${index}`;
      checkbox.checked=Boolean(current.metadata?.human_verified && current.lab_results.some(row=>row.abbreviation === item.abbreviation));
      fields.addEventListener("input",()=>{checkbox.checked=false;document.getElementById("reviewScopeConfirmed").checked=false;});
      confirm.append(checkbox,node("span","","已对照原图核对，将此项纳入重新核查"));
      row.append(legend,fields,confirm); rows.append(row);
    });
    editor.classList.remove("hidden"); editor.scrollIntoView({behavior:"smooth",block:"start"});
    if(info) document.getElementById(current.clarification?.field === "report_conditions" ? "reviewConditions" : "reviewGender").focus();
    else rows.querySelector('input[type="number"]')?.focus({preventScroll:true});
  }
  document.getElementById("editImageValues").addEventListener("click",()=>openEditor());
  function completeInfo() {
    if(current?.clarification?.field === "gender" && current.evidence_status === "missing_info" && !current.metadata?.human_verified)openGenderDialog();
    else openEditor(true);
  }
  document.getElementById("completeImageInfo").addEventListener("click",completeInfo);
  document.getElementById("closeImageReview").addEventListener("click",()=>editor.classList.add("hidden"));
  document.querySelectorAll("[data-review-sex]").forEach(button=>button.addEventListener("click",()=>{
    document.getElementById("reviewGender").value=button.dataset.reviewSex;
    if(current?.metadata?.human_verified && current.clarification?.field === "gender" && document.getElementById("reviewScopeConfirmed").checked)
      document.getElementById("imageReviewForm").requestSubmit();
    else document.getElementById("reviewScopeConfirmed").focus();
  }));
  document.getElementById("imageReviewForm").addEventListener("submit",async event=>{
    event.preventDefault(); if(busy || !current?.review_context) return;
    const errorNode=document.getElementById("imageReviewError"); errorNode.classList.add("hidden");
    const entries=Array.from(rows.children).filter(row=>row.querySelector('[data-field="confirmed"]').checked).map(row=>({
      abbreviation:row.dataset.code, value:Number(row.querySelector('[data-field="value"]').value),
      unit:row.querySelector('[data-field="unit"]').value.trim(), value_comparator:row.querySelector('[data-field="comparator"]').value, confirmed:true,
      empty:!row.querySelector('[data-field="value"]').value.trim(),
    }));
    if(!entries.length || entries.some(item=>item.empty || !Number.isFinite(item.value) || !item.unit)) {
      errorNode.textContent="请勾选至少一个已核对项目，并填写有效读数和原单单位。"; errorNode.classList.remove("hidden"); return;
    }
    entries.forEach(item=>delete item.empty);
    busy=true; submitButton.disabled=true; setGateBusy(true);
    const controls=Array.from(editor.querySelectorAll("input,select,button")); controls.forEach(control=>control.disabled=true);
    const save=document.getElementById("submitImageReview"); save.textContent="正在重新核查…";
    try {
      const result=await window.MEDTRACE_IMAGES.review({review_token:current.review_context.token,lab_results:entries,
        gender:document.getElementById("reviewGender").value,report_conditions:document.getElementById("reviewConditions").value,
        scope_confirmed:document.getElementById("reviewScopeConfirmed").checked});
      genderInput.value=result.patient_info?.gender === "未知" ? "" : result.patient_info?.gender || "";
      renderResult(result); transportStatus.textContent="人工核对已重新核查";
      if (!window.MEDTRACE_FLOW?.isMobile()) resultPanel.scrollIntoView({behavior:"smooth",block:"start"});
    } catch(error) {errorNode.textContent=error.message; errorNode.classList.remove("hidden");}
    finally {busy=false; submitButton.disabled=false; setGateBusy(false); controls.forEach(control=>control.disabled=false); save.textContent="提交核对并重新解读";}
  });
  function showSource(citation,item) {
    hideTooltip(); document.getElementById("metricSourceTitle").textContent=`${item.abbreviation} 的参考依据`;
    const body=document.getElementById("metricSourceBody"); body.replaceChildren();
    body.append(node("p","source-detail-title",citation.title || citation.source_id),node("p","",citation.excerpt || citation.reference_range || "具体条目尚未提供。"));
    if(citation.version) body.append(node("p","source-detail-meta",`知识库版本标签：${citation.version}`));
    body.append(node("p","source-detail-note",citation.original_text_available === true ? "以上为已提供的来源摘录。" : "以上是当前知识库的参考条目摘要，不是标准原文逐字引用。原文页码及适用条件仍需核验。"));
    if(citation.version_note) body.append(node("p","source-detail-meta",citation.version_note));
    if(!sourceDialog.open) sourceDialog.showModal();
  }
  function appendCitations(card,item,result) {
    const ids=item.citation_ids || item.sources || [];
    const matches=(result.citations || []).filter(c=>(Array.isArray(ids)&&ids.some(id=>id===c.id || (id&&typeof id==="object"&&(id.source_id===c.source_id || id.id===c.id)))) ||
      (c.indicator && c.indicator===item.abbreviation) || (!c.indicator && item.source_id && c.source_id===item.source_id));
    if(!matches.length) return;
    const line=node("div","metric-source-links"); line.append(node("span","","参考依据"));
    matches.forEach(citation=>{
      const button=node("button","metric-source-button",`[${citation.id || "来源"}]`); button.type="button";
      button.setAttribute("aria-label",`${item.abbreviation} ${citation.id || "来源"}：查看参考依据`);
      button.setAttribute("aria-describedby","metricSourceTooltip");
      const show=()=>{
        activeSource = {button, show};
        tooltip.textContent=`${item.abbreviation} · ${citation.title || citation.source_id}\n${citation.excerpt || citation.reference_range || "具体条目待补充"}`;
        tooltip.classList.remove("hidden");
        const rect=button.getBoundingClientRect(), width=Math.min(360,innerWidth-32);
        tooltip.style.width=`${width}px`; tooltip.style.left=`${Math.max(16,Math.min(rect.left,innerWidth-width-16))}px`;
        const height=tooltip.getBoundingClientRect().height;
        tooltip.style.top=`${rect.top>height+16?rect.top-height-8:Math.max(16,Math.min(rect.bottom+8,innerHeight-height-16))}px`;
      };
      button.addEventListener("mouseenter",show); button.addEventListener("focus",show);
      button.addEventListener("mouseleave",hideTooltip); button.addEventListener("blur",hideTooltip);
      button.addEventListener("click",()=>showSource(citation,item)); line.append(button);
    }); card.append(line);
  }
  document.getElementById("closeMetricSource").addEventListener("click",()=>sourceDialog.close());
  sourceDialog.addEventListener("click",event=>{if(event.target===sourceDialog)sourceDialog.close();});
  window.addEventListener("scroll",()=>{
    if(activeSource && (activeSource.button.matches(":hover") || document.activeElement === activeSource.button)) activeSource.show();
    else hideTooltip();
  },{passive:true});
  return {render,appendCitations,completeInfo};
})();
