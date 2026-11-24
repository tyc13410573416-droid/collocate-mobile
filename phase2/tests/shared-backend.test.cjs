const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../docs/static/shared-backend.js'), 'utf8');
const first = 'https://first-team.trycloudflare.com';
const second = 'https://second-team.trycloudflare.com';
const record = (url=first) => ({version:1,active:true,image_api_base:url});
function setup(fetcher, config={}, cached=null) {
  const values = new Map(cached ? [['medtrace.sharedBackend.v1',JSON.stringify(cached)]] : []);
  const calls=[];
  const settings={mode:'demo',...config};
  const context={
    window:{MEDTRACE_CONFIG:settings,dispatchEvent(){}},
    document:{getElementById(){return null;}},
    location:{hostname:'tyc13410573416-droid.github.io',pathname:'/collocate-mobile/'},
    localStorage:{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)},
    fetch:async(url,opts)=>{calls.push({url,opts});return fetcher(url,opts);},
    Event:class{},AbortController,Date,JSON,Error,Promise,
    setTimeout:(fn,ms)=>ms===0 ? 0 : setTimeout(fn,ms),clearTimeout,
    atob:value=>Buffer.from(value,'base64').toString('binary'),
  };
  vm.runInNewContext(source,context);
  return {client:context.window.MEDTRACE_SHARED,config:settings,calls};
}
const ok=body=>({ok:true,json:async()=>body});
test('fixed entry falls back from raw host to public API without credentials',async()=>{
  const env=setup(async url=>{
    if(url.includes('raw.githubusercontent.com'))throw new Error('blocked');
    if(url.includes('api.github.com'))return ok({encoding:'base64',content:Buffer.from(JSON.stringify(record())).toString('base64')});
    return ok({configured:true});
  });
  await env.client.ensureReady();
  assert.equal(env.config.imageApiBase,first);
  assert.equal(env.config.sharedImageStatus,'online');
  assert.ok(env.calls.every(call=>call.opts.credentials==='omit'&&!call.opts.headers));
});
test('intentional OCR stop preserves the static demonstration',async()=>{
  const env=setup(async()=>ok({version:1,active:false,image_api_base:''}),{imageApiBase:first});
  await assert.rejects(env.client.ensureReady(),/离线/);
  assert.equal(env.config.mode,'demo');
  assert.equal(env.config.imageApiBase,'');
  assert.equal(env.calls.length,1);
});
test('untrusted registry addresses never receive health or upload requests',async()=>{
  const env=setup(async()=>ok(record('https://untrusted.invalid/patient')));
  await assert.rejects(env.client.ensureReady(),/离线/);
  assert.ok(env.calls.every(call=>!call.url.includes('untrusted.invalid')));
});
test('an explicit manual backend is never overwritten',async()=>{
  const env=setup(async()=>{throw new Error('unexpected network');},{imageManualBase:true,imageApiBase:'https://manual.example'});
  await env.client.refresh(true);await env.client.ensureReady();
  assert.equal(env.config.imageApiBase,'https://manual.example');
  assert.equal(env.calls.length,0);
});
test('a rotated tunnel changes the target without changing the page URL',async()=>{
  let current=first;
  const env=setup(async url=>ok(url.includes('/api/image-status')?{configured:true}:record(current)));
  await env.client.ensureReady();
  current=second;
  await env.client.refresh(true);
  assert.equal(env.config.imageApiBase,second);
  assert.equal(env.config.sharedImageStatus,'online');
});
test('validated cached address survives registry outages',async()=>{
  const env=setup(async url=>{if(!url.includes('/api/image-status'))throw new Error('network down');return ok({configured:true});},{},record());
  await env.client.ensureReady();
  assert.equal(env.config.imageApiBase,first);
});
test('unreachable OCR stays offline while the page remains in demo mode',async()=>{
  const env=setup(async url=>{if(url.includes('/api/image-status'))throw new Error('offline');return ok(record());});
  await assert.rejects(env.client.ensureReady(),/离线/);
  assert.equal(env.config.sharedImageStatus,'offline');
  assert.equal(env.config.mode,'demo');
});
test('retry after recovery checks immediately instead of waiting on an offline cache',async()=>{
  let healthy=false;
  const env=setup(async url=>{
    if(url.includes('/api/image-status')){if(!healthy)throw new Error('offline');return ok({configured:true});}
    return ok(record());
  });
  await assert.rejects(env.client.ensureReady(),/离线/);
  healthy=true;
  await env.client.ensureReady();
  assert.equal(env.config.sharedImageStatus,'online');
});
test('local and direct shared pages keep their own same-origin backend',async()=>{
  const env=setup(async()=>{throw new Error('unexpected network');},{mode:'api'});
  await env.client.ensureReady();
  assert.equal(env.client.enabled,false);
  assert.equal(env.calls.length,0);
});
