const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Regression guard: index.html's "Apply confirmed edit" button must send the
// server's actual contract (mode:'apply' + preview_token). server.js's
// normalizeFeatureEditRequest defaults `mode` to 'preview' when the field is
// absent, so a request shaped like the old {preview:false, approved:true}
// silently executes as a preview (rolled back, nothing persisted) while the
// UI still shows a success toast. See normalizeFeatureEditRequest in server.js
// and the /api/layers/:layerId/features/:featureId/edit route.
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const script = html.slice(html.indexOf('<script>') + '<script>'.length, html.lastIndexOf('</script>'));

function extractFunction(source, name) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `${name} not found in index.html`);
  let depth = 0, i = start, seenOpen = false;
  for (; i < source.length; i += 1) {
    if (source[i] === '{') { depth += 1; seenOpen = true; }
    else if (source[i] === '}') { depth -= 1; if (seenOpen && depth === 0) { i += 1; break; } }
  }
  return source.slice(start, i);
}

test('applyFeatureEdit sends the server-recognized mode/preview_token apply contract', () => {
  const fn = extractFunction(script, 'applyFeatureEdit');
  assert.match(fn, /mode:\s*'apply'/, 'apply request must set mode:\'apply\' — the server ignores unrecognized shapes and silently no-ops as a preview');
  assert.match(fn, /preview_token/, 'apply request must include the preview_token returned by the preceding preview call');
  assert.match(fn, /approved:\s*true/, 'apply request must set approved:true');
});

test('previewFeatureEdit explicitly requests preview mode', () => {
  const fn = extractFunction(script, 'previewFeatureEdit');
  assert.match(fn, /mode:\s*'preview'/, 'preview request should explicitly set mode:\'preview\' rather than relying on the server default');
});
