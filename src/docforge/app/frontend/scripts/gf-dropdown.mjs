import { chromium } from 'playwright';
const BASE='http://localhost:10050', OUT='/out';
const b=await chromium.launch({args:['--no-sandbox']});
const c=await b.newContext({viewport:{width:1400,height:1000}});
const p=await c.newPage();
await p.goto(`${BASE}/login`,{waitUntil:'networkidle'});
await p.fill('input[name="user"]','admin').catch(()=>{});
await p.fill('input[name="password"]','change_me_grafana_admin').catch(()=>{});
await p.click('button[type="submit"]').catch(()=>{});
await p.waitForTimeout(2500);
await p.goto(`${BASE}/d/docforge-overview?from=now-3h&to=now&kiosk`,{waitUntil:'networkidle'});
await p.waitForTimeout(3500);
// Click the Service variable value pill
await p.getByText('Service',{exact:true}).first().click().catch(()=>{});
await p.waitForTimeout(400);
// the value box sits right after label; click the "All" combobox for Service
await p.locator('input[role="combobox"]').first().click().catch(()=>{});
await p.waitForTimeout(900);
await p.screenshot({path:`${OUT}/gf-service-dropdown.png`});
const opts=await p.evaluate(()=>[...document.querySelectorAll('[role="option"], [aria-label^="Select option"]')].map(e=>e.textContent.trim()).filter(Boolean));
console.log(JSON.stringify({serviceOpts:opts},null,2));
await b.close();
