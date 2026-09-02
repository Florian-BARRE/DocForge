// Grafana QA screenshotter: logs in, opens the DocForge Overview dashboard in a TALL viewport
// (so every panel is in-viewport and renders), screenshots in slices, and dumps the
// $service / $route template-variable option lists.
import { chromium } from 'playwright';

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i === -1 ? d : process.argv[i + 1]; };
const BASE = process.env.GF_URL || 'http://localhost:10050';
const USER = process.env.GF_USER || 'admin';
const PASS = process.env.GF_PASS || 'change_me_grafana_admin';
const UID = arg('uid', 'docforge-overview');
const OUTDIR = arg('outdir', '/work');
const VH = Number(arg('vh', '1100'));

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1600, height: VH }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const consoleErrors = [];
page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });

// 1. Login
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
await page.fill('input[name="user"]', USER).catch(()=>{});
await page.fill('input[name="password"]', PASS).catch(()=>{});
await page.click('button[type="submit"]').catch(()=>{});
await page.waitForTimeout(2500);

// 2. Open dashboard, wide time range, kiosk
await page.goto(`${BASE}/d/${UID}?from=now-3h&to=now&kiosk`, { waitUntil: 'networkidle' });
await page.waitForTimeout(4000);

// 3. Find the real scroll element, then step through it screenshotting each viewport slice.
const scrollInfo = await page.evaluate(() => {
  const cands = [...document.querySelectorAll('*')].filter(e => e.scrollHeight > e.clientHeight + 50 && e.clientHeight > 400);
  cands.sort((a,b) => b.scrollHeight - a.scrollHeight);
  const el = cands[0];
  if (el) el.setAttribute('data-qa-scroll', '1');
  return el ? { scrollHeight: el.scrollHeight, clientHeight: el.clientHeight, tag: el.className } : null;
});

let idx = 0;
if (scrollInfo) {
  const step = scrollInfo.clientHeight - 80;
  for (let y = 0; y < scrollInfo.scrollHeight; y += step) {
    await page.evaluate((yy) => {
      const el = document.querySelector('[data-qa-scroll="1"]');
      if (el) el.scrollTop = yy;
    }, y);
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUTDIR}/gf-slice-${String(idx).padStart(2,'0')}.png` });
    idx++;
  }
} else {
  await page.screenshot({ path: `${OUTDIR}/gf-slice-00.png`, fullPage: true });
  idx = 1;
}

// 4. Template variable option lists: open $Service and $Route dropdowns, read options.
async function readVarOptions(label) {
  try {
    const trigger = page.locator(`[aria-label="${label}"], label:has-text("${label}")`).first();
    // Grafana renders variable pickers as inputs; click the value box next to the label.
    const box = page.locator(`text=${label}`).first();
    await box.click({ timeout: 3000 }).catch(()=>{});
    await page.waitForTimeout(600);
    const opts = await page.evaluate(() => {
      const items = [...document.querySelectorAll('[role="option"], [aria-label^="Select option"], .variable-option')];
      return items.map(i => i.textContent.trim()).filter(Boolean);
    });
    await page.keyboard.press('Escape').catch(()=>{});
    await page.waitForTimeout(300);
    return opts;
  } catch { return []; }
}
const serviceOpts = await readVarOptions('Service');
const routeOpts = await readVarOptions('Route');

console.log(JSON.stringify({ scrollInfo, slices: idx, serviceOpts, routeOpts, consoleErrors: [...new Set(consoleErrors)] }, null, 2));
await browser.close();
