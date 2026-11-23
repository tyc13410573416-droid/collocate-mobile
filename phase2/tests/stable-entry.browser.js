async (page) => {
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const assert=(condition,message)=>{if(!condition)throw new Error(message);};
  const address='https://tyc13410573416-droid.github.io/collocate-mobile/';
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(address);
  await page.waitForFunction(()=>window.MEDTRACE_CONFIG?.sharedImageStatus==='online',null,{timeout:30000});
  const backend=await page.evaluate(()=>window.MEDTRACE_CONFIG.imageApiBase);
  await page.locator('#reportFile').setInputFiles('docs/static/assets/medical-demo/sample-02-glucose-crp.png');
  await page.locator('#patientGender').selectOption('男');
  await page.locator('#submitButton').click();
  await page.waitForFunction(()=>!document.getElementById('submitButton').disabled&&!document.getElementById('resultPanel').classList.contains('hidden'),null,{timeout:180000});
  const values=await page.locator('.metric-value').allTextContents();
  assert(values.some(value=>value.startsWith('16.1mmol/L')),'real glucose reading must remain 16.1');
  assert(values.some(value=>value.startsWith('16mg/L')),'real CRP reading must remain 16.0');
  assert(page.url()===address,'team page URL must remain fixed');
  assert((await page.locator('#environmentLabel').textContent()).includes('图片解读'),'real image must not be labelled a synthetic replay');
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'shared page must fit mobile');
  assert(!errors.length,'no browser script errors');
  return {passed:true,address,backend,values,errors};
}
