const {chromium} = require('playwright');
const fs=require('node:fs/promises');
const assert=require('node:assert/strict');
const path=require('node:path');
const os=require('node:os');
const ROOT=path.resolve(__dirname,'..');
const OUT=process.env.INTEGRATIONS_EVIDENCE_DIR || path.join(os.tmpdir(),'docs-integrations-browser');
const BASE='http://127.0.0.1:4321';
const results=[];
async function record(name, fn) { try {const detail=await fn();results.push({name,status:'PASS',detail});} catch(e) {results.push({name,status:'FAIL',error:String(e.stack)});} await fs.writeFile(OUT+'/browser-results.json',JSON.stringify(results,null,2)); }
(async()=>{
 await fs.mkdir(OUT,{recursive:true});
 const {integrations}=await import('../src/lib/integrations.mjs');
 let ready=false;
 for(let attempt=0;attempt<40;attempt++) {
  try { if((await fetch(BASE+'/docs/integrations')).ok) { ready=true; break; } } catch {}
  await new Promise(resolve=>setTimeout(resolve,150));
 }
 assert.ok(ready,'Start the docs preview on 127.0.0.1:4321 before running browser checks');
 const browser=await chromium.launch({headless:true});
 for(const [name,width,height] of [['desktop',1440,1000],['tablet',768,1024],['mobile390',390,844],['mobile375',375,812]]) {
  await record(name+' responsive directory',async()=>{
   const ctx=await browser.newContext({viewport:{width,height},colorScheme:'dark'});const page=await ctx.newPage();

   await page.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});await page.locator('[data-integration-directory][data-ready]').waitFor();await page.screenshot({path:OUT+'/after-'+name+'.png'});
   assert.equal(await page.locator('[data-integration-card]:visible').count(),integrations.length);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'horizontal overflow');
   const first=await page.locator('[data-integration-card]').first().boundingBox();
   await ctx.close();return {width,height,firstCard:first};
  });
 }
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}});const page=await ctx.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});
 const search=()=>page.locator('#integration-search');
 async function query(q,n=1) {await search().fill(q);await page.waitForTimeout(450);assert.equal(await page.locator('[data-integration-card]:visible').count(),n,'query: '+q);}
 await record('new names and historical aliases',async()=>{
  for(const [q,part] of [['LobeChat','LobeHub'],['LobeHub','LobeHub'],['grafi','Graphite'],['Google ADK Java','Google ADK for Java'],['Apollo','Apollo Server'],['Novita','Novita AI'],['watsonx','watsonx Orchestrate ADK']]) {await query(q,q==='watsonx'?2:1);assert.ok((await page.locator('[data-integration-card]:visible').allInnerTexts()).join(' ').includes(part));}
  await page.screenshot({path:OUT+'/search-alias.png'});
 });
 await record('category intersection, empty state and reset',async()=>{
  await search().fill('');await page.waitForTimeout(350);await page.getByRole('button',{name:'Gateways',exact:true}).click();assert.equal(await page.locator('[data-integration-card]:visible').count(),integrations.filter(i=>i.category==='gateways').length);
  await query('LiteLLM');assert.match(await page.locator('[data-integration-card]:visible').innerText(),/LiteLLM Proxy/);
  await query('no-result-zzzzz',0);assert.equal(await page.locator('[data-empty]').isVisible(),true);await page.screenshot({path:OUT+'/no-results.png'});
  await page.locator('[data-empty] [data-clear]').click();assert.equal(await page.locator('[data-integration-card]:visible').count(),integrations.length);assert.equal(await search().inputValue(),'');assert.equal(await search().evaluate(el=>el===document.activeElement),true);
 });
 await record('back/forward and FastNav return preserve query/filter state',async()=>{
  await query('LiteLLM',2);await page.getByRole('button',{name:'Gateways',exact:true}).click();assert.equal(await page.locator('[data-integration-card]:visible').count(),1);
  const filtered=page.url();await page.locator('[data-integration-card]:visible').click();await page.waitForURL('**/gateways/litellm-proxy');await page.locator('h1').filter({hasText:'LiteLLM'}).waitFor();
  await page.goBack();await search().waitFor();await page.waitForTimeout(500);assert.equal(page.url(),filtered);assert.equal(await search().inputValue(),'LiteLLM');assert.equal(await page.locator('[data-integration-card]:visible').count(),1);
  await page.goBack();await page.waitForTimeout(500);assert.equal(await page.locator('[data-integration-card]:visible').count(),2);
  await page.goForward();await page.waitForTimeout(500);assert.equal(await page.locator('[data-integration-card]:visible').count(),1);
  await page.reload({waitUntil:'networkidle'});assert.equal(await page.locator('[data-integration-card]:visible').count(),1);
 });
 await record('idempotent lifecycle initialization',async()=>{
  await page.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});
  await page.evaluate(()=>{for(let i=0;i<4;i++){document.dispatchEvent(new Event('astro:page-load'));window.dispatchEvent(new Event('fastnav'));}});
  const start=await page.evaluate(()=>history.length);await page.getByRole('button',{name:'Java',exact:true}).click();assert.equal(await page.evaluate(()=>history.length),start+1);assert.equal(await page.locator('[data-integration-card]:visible').count(),integrations.filter(i=>i.category==='java').length);
 });
 await record('keyboard only search, category, focus and global search shortcut',async()=>{
  await page.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});
  // Reach the directory with actual keyboard navigation, not mouse focus.
  for(let i=0;i<60 && !(await search().evaluate(el=>el===document.activeElement));i++)await page.keyboard.press('Tab');
  assert.equal(await search().evaluate(el=>el===document.activeElement),true);
  await page.keyboard.type('Graphite');await page.waitForTimeout(450);assert.equal(await page.locator('[data-integration-card]:visible').count(),1);
  await page.keyboard.press('Tab');await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter');
  const outline=await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle);assert.notEqual(outline,'none');await page.screenshot({path:OUT+'/keyboard-focus.png'});
  await page.keyboard.press('Control+k');await page.waitForTimeout(300);
  assert.equal(await page.locator('#search-modal').isVisible(),true);await page.keyboard.press('Escape');
 });
 await record('all logo images decode; complete logo atlas',async()=>{
  const manifest=JSON.parse(await fs.readFile(path.join(ROOT,'public/images/integrations/manifest.json')));
  await page.setContent('<body style="margin:0;padding:20px;background:#0a0a0a;color:#fafafa;font:13px Inter,sans-serif"><div id="atlas" style="display:grid;grid-template-columns:repeat(7,1fr);gap:12px"></div></body>');
  await page.evaluate(({assets,base})=>{document.querySelector('#atlas').innerHTML=Object.entries(assets).map(([key,a])=>`<div style="height:92px;background:#111;padding:8px;display:flex;align-items:center;justify-content:center;gap:8px;flex-direction:column"><span style="width:48px;height:48px;background:${a.tile==='dark'?'#18181b':'#fafafa'};border-radius:7px;display:flex;align-items:center;justify-content:center">${a.file?`<img width="40" height="40" style="object-fit:contain" src="${base}${a.file}"/>`:`<b style="color:#333">${a.text}</b>`}</span><span>${key}</span></div>`).join('');},{assets:manifest.assets,base:BASE});
  await page.waitForTimeout(1000);const broken=await page.locator('img').evaluateAll(imgs=>imgs.filter(i=>!i.complete||!i.naturalWidth).map(i=>i.src));assert.deepEqual(broken,[]);await page.screenshot({path:OUT+'/logo-atlas.png',fullPage:true});return {images:await page.locator('img').count()};
 });
 await record('all card routes return successful pages and rendered sidebar parity',async()=>{
  await page.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});
  const hrefs=await page.locator('[data-integration-card]').evaluateAll(els=>els.map(e=>e.getAttribute('href')));
  const nav=new Set(await page.locator('.integration-sidebar a').evaluateAll(els=>els.map(e=>e.getAttribute('href'))));for(const href of hrefs){assert.ok(nav.has(href));const r=await page.request.get(BASE+href);assert.equal(r.status(),200,href);}
  return {cards:hrefs.length,uniqueRoutes:new Set(hrefs).size,sidebarLinks:nav.size};
 });
 await record('mobile sidebar current page and native disclosure',async()=>{
  await page.setViewportSize({width:390,height:844});await page.goto(BASE+'/docs/integrations/frameworks/graphite',{waitUntil:'networkidle'});await page.locator('#mobile-menu-button').click();await page.waitForTimeout(350);
  const active=page.locator('.integration-sidebar a[aria-current="page"]');assert.equal(await active.innerText(),'Graphite (grafi)');assert.equal(await active.isVisible(),true);assert.equal(await active.evaluate(e=>e.closest('details').open),true);
  assert.equal(await active.evaluate(e=>{const r=e.getBoundingClientRect();const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return top===e||e.contains(top);}),true,'current guide must not be covered by header menu');
  await page.screenshot({path:OUT+'/mobile-sidebar.png'});
  await page.keyboard.press('Escape');assert.equal(await page.locator('#mobile-menu-button').getAttribute('aria-expanded'),'false');
  await page.locator('#mobile-menu-button').click();await page.locator('#sidebar-overlay').click({position:{x:380,y:700}});assert.equal(await page.locator('#mobile-menu-button').getAttribute('aria-expanded'),'false');
  await page.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});await page.locator('#integration-category').selectOption('gateways');assert.equal(await page.locator('[data-integration-card]:visible').count(),integrations.filter(i=>i.category==='gateways').length);await page.screenshot({path:OUT+'/mobile-filter.png'});
  await page.goto(BASE+'/docs/integrations/google-adk',{waitUntil:'networkidle'});assert.equal(await page.locator('.integration-sidebar a[aria-current="page"]').innerText(),'Google ADK');
 });
 await record('reduced motion and light preference retain site dark tokens',async()=>{
  const c=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce',colorScheme:'light'});const p=await c.newPage();await p.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});
  assert.equal(await p.locator('[data-integration-card]').first().evaluate(e=>getComputedStyle(e).transitionDuration),'0s');const background=await p.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor);await p.screenshot({path:OUT+'/after-light-reduced-motion.png'});await c.close();return {background};
 });
 await record('JavaScript disabled: all cards, category anchors and direct navigation',async()=>{
  const c=await browser.newContext({viewport:{width:375,height:812},javaScriptEnabled:false});const p=await c.newPage();await p.goto(BASE+'/docs/integrations',{waitUntil:'networkidle'});assert.equal(await p.locator('[data-integration-card]:visible').count(),integrations.length);assert.equal(await p.locator('.directory-controls').isVisible(),false);await p.screenshot({path:OUT+'/no-js-mobile.png'});
  await p.locator('noscript a[href="#java"]').click();await p.locator('[href="/docs/integrations/traceai/java/google-adk"][data-integration-card]').click();await p.waitForURL('**/java/google-adk');assert.equal(await p.locator('h1').count(),1);await c.close();
 });
 await record('no application JavaScript errors',async()=>{assert.deepEqual(errors,[]);});
 await browser.close();console.log(JSON.stringify(results,null,2));if(results.some(r=>r.status==='FAIL'))process.exit(1);
})().catch(async e=>{console.error(e);process.exit(1)});
