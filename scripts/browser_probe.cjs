#!/usr/bin/env node
// Project suites are trusted programs. This runner does not sandbox them.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { parseArgs } = require('node:util');
const { chromium } = require('playwright');

async function main() {
  const { values } = parseArgs({ options: {
    suite: { type: 'string' }, url: { type: 'string' },
    'inject-defect': { type: 'boolean', default: false },
  }});
  if (!values.suite) throw new Error('--suite is required');
  const root = fs.realpathSync(process.env.AGUI_PROJECT_ROOT || process.cwd());
  const suite = require(path.resolve(values.suite));
  const cases = suite.cases;
  if (!Array.isArray(cases) || !cases.length || new Set(cases.map(c => c.id)).size !== cases.length ||
      cases.some(c => !/^[a-z][a-z0-9_-]*$/.test(c.id) || typeof c.run !== 'function'))
    throw new Error('Suite must provide unique cases with executable functions');
  const base = path.resolve(process.env.AGUI_ARTIFACT_DIR || path.join(root, '.agui/evidence/browser-artifacts'));
  const directory = path.join(base, crypto.randomUUID());
  if (path.relative(root, directory).startsWith('..') || path.isAbsolute(path.relative(root, directory)))
    throw new Error('Artifact directory must be inside the project');
  fs.mkdirSync(directory, { recursive: true });
  const browser = await chromium.launch({ headless: true,
    ...(process.env.AGUI_BROWSER_EXECUTABLE ? { executablePath: process.env.AGUI_BROWSER_EXECUTABLE } : {}) });
  const results = [], artifacts = [];
  function recordArtifact(filename) {
    artifacts.push({ path: path.relative(root, filename).split(path.sep).join('/'),
      sha256: crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex') });
  }
  try {
    for (const test of cases) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
      const page = await context.newPage(); page.setDefaultTimeout(7000);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let result = { id: test.id, status: 'passed', detail: 'Actual Chromium assertions completed.' };
      try {
        await test.run({ page, context, url: values.url || suite.url, defect: values['inject-defect'] });
        if (errors.length) throw new Error(`Browser raised ${errors.length} JavaScript errors`);
      } catch (error) { result = { id: test.id, status: 'failed', detail: String(error.message).slice(0,1000) }; }
      finally {
        const shot = path.join(directory, `${test.id}.png`);
        const trace = path.join(directory, `${test.id}.zip`);
        try { await page.screenshot({ path: shot, fullPage: true }); recordArtifact(shot); }
        catch { result.status = 'failed'; result.detail += ' Screenshot capture failed.'; }
        try { await context.tracing.stop({ path: trace }); recordArtifact(trace); }
        catch { result.status = 'failed'; result.detail += ' Trace capture failed.'; }
        await context.close();
      }
      results.push(result);
    }
  } finally { await browser.close(); }
  const metadata = path.join(directory, 'run.json');
  fs.writeFileSync(metadata, JSON.stringify({ browser_version: browser.version(),
    playwright_version: require('playwright/package.json').version, defect: values['inject-defect'],
    suite: path.relative(root, path.resolve(values.suite)), cases: results }, null, 2));
  recordArtifact(metadata);
  const report = { schema_version: 1, context: { execution_mode: 'browser' }, cases: results, artifacts };
  const encoded = JSON.stringify(report, null, 2) + '\n';
  if (process.env.AGUI_EVIDENCE_OUTPUT) fs.writeFileSync(process.env.AGUI_EVIDENCE_OUTPUT, encoded);
  process.stdout.write(encoded);
  process.exitCode = results.every(c => c.status === 'passed') ? 0 : 1;
}
main().catch(error => { process.stderr.write(String(error.message) + '\n'); process.exitCode = 1; });
