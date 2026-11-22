async (page) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const reports = [];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('http://127.0.0.1:8876/');
  for (const [id, state] of [['R012', 'pass'], ['R005', 'review'], ['R013', 'review'], ['R006', 'abstain']]) {
    await page.locator(`[data-gate-demo="${id}"]`).click();
    assert(await page.locator('#loadingState').isVisible(), `${id}: loading must be visible`);
    await page.waitForFunction((gate) => document.getElementById('resultPanel').dataset.gate === gate && !document.getElementById('resultPanel').classList.contains('hidden') && !document.getElementById('submitButton').disabled, state);
    if (id === 'R013') {
      assert(await page.locator('#genderDialog').isVisible(), 'missing_info must open a sex prompt');
      await page.locator('#deferGender').click();
    }
    const gate = await page.locator('#decisionGate').textContent();
    if (id === 'R005') {
      assert(await page.locator('.conflict-source').count() === 2, 'conflict must show two sources');
      assert(gate.includes('9–50') && gate.includes('7–40') && gate.includes('合成数据'), 'conflict ranges and synthetic label');
      assert(!(await page.locator('#clarificationBox').isVisible()), 'conflict must not display an unrelated sex prompt');
      assert(!(await page.locator('#assetPreview').isVisible()), 'no phantom image preview');
      assert(await page.locator('.status-chip.high').count() === 0, 'review must not colour a high result as definitive');
    }
    if (state === 'abstain') {
      assert(!(await page.locator('[data-gate-content]').isVisible()), 'abstain must hide all interpretation content');
      assert(await page.locator('#disclaimer').isVisible(), 'abstain disclaimer remains visible');
    }
    await page.locator('#auditPanel > summary').click();
    assert(await page.locator('#trace li').count() >= 4, 'audit timeline must have concrete steps');
    await page.locator('#decisionGate').scrollIntoViewIfNeeded();
    await page.screenshot({ path: `.playwright-cli/${id}-desktop.png` });
    reports.push({ id, state, title: await page.locator('#gateTitle').textContent() });
  }
  await page.locator('[data-gate-demo="R013"]').click();
  await page.locator('#genderDialog').waitFor({ state: 'visible' });
  await page.locator('#clarificationGender').selectOption('女');
  await page.getByRole('button', { name: '提交并重新解读' }).click();
  await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'pass' && !document.getElementById('submitButton').disabled);
  assert(await page.locator('#patientGender').inputValue() === '女', 'sex must persist in left form');
  assert((await page.locator('#patientFields').textContent()).includes('女'), 'result must show corrected sex');
  assert((await page.locator('.metric-reference').first().textContent()).includes('7-40'), 'sex correction must select female reference');
  assert(!(await page.locator('#genderDialog').isVisible()), 'corrected input must not prompt again');
  await page.locator('#answerCitations a').first().click();
  assert(await page.locator('#sources').isVisible(), 'clicking source must open source details');
  await page.locator('#quickCase').click();
  await page.waitForFunction(() => document.getElementById('reportId').value === 'R012' && !document.getElementById('submitButton').disabled);
  assert(await page.locator('#resultPanel').isVisible(), 'quick demo button must generate an actual result');
  await page.locator('#rawText').fill('这是一份新报告，ALT 999 U/L');
  await page.locator('#submitButton').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  assert(!(await page.locator('#resultPanel').isVisible()), 'edited input must not reuse a stale fixture');
  assert((await page.locator('#errorBanner').textContent()).includes('报告内容已修改'), 'edited fixture explains limitation');
  for (const width of [1024, 820, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator('[data-gate-demo="R005"]').click();
    await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'review' && !document.getElementById('submitButton').disabled);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `overflow at ${width}`);
    await page.locator('#decisionGate').scrollIntoViewIfNeeded();
    if (width === 390) {
      await page.screenshot({ path: '.playwright-cli/conflict-mobile.png' });
      await page.locator('[data-gate-demo="R013"]').click();
      await page.locator('#genderDialog').waitFor({ state: 'visible' });
      await page.screenshot({ path: '.playwright-cli/gender-mobile.png' });
      await page.locator('#clarificationGender').selectOption('男');
      await page.getByRole('button', { name: '提交并重新解读' }).click();
      await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'pass' && !document.getElementById('submitButton').disabled);
    }
  }
  // Failed real requests must stay errors, even if a fixture with the same id exists.
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => { window.MEDTRACE_CONFIG.mode = 'api'; });
  await page.route('**/api/analyze', (route) => route.fulfill({ status: 502, contentType: 'application/json', body: '{"error":"测试后端不可用"}' }));
  await page.locator('[data-gate-demo="R012"]').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  assert(!(await page.locator('#resultPanel').isVisible()), 'real failure cannot silently use demo answer');
  assert((await page.locator('#errorBanner').textContent()).includes('测试后端不可用'), 'real failure message');
  await page.unroute('**/api/analyze');
  assert(!errors.length, `JS errors: ${errors.join('; ')}`);
  return { passed: true, scenarios: reports, sexCorrection: true, staleInputBlocked: true, realApiFailureBlocked: true, widths: [1440, 1024, 820, 768, 390, 320], errors };
}
