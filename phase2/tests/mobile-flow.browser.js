async (page) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const waitReady = async gate => {
    await page.waitForFunction(expected => document.getElementById('resultPanel').dataset.gate === expected &&
      !document.getElementById('resultPanel').classList.contains('hidden') && !document.getElementById('submitButton').disabled, gate);
  };
  const choose = async id => {
    if (await page.locator('#mobileBack').isVisible()) await page.locator('#mobileBack').click();
    await page.locator('#mobileExamples').evaluate(el => { el.open = true; });
    await page.locator(`[data-gate-demo="${id}"]`).click();
  };
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://127.0.0.1:8876/');
  await page.waitForFunction(() => Boolean(window.MEDTRACE_FLOW));
  assert(await page.locator('#analyzeForm').isVisible(), 'mobile starts with input');
  assert(!await page.locator('.output-card').isVisible(), 'empty output is not stacked under the input');
  assert(await page.locator('#gateDemoPicker').evaluate(el => Boolean(el.closest('#analyzeForm'))), 'demo choices are on input step');
  const dock = await page.locator('#submitButton').boundingBox();
  assert(dock.y >= 0 && dock.y + dock.height <= 844, 'generate button visible without scrolling');
  const mobileFields = ['#rawText', '#currentMedications', '#patientGender', '#reportId'];
  const saved = {};
  await choose('R012');
  assert(await page.locator('#loadingState').isVisible(), 'loading is visible on result step');
  assert(!await page.locator('#analyzeForm').isVisible(), 'input is hidden during loading');
  assert(await page.locator('#mobileBack').isDisabled(), 'cannot change input while request is running');
  await waitReady('pass');
  for (const selector of mobileFields) saved[selector] = await page.locator(selector).inputValue();
  assert(await page.evaluate(() => scrollY < 2), 'result starts at top, without scrolling through input');
  const banner = await page.locator('#decisionGate').boundingBox();
  assert(banner.y >= 0 && banner.y + banner.height < 844, 'gate banner is visible on first result screen');
  await page.locator('#mobileBack').click();
  for (const selector of mobileFields) assert(await page.locator(selector).inputValue() === saved[selector], selector + ' retained');
  assert(await page.locator('#rawText').evaluate(el => el.clientHeight >= el.scrollHeight - 1), 'return restores auto-sized text');

  await choose('R005');
  await waitReady('review');
  assert(await page.locator('.conflict-source').count() === 2, 'conflicting source details remain available');
  assert(!await page.locator('.input-card').isVisible(), 'review stays in result step');
  await choose('R013');
  await page.locator('#genderDialog').waitFor({ state: 'visible' });
  await page.locator('#clarificationGender').selectOption('女');
  await page.getByRole('button', { name: '提交并重新解读', exact: true }).click();
  await waitReady('pass');
  assert(await page.locator('#patientGender').inputValue() === '女', 'gender follow-up retained in input');
  assert(!await page.locator('.input-card').isVisible(), 'gender follow-up does not expose input screen');
  await choose('R006');
  await waitReady('abstain');
  assert(!await page.locator('[data-gate-content]').isVisible(), 'abstain hides interpretation');
  assert(await page.locator('#disclaimer').isVisible(), 'abstain keeps disclaimer');

  await page.locator('#mobileBack').click();
  await page.locator('#rawText').fill('这是一份修改后的报告，ALT 999 U/L');
  await page.locator('#submitButton').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.getElementById('submitButton').disabled);
  assert(await page.locator('#mobileRetry').isVisible(), 'error exposes retry');
  assert(!await page.locator('#resultPanel').isVisible(), 'errors do not show previous answer');
  assert(!await page.locator('#analyzeForm').isVisible(), 'error remains a clear result view');
  await page.locator('#mobileRetry').click();
  await page.waitForFunction(() => document.body.dataset.mobilePhase === 'error' && !document.getElementById('submitButton').disabled);
  await page.locator('#mobileBack').click();
  assert((await page.locator('#rawText').inputValue()).includes('999'), 'failed input is retained');

  for (const width of [320, 390, 768, 820]) {
    await page.setViewportSize({ width, height: 900 });
    await choose('R012');
    await waitReady('pass');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `result overflow at ${width}`);
    assert(!await page.locator('#analyzeForm').isVisible(), `input hidden at ${width}`);
    await page.locator('#mobileBack').click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `input overflow at ${width}`);
  }
  for (const width of [821, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert(await page.locator('#analyzeForm').isVisible() && await page.locator('.output-card').isVisible(), `desktop has both columns at ${width}`);
    assert(!await page.locator('.mobile-flow-nav').isVisible(), 'mobile navigation hidden on desktop');
    assert(await page.locator('#gateDemoPicker').evaluate(el => Boolean(el.closest('.output-card'))), 'desktop demo returns to original position');
    await page.locator('[data-gate-demo="R012"]').click();
    await waitReady('pass');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `desktop overflow at ${width}`);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.locator('.output-card').isVisible() && !await page.locator('#analyzeForm').isVisible(), 'resize preserves current result');
  assert(!errors.length, errors.join(';'));
  return { passed: true, loading: true, fourStates: true, inputPreserved: true, errorRetry: true, genderFollowup: true, desktopPreserved: true, widths: [320,390,768,820,821,1024,1440], errors };
}
