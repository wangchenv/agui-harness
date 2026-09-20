const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

const url = pathToFileURL(path.join(__dirname, 'index.html')).href;
async function visit(page, target, defect) {
  await page.goto(target);
  if (defect) {
    // Mutate real rendering: an interrupted response incorrectly exposes review.
    await page.evaluate(() => {
      const original = window.cardHTML;
      window.cardHTML = (ticket, draft) => original(ticket, draft) +
        (draft.phase === 'interrupted' ? '<button data-action="review">Unsafe review</button>' : '');
    });
  }
}
const cases = [
  { id: 'responsive_layout', async run({ page, url }) {
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await visit(page, url, false);
      const measurements = await page.evaluate(() => ({
        width: innerWidth, content: document.documentElement.scrollWidth,
        heading: document.querySelector('#workspace-title').getBoundingClientRect().width,
      }));
      assert.ok(measurements.content <= measurements.width, `horizontal overflow at ${width}px`);
      assert.ok(measurements.heading > 0);
    }
  }},
  { id: 'keyboard_navigation', async run({ page, url }) {
    await visit(page, url, false);
    await page.locator('#priority-select').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('[data-action="draft"]').evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Enter');
    const review = page.locator('[data-action="review"]'); await review.waitFor();
    await review.focus(); await page.keyboard.press('Enter');
    await page.locator('#approval-dialog[open]').waitFor();
    await page.keyboard.press('Escape');
    await page.locator('#approval-dialog[open]').waitFor({ state: 'hidden' });
    assert.equal(await review.evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Enter');
    await page.locator('#approval-dialog[open]').waitFor();
    await page.locator('#confirm-approval').focus(); await page.keyboard.press('Enter');
    await page.locator('.state-card.success').waitFor();
    assert.match(await page.locator('.receipt-details .id').innerText(), /^REC-/);
  }},
  { id: 'ui_state_recovery', async run({ page, url, defect }) {
    await visit(page, url, defect);
    await page.locator('#scenario-select').selectOption('disconnect');
    await page.locator('[data-action="draft"]').click();
    await page.locator('[data-action="retry"]').waitFor();
    assert.equal(await page.locator('[data-action="review"]').count(), 0, 'interrupted output must not expose review');
    assert.equal(await page.locator('.receipt-details').count(), 0);
    await visit(page, url, false);
    await page.locator('#scenario-select').selectOption('unknown');
    await page.locator('[data-action="draft"]').click();
    await page.locator('[data-action="review"]').click();
    await page.locator('#confirm-approval').click();
    await page.locator('[data-action="reconcile"]').waitFor();
    assert.equal(await page.locator('[data-action="draft"]').isDisabled(), true);
    assert.equal(await page.locator('[data-action="review"]').count(), 0);
    await page.locator('[data-action="reconcile"]').click();
    await page.locator('.state-card.success').waitFor();
    assert.match(await page.locator('.receipt-details .id').innerText(), /^REC-/);
    await page.locator('[data-action="view-record"]').click();
    assert.equal(await page.locator('#activity-content .activity-list li').filter({ hasText: '模拟记录' }).count(), 1);
  }},
];
module.exports = { url, cases };
