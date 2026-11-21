// GitHub Pages fallback: enrich the existing static responses with the same
// stage-two evidence fields returned by the local Mock/Nexent adapter.
(function enrichStageTwoDemo() {
  const results = window.MEDTRACE_STATIC_RESULTS || {};
  Object.values(results).forEach((result) => {
    const items = Array.isArray(result.lab_results) ? result.lab_results : (result.items || []);
    result.normalization = items
      .filter((item) => item && item.value != null && item.unit)
      .map((item) => ({
        status: "pass",
        indicator: item.abbreviation || item.indicator_code || item.test_name || item.indicator_name || "指标",
        value: Number(item.value),
        unit: item.unit,
        original_value: Number(item.value),
        original_unit: item.unit,
        conversion: "identity",
        confidence: 1,
      }));
    const traceLog = Array.isArray(result.trace_log) ? result.trace_log : [];
    if (traceLog.length && !traceLog.some((step) => step && step.tool === "normalize")) {
      const index = traceLog.findIndex((step) => step && step.tool === "query_reference");
      traceLog.splice(index < 0 ? 1 : index, 0, { tool: "normalize", status: "done", elapsed_ms: 90 });
      result.trace_log = traceLog;
    }
    result.meta = { ...(result.meta || {}), stage2_tools: ["normalize", "check_interaction"] };
    result.disclaimer = "本结果仅供辅助参考，不构成任何临床诊断或用药建议。医学决策请务必以执业医师意见为准。";
    if (result.decision_gate === "review") {
      result.answer = `当前处于安全复核状态，暂不能给出确定的偏高、偏低或正常结论。复核原因：${result.next_action || "请核对原始报告和患者信息"}。请核对原始报告、患者信息和来源版本后再继续。`;
    } else if (result.decision_gate === "abstain") {
      result.answer = "当前输入缺少可用的检验依据，暂不输出确定性解读。建议补充原始报告并咨询专业人员。";
    } else if (Array.isArray(result.citations) && result.citations.length && !/\[来源/.test(result.answer || "")) {
      result.answer = `${result.answer || ""} [来源1]`;
    }
  });
})();
