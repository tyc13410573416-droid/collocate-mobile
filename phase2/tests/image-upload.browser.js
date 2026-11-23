async (page) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const photo = { name: 'sample-02-glucose-crp.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+k0U8AAAAASUVORK5CYII=', 'base64') };
  await page.goto('http://127.0.0.1:8876/');
  await page.evaluate(() => localStorage.removeItem('medtrace.imageApiBase.v1'));
  await page.reload();
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
      data.metadata.image_route = 'nexent-analyze-image';
      data.metadata.vision_tool_observed = true;
      data.image_transcription = { raw_text: '测试转录 ALT 68 U/L。<img src=x onerror="window.badTranscript=true">', readable: true, uncertain_fields: [] };
      if (kind === 'low') { data.decision_gate = 'review'; data.evidence_status = 'low_confidence'; data.metadata.extraction_confidence = 0.65; }
      if (kind === 'low-empty') { data.decision_gate = 'review'; data.evidence_status = 'low_confidence'; data.patient_info = {}; delete data.metadata.extraction_confidence; data.image_transcription.uncertain_fields = ['ALT 小数点']; }
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
  await page.locator('#imageTranscriptPanel > summary').click();
  assert((await page.locator('#imageTranscriptText').textContent()).includes('ALT 68'), 'actual transcript available');
  assert(await page.locator('#imageTranscriptText img').count() === 0, 'transcript rendered as text, not HTML');
  assert(!(await page.evaluate(() => window.badTranscript)), 'no transcript script execution');

  action = 'low';
  await page.locator('#submitButton').click();
  await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'review' && !document.getElementById('submitButton').disabled);
  assert(await page.locator('#confidenceAlert').isVisible(), 'low-confidence review alert');
  assert(await page.locator('.status-chip.high').count() === 0, 'low confidence has no definitive red reading');
  assert(!(await page.locator('#genderDialog').isVisible()), 'low confidence has no unrelated sex prompt');

  action = 'low-empty';
  await page.locator('#submitButton').click();
  await page.waitForFunction(() => document.getElementById('resultPanel').dataset.gate === 'review' && !document.getElementById('submitButton').disabled);
  assert(await page.locator('#confidenceAlert').isVisible(), 'review alert with unknown patient');
  assert(!(await page.locator('#confidenceAlert').textContent()).includes('65%'), 'no stale confidence');
  assert((await page.locator('#imageUncertainFields').textContent()).includes('小数点'), 'uncertain fields visible');

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
  assert(sentBodies.length === 5, 'demo sample does not enter real photo route');
  assert((await page.locator('#fileName').textContent()).includes('预置数据演示'), 'sample explicitly marked');
  await page.unroute('**/api/analyze-image');

  // Local Flask returns an honest unavailable error when Nexent is unconfigured.
  await page.goto('http://127.0.0.1:5050/');
  await page.locator('#reportFile').setInputFiles(photo);
  await page.locator('#submitButton').click();
  await page.locator('#errorBanner').waitFor({ state: 'visible' });
  assert((await page.locator('#errorBanner').textContent()).includes('尚未接通'), 'local proxy not configured remains error');
  assert(!(await page.locator('#resultPanel').isVisible()), 'local demo mode cannot fabricate OCR');
  await page.goto('http://127.0.0.1:8876/');
  await page.locator('#aboutPanel > summary').click();
  await page.route('**/api/image-status', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"configured":true}' }));
  await page.locator('#imageServiceUrl').fill('http://127.0.0.1:8876');
  await page.locator('#imageServiceForm button[type="submit"]').click();
  await page.waitForFunction(() => document.getElementById('imageServiceStatus').textContent.includes('后端可访问'));
  assert((await page.locator('#imageServiceStatus').textContent()).includes('真实图片验证'), 'configuration is not OCR success');
  await page.reload();
  assert(await page.locator('#imageServiceUrl').inputValue() === 'http://127.0.0.1:8876', 'public backend URL persists locally');
  await page.locator('#aboutPanel > summary').click();
  await page.locator('#resetImageService').click();
  assert(await page.evaluate(() => !window.MEDTRACE_CONFIG.imageApiBase && localStorage.getItem('medtrace.imageApiBase.v1') === null), 'restore default removes saved address');
  await page.locator('#imageServiceUrl').fill('http://untrusted.example');
  await page.locator('#imageServiceForm button[type="submit"]').click();
  assert((await page.locator('#imageServiceStatus').textContent()).includes('HTTPS'), 'reject insecure cross-origin backend');
  await page.unroute('**/api/image-status');
  await page.locator('#aboutPanel > summary').click();
  await page.locator('#reportFile').setInputFiles('docs/static/assets/medical-demo/sample-01-coagulation.png');
  await page.locator('#assetPreview').scrollIntoViewIfNeeded();
  await page.screenshot({ path: '.playwright-cli/native-vision-mobile.png' });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'real image preview fits mobile');
  assert(!errors.length, `JavaScript errors: ${errors.join('; ')}`);
  return { passed: true, tested: ['actual local preview', 'no filename matching', 'unconfigured Pages no upload', 'multipart bytes', 'same photo sex correction', 'low confidence review', 'upstream OCR failure', 'PDF preview', 'invalid type', 'demo preserved', 'local 503', '390px mobile'], errors };
}
