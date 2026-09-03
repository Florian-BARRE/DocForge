// ====== Contrast verification for the a11y micro-fixes ======
// Opens the New-collection wizard (stepper "1") and a collection's Search Lab (a hit's "view page"
// link), then reads live computed styles + relative luminance in-page to report WCAG contrast
// ratios against the actual rendered background — a static hex diff can't catch surface tinting.
//
// Usage: node a11y-check.mjs [--base http://localhost:10046]

import { chromium } from 'playwright';

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i === -1 ? d : process.argv[i + 1]; };
const BASE = process.env.GF_URL || arg('base', 'http://localhost:10046');

function relLum(rgbString) {
  const m = rgbString.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!m) return null;
  const [r, g, b] = [m[1], m[2], m[3]].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrastRatio(fg, bg) {
  const L1 = relLum(fg), L2 = relLum(bg);
  if (L1 == null || L2 == null) return null;
  const [hi, lo] = L1 > L2 ? [L1, L2] : [L2, L1];
  return (hi + 0.05) / (lo + 0.05);
}

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
const page = await ctx.newPage();
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

const results = {};

// 1. Wizard stepper "1" — Collections tab -> "New collection".
await page.getByText('Collections', { exact: false }).first().click().catch(() => {});
await page.waitForTimeout(600);
await page.getByText('New collection', { exact: false }).first().click().catch(() => {});
await page.waitForTimeout(800);
const wizardRaw = await page.evaluate(() => {
  const spans = [...document.querySelectorAll('span')].filter((s) => s.textContent.trim() === '1');
  const el = spans.find((s) => {
    const cs = getComputedStyle(s);
    return cs.borderRadius && parseInt(cs.borderRadius) > 8;
  }) || spans[0];
  if (!el) return { found: false };
  const cs = getComputedStyle(el);
  return {
    found: true,
    text: el.textContent,
    color: cs.color,
    background: cs.backgroundColor,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
  };
});
results.wizardStepOne = wizardRaw.found
  ? { ...wizardRaw, ratio: contrastRatio(wizardRaw.color, wizardRaw.background) }
  : wizardRaw;

// 2. Search hit "view page" link — first collection -> Search tab -> run a query.
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
await page.getByText('Demo — Acme Handbook', { exact: false }).first().click().catch(() => {});
await page.waitForTimeout(800);
await page.getByText('Search', { exact: false }).first().click().catch(() => {});
await page.waitForTimeout(800);
const searchInput = page.locator('input[aria-label="Search this collection"]');
if (await searchInput.count()) {
  await searchInput.fill('policy');
  await searchInput.press('Enter');
  await page.waitForTimeout(2500);
}
const linkRaw = await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'view page');
  if (!btn) return { found: false };
  const cs = getComputedStyle(btn);
  return { found: true, color: cs.color, background: cs.backgroundColor, fontSize: cs.fontSize };
});
results.viewPageLink = linkRaw.found
  ? { ...linkRaw, ratio: contrastRatio(linkRaw.color, linkRaw.background) }
  : linkRaw;

console.log(JSON.stringify(results, null, 2));
await browser.close();
