// Browser UI smoke checks. Does not click collection, portfolio writes or compute buttons.
async (page) => {
  await page.setViewportSize({width:1280,height:900});
  await page.reload();
  const posts=[], errors=[], result={};
  page.on('request', req=>{if(req.method()==='POST')posts.push(req.url());});
  page.on('pageerror', error=>errors.push(error.message));
  async function visit(name) {
    await page.locator(`.nav-btn[data-view="${name}"]`).click();
    await page.waitForFunction(n=>!viewPending.has(n),name);
    result[name]=await page.locator(`#view-${name}`).evaluate(el=>({state:el.querySelector('.view-load-state')?.dataset.state}));
  }
  await visit('rank');
  await page.locator('#rank-q').fill('현대');
  result.rank.search=await page.locator('#rank-body tr').allInnerTexts();
  result.rank.matches=await page.locator('#rank-body tr').count();
  await page.locator('#rank-q').fill('');
  await visit('trade');
  await page.locator('#trade-universe').selectOption('outside');
  result.trade.universe=await page.locator('#trade-universe').inputValue();
  await page.locator('#flow-q').fill('존재하지않는종목QA');
  result.trade.emptySearch=await page.locator('#view-trade').innerText();
  await page.locator('#flow-q').fill('');
  await page.locator('#trade-universe').selectOption('all');
  await visit('watch');
  const stock=page.locator('#view-watch [data-open]').first();
  if(await stock.count()) {
    const code=await stock.getAttribute('data-open');
    await stock.click();
    await page.waitForFunction(code=>{
      const title=document.querySelector('#drawer-title').textContent;
      return title.includes(`(${code})`) && !title.includes('로딩 중');
    },code,{timeout:60000});
    result.watch.detailTitle=await page.locator('#drawer-title').innerText();
    await page.locator('#drawer-close').click();
    result.watch.closed=await page.locator('#drawer').evaluate(el=>el.classList.contains('hidden'));
  } else result.watch.detail='no saved watchlist row';
  await visit('strategy');
  result.strategy.savedResultVisible=await page.locator('#strategy-box').innerText();
  result.posts=posts; result.errors=errors;
  // Only compact facts; no report bodies or user positions in the tool output.
  result.rank.searchMatchesAll = result.rank.matches>0 && result.rank.search.every(row=>row.includes('현대'));
  delete result.rank.search;
  result.trade.emptyStateVisible=/종목이 없습니다/.test(result.trade.emptySearch);
  delete result.trade.emptySearch;
  result.strategy.savedResultVisible=Boolean(result.strategy.savedResultVisible.trim());
  return result;
}
