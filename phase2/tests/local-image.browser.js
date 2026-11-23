async (page) => {
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('http://127.0.0.1:5052/');
  await page.locator('#reportFile').setInputFiles('C:/Users/tyc/Documents/ChatGPT/华为/docs/static/assets/medical-demo/sample-02-glucose-crp.png');
  await page.locator('#patientGender').selectOption('男');
  await page.locator('#submitButton').click();
  return {started:true,loading:await page.locator('#loadingState').isVisible(),errors};
}
