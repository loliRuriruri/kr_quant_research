// Playwright CLI white-box fault injection: no collector, report generation or writes.
async (page) => {
  await page.setViewportSize({width: 1280, height: 900});
  await page.reload();
  await page.waitForFunction(() => typeof openStock === 'function');
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/results/stock/005930', async route => {
    await gate;
    await route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({detail: 'A-late-response'})});
  });
  await page.route('**/api/results/stock/000660', route => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({detail: 'B-current-response'})
  }));
  await page.evaluate(() => { window.drawerA = openStock('005930'); });
  await page.evaluate(() => openStock('000660'));
  const before = await page.locator('#drawer-body').innerText();
  release();
  await page.evaluate(() => window.drawerA);
  const after = await page.locator('#drawer-body').innerText();
  const result = {before, after, latestSelectionPreserved: before === after && after.includes('B-current-response')};
  await page.unroute('**/api/results/stock/005930');
  await page.unroute('**/api/results/stock/000660');
  return result;
}
