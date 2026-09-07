// Run via playwright-cli run-code --filename=scripts/verify_loading_item1_browser.js.
// Requires an open local-app browser. Does not click collection or mutation buttons.
async (page) => {
  await page.reload();
  await page.waitForFunction(() => typeof viewPending !== 'undefined' && viewPending.size === 0);
  const posts = [];
  page.on('request', r => { if (r.method() === 'POST') posts.push(r.url()); });
  const results = [];
  for (const name of ['rank', 'screens', 'sector', 'trade', 'watch', 'seasonality', 'strategy', 'market', 'investor', 'us13f', 'dash']) {
    await page.locator(`.nav-btn[data-view="${name}"]`).click();
    await page.waitForFunction(n => !viewPending.has(n), name);
    results.push(await page.locator(`#view-${name}`).evaluate(el => ({
      name: el.id, ms: el.dataset.loadMs,
      state: el.querySelector('.view-load-state')?.dataset.state
    })));
  }
  const result = { results, posts };
  console.log(JSON.stringify(result));
  return result;
}
