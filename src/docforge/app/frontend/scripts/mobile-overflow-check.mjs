// One-off mobile-overflow / shell-reskin verification script.
// Checks scrollWidth<=innerWidth at several viewport widths on a few pages, exercises the new
// TopBar hamburger menu, and screenshots each state for visual review.

import { chromium } from 'playwright';

const BASE = process.env.GF_URL || 'http://localhost:10046';
const OUT_DIR = '/work';

const WIDTHS = [375, 768, 1440, 1920];
const HEIGHT = 900;

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: WIDTHS[0], height: HEIGHT } });
const page = await ctx.newPage();

const results = [];

async function measure(label) {
  const m = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }));
  results.push({ label, ...m, overflow: m.scrollWidth > m.innerWidth || m.bodyScrollWidth > m.innerWidth });
}

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

for (const w of WIDTHS) {
  await page.setViewportSize({ width: w, height: HEIGHT });
  await page.waitForTimeout(300);
  await measure(`collections@${w}`);
  await page.screenshot({ path: `${OUT_DIR}/collections-${w}.png`, fullPage: false });
}

// Exercise the hamburger menu at mobile width on the collections page.
await page.setViewportSize({ width: 375, height: HEIGHT });
await page.waitForTimeout(300);
const menuBtn = page.locator('button[aria-label="Open navigation menu"]');
if (await menuBtn.count()) {
  await menuBtn.click();
  await page.waitForTimeout(300);
  await measure('collections-menu-open@375');
  await page.screenshot({ path: `${OUT_DIR}/collections-menu-open-375.png`, fullPage: false });
  // click a nav item, verify it navigates + closes the menu
  const workersTab = page.getByText('Workers', { exact: true }).first();
  await workersTab.click().catch(() => {});
  await page.waitForTimeout(600);
  await measure('workers-after-menu-nav@375');
  await page.screenshot({ path: `${OUT_DIR}/workers-after-menu-nav-375.png`, fullPage: false });
}

// New-collection wizard (has the stepper + PageHeader actions).
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(600);
for (const w of WIDTHS) {
  await page.setViewportSize({ width: w, height: HEIGHT });
  await page.waitForTimeout(200);
  const newBtn = page.getByText('New collection', { exact: false }).first();
  if (await newBtn.count()) { await newBtn.click({ timeout: 3000 }).catch(() => {}); await page.waitForTimeout(500); }
  await measure(`new-collection@${w}`);
  await page.screenshot({ path: `${OUT_DIR}/new-collection-${w}.png`, fullPage: false });
}

console.log(JSON.stringify(results, null, 2));
await browser.close();
