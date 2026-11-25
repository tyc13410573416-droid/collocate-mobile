async (page) => {
  const folder='C:/Users/tyc/Documents/ChatGPT/华为/交付截图/移动端分步_20261125';
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const assert=(ok,message)=>{if(!ok)throw new Error(message);};
  const choose=async id=>{
    if(await page.locator('#mobileBack').isVisible())await page.locator('#mobileBack').click();
    await page.locator('#mobileExamples').evaluate(el=>{el.open=true;});
    await page.locator(`[data-gate-demo="${id}"]`).click();
  };
  const ready=async gate=>page.waitForFunction(expected=>document.getElementById('resultPanel').dataset.gate===expected&&!document.getElementById('submitButton').disabled,gate);
  const shot=async name=>{
    await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    await page.screenshot({path:folder+'/'+name,animations:'disabled'});
  };
  await page.setViewportSize({width:390,height:844});
  await page.goto('https://tyc13410573416-droid.github.io/collocate-mobile/');
  assert(await page.locator('meta[name="medtrace-release"]').getAttribute('content')==='20261125-mobile-steps','public release must be current');
  await page.waitForFunction(()=>Boolean(window.MEDTRACE_FLOW));
  await shot('01-手机输入视图.png');
  await choose('R012');
  assert(await page.locator('#loadingState').isVisible(),'loading screen exists');
  await shot('02-生成后的加载视图.png');
  await ready('pass');
  await shot('03-手机结果视图与返回.png');
  await choose('R005');await ready('review');
  await shot('04-来源冲突复核视图.png');
  await choose('R013');await ready('review');
  await page.locator('#genderDialog').waitFor({state:'visible'});
  await shot('10-缺少信息时追问.png');
  await page.locator('#deferGender').click();
  await choose('R006');await ready('abstain');
  await shot('05-拒答视图.png');
  await page.setViewportSize({width:1440,height:1100});
  await page.locator('[data-gate-demo="R012"]').click();await ready('pass');
  await page.locator('#workspace').evaluate(el=>window.scrollTo({top:el.getBoundingClientRect().top+scrollY-24,behavior:'instant'}));
  await page.screenshot({path:folder+'/09-电脑端保留双栏.png',animations:'disabled'});
  assert(!errors.length,errors.join(';'));
  return {passed:true,publicRelease:true,files:7,mobileSteps:true,desktopPreserved:true,errors};
}
