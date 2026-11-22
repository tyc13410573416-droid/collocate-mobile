// Static mode replays verified inputs. Real API errors never become demo answers.
window.MEDTRACE_DEMO = {
  analyze(payload) {
    const catalog = window.MEDTRACE_GATE_FIXTURES;
    const entry = catalog?.samples[payload.report_id];
    if (!entry || String(payload.raw_text || '').trim() !== entry.text.trim() || (payload.asset_id || '') !== entry.asset_id) {
      throw new Error('当前为样本演示模式。报告内容已修改，请重新选择演示案例；自定义报告需接入真实 API 后解读。');
    }
    const textGender = /女性|女|female\b/i.test(entry.text) ? '女' : /男性|男|\bmale\b/i.test(entry.text) ? '男' : '未知';
    const gender = payload.patient_info?.gender || textGender;
    const medications = String(payload.medications || '').trim();
    const fixture = catalog.variants[payload.report_id]?.[gender]?.[medications];
    if (!fixture) throw new Error('当前演示不支持这组用药输入，请重新选择样本。原始内容已保留。');
    return JSON.parse(JSON.stringify(fixture));
  },
};
