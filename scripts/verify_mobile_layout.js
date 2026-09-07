// Read-only navigation/layout smoke check for playwright-cli run-code.
async (page) => {
  const results = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.locator('#layout-mode').selectOption('auto');
  for (const width of [390, 700, 1280]) {
    await page.setViewportSize({width, height:844});
    for (const name of ['dash', 'rank', 'trade', 'seasonality', 'run']) {
      if (await page.locator('#compact-menu-toggle').isVisible()) await page.locator('#compact-menu-toggle').click();
      await page.locator(`.nav-btn[data-view="${name}"]`).click();
      await page.waitForFunction(n => !viewPending.has(n), name);
      results.push(await page.evaluate(({width, name}) => ({width, name,
        viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
        mainWidth: document.querySelector('main').clientWidth,
        menuClosed: !document.body.classList.contains('compact-menu-open'),
        state: document.querySelector(`#view-${name} .view-load-state`)?.dataset.state
      }), {width, name}));
    }
  }
  await page.setViewportSize({width:390, height:844});
  await page.locator('#layout-mode').selectOption('desktop');
  await page.reload();
  const savedDesktop = await page.evaluate(() => document.documentElement.dataset.layout === 'desktop' && document.body.scrollWidth >= 1200);
  await page.locator('#layout-mode').selectOption('auto');
  await page.reload();
  await page.waitForFunction(() => !viewPending.has('dash') && document.querySelector('#view-dash .view-load-state')?.dataset.state === 'ready');
  await page.locator('#compact-menu-toggle').click();
  await page.keyboard.press('Escape');
  const escapeClosed = await page.locator('#compact-menu-toggle').getAttribute('aria-expanded') === 'false';
  await page.screenshot({path:'output/playwright/mobile-layout-390.png'});
  return {results, savedDesktop, escapeClosed, errors};
}
