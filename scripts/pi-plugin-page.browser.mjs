import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('dist');
const server=createServer(async(req,res)=>{
 try{
  let file=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(file.endsWith('/'))file+='index.html';
  const absolute=path.resolve(root,`.${file}`);
  if(!absolute.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
  const content=await readFile(absolute);
  const ext=path.extname(absolute);res.setHeader('content-type',({'.html':'text/html','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp'})[ext]??'application/octet-stream');res.end(content);
 }catch{res.writeHead(404);res.end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for (const agent of ['pi', 'oh-my-pi']) {
  const response = await page.goto(`http://127.0.0.1:${server.address().port}/docs/integrations/coding-agents/${agent}/`,{waitUntil:'networkidle'});
  assert.equal(response.status(), 200);
  await page.locator('h1').first().waitFor();
  const body = await page.locator('body').innerText();
  assert.ok(body.includes(`npx @traceai/agents setup ${agent} --project coding-agents`));
  assert.ok(body.includes('captured by default'));
  assert.ok(body.includes('Status and lifecycle'));
  await page.screenshot({path:`${agent}-docs.png`,fullPage:true});
  await page.getByRole('heading', {name:'Quick start',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:`${agent}-quick-start.png`});
  assert.equal(errors.length,0,errors.join('\n'));
  console.log(JSON.stringify({page:agent,browser:'chromium',width:1440,pass:true}));
 }
}finally{await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
