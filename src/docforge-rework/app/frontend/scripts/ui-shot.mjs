// ====== DocForge UI screenshotter (Playwright) ======
// Drives the frontend (default http://localhost:10046) in a real browser and screenshots it, so a
// session with no host browser can still see + test the UI. No host browser is needed: run it inside
// the official Playwright Docker image (browsers + libs baked in) with --network host — see
// UI-SCREENSHOT.md. Seeds the bearer into localStorage BEFORE any page script (addInitScript) so the
// first API call is authenticated (apiFetch clears the token on a 401, so a late inject would 401).
//
// Usage (inside the container): node ui-shot.mjs --out /work/shot.png [--path "DemoCollection,Documents,doc.pdf,Pages"]
//   --path : comma-separated visible texts to click in order (hand-rolled routing has no deep-link URLs).
//   Reports, as JSON on stdout: the <img> audit (blob: object URLs vs stale direct /blobs URLs vs
//   broken placeholders) and every /api/v1 401 — the two signals that catch an auth-regressed UI.

import { chromium } from 'playwright';

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i === -1 ? d : process.argv[i + 1]; };
const BASE = process.env.GF_URL || arg('base', 'http://localhost:10046');
const TOKEN = process.env.DOCFORGE_API_TOKEN || '';
const OUT = arg('out', '/work/shot.png');
const PATH = (arg('path', '') || '').split(',').map(s => s.trim()).filter(Boolean);

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
if (TOKEN) await ctx.addInitScript(t => window.localStorage.setItem('docforge_api_token', t), TOKEN);
const page = await ctx.newPage();
const unauthorized = [];
page.on('response', r => { if (r.status() === 401) unauthorized.push(r.url().split('/api/v1')[1] || r.url()); });

// 1. Load authenticated, then walk the click-path (each step is a visible text to click).
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
for (const text of PATH) {
  const el = page.getByText(text, { exact: false }).first();
  if (await el.count()) { await el.click({ timeout: 5000 }).catch(() => {}); await page.waitForTimeout(1800); }
}

// 2. Screenshot + audit images (a blob: src = the authenticated BlobImage path; a raw /blobs src or an
//    "unavailable" placeholder = a broken auth-blind <img>).
await page.screenshot({ path: OUT, fullPage: true });
const images = await page.evaluate(() => {
  const g = [...document.querySelectorAll('img')];
  return {
    total: g.length,
    blobObjectUrl: g.filter(i => i.src.startsWith('blob:')).length,
    loaded: g.filter(i => i.complete && i.naturalWidth > 0).length,
    rawBlobsUrl: g.filter(i => i.src.includes('/api/v1/blobs/')).length,
  };
});
console.log(JSON.stringify({ out: OUT, images, unauthorized: [...new Set(unauthorized)] }, null, 2));
await browser.close();
