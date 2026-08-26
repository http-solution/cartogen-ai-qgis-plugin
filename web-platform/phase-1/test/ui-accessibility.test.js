const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const file = path.join(__dirname, '..', 'index.html');
const html = fs.readFileSync(file, 'utf8');

function scriptSource() {
  return [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(match => match[1]).join('\n');
}

test('workspace controls have names, one h1, and one drawing implementation', () => {
  assert.match(html, /<h1\b[^>]*>[^<]+<\/h1>/i);
  for (const id of ['chatInput', 'basemap', 'reportPaper', 'reportOrientation']) {
    const control = html.match(new RegExp(`<(?:textarea|select)[^>]*\\bid=["']${id}["'][^>]*>`, 'i'))?.[0] || '';
    assert.ok(/aria-label=|aria-labelledby=/.test(control) || new RegExp(`for=["']${id}["']`, 'i').test(html), `${id} needs an accessible name`);
  }
  assert.equal((scriptSource().match(/function\s+drawGeometry\s*\(/g) || []).length, 1);
  assert.equal((scriptSource().match(/function\s+renderDrawing\s*\(/g) || []).length, 1);
  assert.match(html, /@media\s*\(prefers-reduced-motion:\s*reduce\)/i);
  assert.match(html, /:focus-visible/);
});

test('workspace has no horizontal overflow at required viewports', async t => {
  const browser = await chromium.launch({ headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  for (const width of [375, 768, 1280, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`file://${file.replace(/\\/g, '/')}`, { waitUntil: 'domcontentloaded' });
    const result = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
    assert.ok(result.scrollWidth <= result.innerWidth, `${width}px viewport overflows: ${JSON.stringify(result)}`);
  }
});
