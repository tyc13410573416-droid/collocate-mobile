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
  });
})();
