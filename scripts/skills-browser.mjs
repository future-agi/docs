#!/usr/bin/env node
/** Cloud-only smoke test of built documentation, including mobile overflow and API anchors. */
import fs from 'node:fs';
import path from 'node:path';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dist=path.join(root,'dist');
const out=process.argv[2] ?? path.join(root,'evidence','docs-browser.json');
const mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2'};
const server=createServer((req,res)=>{
  let file=path.resolve(dist,`.${decodeURIComponent(new URL(req.url,'http://localhost').pathname)}`);
  if (!file.startsWith(`${dist}/`) && file!==dist) {res.writeHead(403);res.end();return;}
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file=path.join(file,'index.html');
  if (!fs.existsSync(file)) {res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]??'application/octet-stream'});
  fs.createReadStream(file).pipe(res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true});
const records=[];
try {
  const page=await browser.newPage();
  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:900});
    for (const slug of ['agent-contexts','import-skills','migration','tests','reviewed-releases','sdk-cli','campaigns','sealed-api']) {
      const response=await page.goto(`${origin}/docs/skills/${slug}/`,{waitUntil:'networkidle'});
      assert.equal(response.status(),200,slug);
      if (slug==='sealed-api') {
        // This long static page can still be parsing after network quiescence on a cached revisit.
        // Assert readiness of the complete contract before checking every anchor.
        await page.waitForFunction(()=>document.querySelectorAll('.api-schema').length===438 && document.getElementById('schema-skillsversionpageresponse'));
      }
      const result=await page.evaluate(()=>({
        title:document.title,
        width:innerWidth,
        scrollWidth:document.documentElement.scrollWidth,
        brokenImages:[...document.querySelectorAll('article img')].filter(image=>!image.complete||image.naturalWidth===0).map(image=>image.getAttribute('src')),
        missingAnchors:[...document.querySelectorAll('a[href^="#schema-"]')].map(link=>link.getAttribute('href')).filter(href=>!document.getElementById(href.slice(1))),
        operations:document.querySelectorAll('.api-operation').length,
        liveExamples:[...document.querySelectorAll('summary')].filter(node=>node.textContent.startsWith('Captured request')).length,
      }));
      assert.ok(result.scrollWidth<=width+1,`${slug} at ${width}: page overflow ${result.scrollWidth}`);
      assert.deepEqual(result.brokenImages,[],slug);
      assert.deepEqual(result.missingAnchors,[],slug);
      if (slug==='sealed-api') {assert.equal(result.operations,154);assert.ok(result.liveExamples>=64);}
      records.push({slug,...result});
    }
  }
} finally {
  await browser.close();
  server.closeAllConnections();
  await new Promise(resolve=>server.close(resolve));
  fs.mkdirSync(path.dirname(out),{recursive:true});
  fs.writeFileSync(out,JSON.stringify(records,null,2));
}
console.log(`Passed ${records.length} desktop/mobile page checks`);
