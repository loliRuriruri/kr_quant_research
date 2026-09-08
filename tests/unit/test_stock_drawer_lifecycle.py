"""Run the actual JS drawer functions with deterministic deferred requests."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def test_stock_drawer_latest_owner_close_and_async_extras(tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node required')
    source = (Path(__file__).resolve().parents[2] / 'src/kr_quant/web/static/app.js').read_text(encoding='utf-8')
    functions = []
    for name in ['closeDrawer', 'openDrawerUi', 'openStock', 'loadTier1StockInsights', 'loadReport']:
        functions.append(re.search(r'(?:async )?function ' + name + r'\([^\n]*\) \{.*?\n\}', source, re.S).group())
    script = r'''
const assert = require('node:assert/strict');
const nodes = new Map();
function $(id) {
 if (!nodes.has(id)) { const classes=new Set(); nodes.set(id, {innerHTML:'',textContent:'',style:{},
 classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c)},
 addEventListener(type,fn){this[type]=fn;}}); }
 return nodes.get(id);
}
const document={body:{classList:{remove(){},add(){}}}};
const padTicker = t => String(t).padStart(6,'0');
const escapeHtml = s => String(s);
let publicShareMode = false;
let stockDrawerRequest=0, pending=[], rendered=[];
const api=path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject}));
const renderReport=row=>rendered.push(row);
''' + '\n'.join(functions) + r'''
(async()=>{
 for (const success of [false,true]) {
  const a=openStock('005930'), b=openStock('000660');
  const first=pending.shift(), second=pending.shift();
  second.reject(new Error('current B')); await b;
  const content=$('#drawer-body').innerHTML;
  if(success) first.resolve({row:{ticker:'005930'}}); else first.reject(new Error('stale A'));
  await a; assert.equal($('#drawer-body').innerHTML,content);
  assert(content.includes('current B'));
 }
 const late=openStock('005930'); const first=pending.shift(); closeDrawer();
 const content=$('#drawer-body').innerHTML;
 first.reject(new Error('closed')); await late;
 assert($('#drawer').classList.contains('hidden'));
 assert.equal($('#drawer-body').innerHTML,content);
 assert.equal($('#global-progress-bar').style.display,'none');
 const report=loadReport('005930',undefined,()=>false);
 pending.shift().resolve({exists:true,row:{ticker:'005930'}}); await report;
 assert.equal(rendered.length,0);
 const insights=loadTier1StockInsights('005930',()=>false);
 pending.shift().resolve({ok:true}); await insights;
 const wrong=openStock('005930'); pending.shift().resolve({row:{ticker:'000660'}}); await wrong;
 assert($('#drawer-body').innerHTML.includes('요청 종목과 응답 종목'));
 assert.equal(typeof $('#stock-detail-retry').click,'function');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    script_file = tmp_path / 'runner.js'
    script_file.write_text(script, encoding='utf-8')
    result = subprocess.run(['node', str(script_file)], capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr

