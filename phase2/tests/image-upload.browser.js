async (page) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const photo = { name: 'sample-02-glucose-crp.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+k0U8AAAAASUVORK5CYII=', 'base64') };
  await page.goto('http://127.0.0.1:8876/');
  let posts = 0;
  page.on('request', (request) => { if (request.method() === 'POST') posts++; });
  // Even a file named exactly like a demo picture is a new upload, never a fixture.
  await page.locator('#reportFile').setInputFiles(photo);
  assert((await page.locator('#rawText').inputValue()) === '', 'file choice clears old sample text');
  assert((await page.locator('#reportId').inputValue()) === '', 'file choice clears old report id');
  assert((await page.locator('#assetPreviewImage').getAttribute('src')).startsWith('blob:'), 'real local preview');
  assert((await page.locator('#uploadStatus').textContent()).includes('尚未接通'), 'public page states actual availability');
  await page.locator('#submitButton').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  assert(posts === 0, 'unconfigured Pages must send no file bytes');
  assert(!(await page.locator('#resultPanel').isVisible()), 'no demo result for actual upload');
  assert(await page.locator('#removeFile').isVisible(), 'keep file after error');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#uploadStatus').scrollIntoViewIfNeeded();
  await page.screenshot({ path: '.playwright-cli/image-not-configured-mobile.png' });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'photo preview fits mobile');

  // Simulate our proxy contract, not OCR. Verify multipart and same photo on sex retry.
  await page.evaluate(() => { window.MEDTRACE_CONFIG.imageApiBase = location.origin; });
  const sentBodies = [];
  let action = 'missing';
  await page.route('**/api/analyze-image', async (route) => {
    sentBodies.push(route.request().postDataBuffer());
    if (action === 'failure') {
      await route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: '{"type":"stage","stage":"uploaded"}\n{"type":"error","error_code":"AGENT_FAILED","error":"测试：OCR 服务不可用"}\n' });
      return;
    }
    const result = await page.evaluate((kind) => {
      const data = structuredClone(window.MEDTRACE_GATE_FIXTURES.variants.R013[kind === 'missing' ? '未知' : '男']['']);
      data.transport = 'nexent-image-http';
      if (kind === 'low') { data.decision_gate = 'review'; data.evidence_status = 'low_confidence'; data.metadata.extraction_confidence = 0.65; }
      return data;
    }, action);
    const body = [{ type: 'stage', stage: 'uploading' }, { type: 'stage', stage: 'uploaded' }, { type: 'stage', stage: 'agent_submitted' }, { type: 'result', result }].map((event) => JSON.stringify(event)).join('\n') + '\n';
    await route.fulfill({ status: 200, contentType: 'application/x-ndjson; charset=utf-8', body });
  });
  await page.locator('#submitButton').click();
  await page.locator('#genderDialog').waitFor({ state: 'visible' });
  assert(await page.locator('#resultPanel').getAttribute('data-gate') === 'review', 'photo missing sex is review');
  action = 'pass';
  await page.locator('#clarificationGender').selectOption('男');
  await page.getByRole('button', { name: '提交并重新解读' }).click();
  await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'pass' && !document.getElementById('submitButton').disabled);
  assert(sentBodies.length === 2, 'same upload retried after sex correction');
  assert(sentBodies.every((body) => body.includes(photo.buffer)), 'photo bytes sent on both requests');
  assert(sentBodies[1].toString().includes('name="gender"\r\n\r\n男'), 'corrected sex in actual multipart');
  assert(sentBodies.every((body) => body.toString().includes('filename="report.png"')), 'neutral outgoing filename');
  assert((await page.locator('#auditMode').textContent()).includes('图片接口'), 'photo audit not labelled demo');
  assert((await page.locator('#uploadStatus').textContent()).includes('已收到结构化'), 'completion distinct from upload');

  action = 'low';
  await page.locator('#submitButton').click();
  await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'review' && !document.getElementById('submitButton').disabled);
  assert(await page.locator('#confidenceAlert').isVisible(), 'low-confidence review alert');
  assert(await page.locator('.status-chip.high').count() === 0, 'low confidence has no definitive red reading');
  assert(!(await page.locator('#genderDialog').isVisible()), 'low confidence has no unrelated sex prompt');

  action = 'failure';
  await page.locator('#submitButton').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  assert((await page.locator('#errorBanner').textContent()).includes('OCR 服务不可用'), 'upstream failure displayed');
  assert(!(await page.locator('#resultPanel').isVisible()), 'no stale result after OCR error');
  assert(await page.locator('#removeFile').isVisible(), 'failed photo preserved for retry');

  await page.locator('#removeFile').click();
  assert(!(await page.locator('#assetPreview').isVisible()), 'remove clears preview');
  await page.locator('#reportFile').setInputFiles({ name: 'report.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\ntransport-test') });
  assert(await page.locator('#assetPreviewPdf').isVisible(), 'PDF local preview link');
  assert(!(await page.locator('#assetPreviewImage').isVisible()), 'PDF does not leave stale photo');
  await page.locator('#removeFile').click();
  await page.locator('#reportFile').setInputFiles({ name: 'bad.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') });
  assert((await page.locator('#uploadStatus').textContent()).includes('请选择'), 'unsupported file rejected');
  assert(!(await page.locator('#assetPreview').isVisible()), 'invalid file clears old preview');
  await page.locator('.asset-button[data-asset="glucose-crp"]').click();
  await page.locator('#submitButton').click();
  await page.waitForFunction(() => !document.getElementById('resultPanel').classList.contains('hidden') && !document.getElementById('submitButton').disabled);
  assert(sentBodies.length === 4, 'demo sample does not enter real photo route');
  assert((await page.locator('#fileName').textContent()).includes('预置数据演示'), 'sample explicitly marked');
  await page.unroute('**/api/analyze-image');

  // Local Flask returns an honest unavailable error when Nexent is unconfigured.
  await page.goto('http://127.0.0.1:5050/');
  await page.locator('#reportFile').setInputFiles(photo);
  await page.locator('#submitButton').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  assert((await page.locator('#errorBanner').textContent()).includes('尚未接通'), 'local proxy not configured remains error');
  assert(!(await page.locator('#resultPanel').isVisible()), 'local demo mode cannot fabricate OCR');
  assert(!errors.length, `JavaScript errors: ${errors.join('; ')}`);
  return { passed: true, tested: ['actual local preview', 'no filename matching', 'unconfigured Pages no upload', 'multipart bytes', 'same photo sex correction', 'low confidence review', 'upstream OCR failure', 'PDF preview', 'invalid type', 'demo preserved', 'local 503', '390px mobile'], errors };
}
