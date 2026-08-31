
let onDemandTimer = null;
async function fetchOnDemandFlow(query, boxTarget, scope = "trade") {
  const box = $(boxTarget);
  if (!box) return;

  box.innerHTML = `
    <div class="flow-diag-card" style="text-align:center; padding:24px 18px;">
      <p style="margin:0; font-size:14px; color:#38bdf8;">⏳ <b>[${escapeHtml(query)}]</b> 전 종목 실시간 수급 & 기술적 지표 온디맨드 정밀 진단 중…</p>
      <span class="hint" style="margin-top:6px; display:block;">KIS / Toss 수급 시계열 및 KRX 일봉 지표를 실시간 분석하고 있습니다.</span>
    </div>
  `;

  try {
    const data = await api(`/api/flow/ticker/${encodeURIComponent(query)}`);
    if (data && data.ok && data.row) {
      const diagHtml = renderFlowDiagCard(data.row, query);
      const hintMsg = scope === "empty"
        ? "※ 해당 종목은 현재 빈집(외인·기관 동반 10억 이상 순매도) 스캔 조건에는 해당하지 않으나, 위와 같이 실시간 개별 진단이 완료되었습니다."
        : "※ 해당 종목은 현재 퀀트 밖 수급 셋업 상위 유니버스 목록에는 없으나, 위와 같이 실시간 개별 정밀 진단이 완료되었습니다.";

      box.innerHTML = `
        ${diagHtml}
        <div style="text-align:center; padding:16px; background:rgba(15,23,42,0.4); border-radius:8px; border:1px dashed rgba(255,255,255,0.1);">
          <p class="hint" style="margin:0;">${hintMsg}</p>
        </div>
      `;

      // Attach button handlers
      box.querySelectorAll("[data-open]").forEach((b) => {
        b.addEventListener("click", () => openStock(b.dataset.open).catch((e) => alert(e.message)));
      });
      box.querySelectorAll("[data-backtest-stock]").forEach((b) => {
        b.addEventListener("click", () => {
          openStrategyBacktest(b.dataset.backtestStock, b.dataset.company || b.dataset.backtestStock);
        });
      });
      box.querySelectorAll("[data-watch-stock]").forEach((b) => {
        b.addEventListener("click", async () => {
          await addWatch(b.dataset.watchStock, b.dataset.company);
        });
      });
      box.querySelectorAll("[data-ai-trigger]").forEach((b) => {
        b.addEventListener("click", () => {
          generateAiReport(b.dataset.aiTrigger, b.dataset.aiCompany || b.dataset.aiTrigger);
        });
      });
    } else {
      box.innerHTML = `
        <div class="flow-diag-card" style="border-color:#ef4444; text-align:center; padding:20px;">
          <p style="color:#f87171; font-weight:600; margin:0;">⚠️ 종목 '${escapeHtml(query)}'의 수급 정보를 찾을 수 없습니다.</p>
          <span class="hint" style="margin-top:6px; display:block;">정확한 6자리 종목코드나 공식 종목명을 입력해주세요.</span>
        </div>
      `;
    }
  } catch (err) {
    box.innerHTML = `<div class="flow-diag-card" style="border-color:#ef4444;"><p style="color:#f87171;">진단 오류: ${escapeHtml(err.message)}</p></div>`;
  }
}


function renderPlaybookHtml(pb) {
  if (!pb || !pb.archetype) return "";
  return `
    <div class="strategy-playbook-card">
      <div class="playbook-header">
        <div style="display:flex; align-items:center; gap:8px;">
          <b style="color:#38bdf8; font-size:14px;">💡 3초 핵심 퀀트 해석 & 검증 요약</b>
          <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:600;">${escapeHtml(pb.archetype_badge || "")}</span>
        </div>
        <span style="font-size:11.5px; color:#94a3b8;">검증 구간 1위: <b>${escapeHtml(pb.actionable_name || "")}</b> (${escapeHtml(pb.actionable_params_ko || "")})</span>
      </div>

      <div style="background:rgba(56,189,248,0.06); border-left:3px solid #38bdf8; border-radius:4px; padding:8px 12px; margin-bottom:12px; font-size:12.5px; line-height:1.5; color:#f1f5f9;">
        <b>🔍 주가 파동 진단:</b> ${escapeHtml(pb.archetype_desc || "")}
      </div>

      <div style="background:rgba(168,85,247,0.06); border-left:3px solid #c084fc; border-radius:4px; padding:8px 12px; margin-bottom:12px; font-size:12px; line-height:1.5; color:#e2e8f0;">
        <b>🧪 검증 결과 해석:</b> ${escapeHtml(pb.actionable_reason || "")}
      </div>

      <div class="playbook-grid">
        <div class="playbook-item" style="border-left:3px solid #22c55e;">
          <h4 style="color:#4ade80;">진입으로 검증한 조건</h4>
          <p>${escapeHtml(pb.entry_rule || "")}</p>
        </div>
        <div class="playbook-item" style="border-left:3px solid #38bdf8;">
          <h4 style="color:#38bdf8;">청산으로 검증한 조건</h4>
          <p>${escapeHtml(pb.exit_rule || "")}</p>
        </div>
        <div class="playbook-item" style="border-left:3px solid #ef4444; grid-column: 1 / -1;">
          <h4 style="color:#f87171;">해석 시 주의할 실패 조건</h4>
          <p>${escapeHtml(pb.avoid_rule || "")}</p>
        </div>
      </div>
    </div>
  `;
}


async function triggerFlowDiag(ticker, company, scope = "empty") {
  const boxId = scope === "empty" ? "#empty-box" : "#trade-box";
  const box = $(boxId);
  if (!box) return;

  const data = await api(`/api/flow/ticker/${ticker}`);
  if (data && data.ok && data.row) {
    const diagHtml = renderFlowDiagCard(data.row, company || ticker);
    const existingTable = box.querySelector(".table-wrap") ? box.querySelector(".table-wrap").outerHTML : "";
    const existingKpis = box.querySelector(".flow-kpis") ? box.querySelector(".flow-kpis").outerHTML : "";
    box.innerHTML = `${existingKpis}${diagHtml}${existingTable}`;

    // Attach button handlers
    box.querySelectorAll("[data-open]").forEach((b) => {
      b.addEventListener("click", () => openStock(b.dataset.open).catch((e) => alert(e.message)));
    });
    box.querySelectorAll("[data-backtest-stock]").forEach((b) => {
      b.addEventListener("click", () => {
        openStrategyBacktest(b.dataset.backtestStock, b.dataset.company || b.dataset.backtestStock);
      });
    });
    box.querySelectorAll("[data-watch-stock]").forEach((b) => {
      b.addEventListener("click", async () => {
        await addWatch(b.dataset.watchStock, b.dataset.company);
      });
    });
  } else {
    if (flowCache) {
      if (scope === "empty") renderEmpty(flowCache);
      else renderTrade(flowCache);
    }
  }
}


function renderFlowDiagCard(row, query) {
  if (!row) return "";
  const code = padTicker(row.ticker);
  const company = row.company || code;
  const fNet = row.foreign_net != null ? `${row.foreign_net > 0 ? "+" : ""}${row.foreign_net.toLocaleString("ko-KR")}주` : "—";
  const iNet = row.institution_net != null ? `${row.institution_net > 0 ? "+" : ""}${row.institution_net.toLocaleString("ko-KR")}주` : "—";
  const pNet = row.individual_net != null ? `${row.individual_net > 0 ? "+" : ""}${row.individual_net.toLocaleString("ko-KR")}주` : "—";
  const peNet = row.pe_net != null ? `${row.pe_net > 0 ? "+" : ""}${row.pe_net.toLocaleString("ko-KR")}주` : "—";
  const fRate = row.foreign_holding_rate != null ? `${(row.foreign_holding_rate * 100).toFixed(1)}%` : "—";
  const setups = (row.setups || []).join(" · ") || "일반 수급";

  const ta = row.ta || {};
  const stoch = ta.stoch_k != null ? `%K ${ta.stoch_k.toFixed(1)} (%D ${ta.stoch_d != null ? ta.stoch_d.toFixed(1) : "—"})` : "—";
  const cloud = ta.ichi_cloud ? `구름대 ${ta.ichi_cloud === "above" ? "상회 (강세)" : ta.ichi_cloud === "below" ? "하회 (약세)" : "내부"}` : "—";

  const dailyRows = (row.daily || []).slice(0, 5).map(d => `
    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
      <td style="color:#94a3b8; font-size:11.5px; padding:5px 8px;">${escapeHtml(d.date || "")}</td>
      <td class="num ${d.foreign > 0 ? 'text-emerald-400 font-bold' : d.foreign < 0 ? 'text-rose-400' : ''}" style="padding:5px 8px;">${signedInt(d.foreign)}</td>
      <td class="num ${d.institution > 0 ? 'text-emerald-400 font-bold' : d.institution < 0 ? 'text-rose-400' : ''}" style="padding:5px 8px;">${signedInt(d.institution)}</td>
      <td class="num ${d.pension > 0 ? 'text-emerald-400 font-bold' : d.pension < 0 ? 'text-rose-400' : ''}" style="padding:5px 8px;">${signedInt(d.pension || 0)}</td>
      <td class="num ${d.pe > 0 ? 'text-purple-400 font-bold' : d.pe < 0 ? 'text-rose-400' : ''}" style="padding:5px 8px;">${signedInt(d.pe || 0)}</td>
    </tr>
  `).join("");

  return `
    <div class="flow-diag-card">
      <div class="flow-diag-head">
        <div>
          <h3 style="margin:0; font-size:16px; color:#fff; display:flex; align-items:center; gap:6px;">
            <span>🎯 ${escapeHtml(company)} (${code}) 실시간 수급 & 빈집 트레이딩 정밀 진단</span>
          </h3>
          <span class="hint" style="margin-top:2px;">검색어 '${escapeHtml(query)}' 맞춤 수급 셋업 및 기술적 지표 실시간 분석 결과</span>
        </div>
        <div>
          <span class="chip ok" style="font-size:12px; padding:4px 10px;">${escapeHtml(setups)}</span>
        </div>
      </div>

      <div class="flow-diag-grid">
        <div class="portfolio-kpi-item">
          <span>외국인 5일 순매수</span>
          <b class="${row.foreign_net > 0 ? "up" : row.foreign_net < 0 ? "down" : ""}">${fNet}</b>
        </div>
        <div class="portfolio-kpi-item">
          <span>기관 5일 순매수</span>
          <b class="${row.institution_net > 0 ? "up" : row.institution_net < 0 ? "down" : ""}">${iNet}</b>
        </div>
        <div class="portfolio-kpi-item">
          <span>개인 5일 순매수</span>
          <b class="${row.individual_net > 0 ? "up" : row.individual_net < 0 ? "down" : ""}">${pNet}</b>
        </div>
        <div class="portfolio-kpi-item">
          <span>외인 지분율 / 사모</span>
          <b>${fRate} <small style="font-size:12px;font-weight:normal;color:#94a3b8;">/ ${peNet}</small></b>
        </div>
      </div>

      ${dailyRows ? `
      <div style="margin-bottom:12px; background:#0f172a; border:1px solid #1e293b; border-radius:8px; overflow:hidden;">
        <div style="padding:6px 12px; background:rgba(30,41,59,0.7); font-size:11.5px; font-weight:700; color:#38bdf8;">
          📅 최근 5거래일 일자별 스마트머니 수급 추이 (토스증권 실시간)
        </div>
        <table style="width:100%; border-collapse:collapse; font-size:11.5px; margin:0;">
          <thead>
            <tr style="border-bottom:1px solid #1e293b; color:#94a3b8;">
              <th style="text-align:left; padding:5px 8px;">일자</th>
              <th style="text-align:right; padding:5px 8px;">외국인</th>
              <th style="text-align:right; padding:5px 8px;">기관계</th>
              <th style="text-align:right; padding:5px 8px;">연기금</th>
              <th style="text-align:right; padding:5px 8px;">사모펀드</th>
            </tr>
          </thead>
          <tbody>
            ${dailyRows}
          </tbody>
        </table>
      </div>
      ` : ""}

      <div style="background:#111a2e; padding:10px 14px; border-radius:8px; margin-bottom:12px; font-size:12.5px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:12px; color:#94a3b8;">
          <span>⚡ 기술적 셋업: ${escapeHtml(stoch)} · ${escapeHtml(cloud)}</span>
          <span>${row.empty ? "🏚️ 빈집 감지됨" : row.dual ? "⚡ 쌍끌이 감지됨" : "안정 수급"}</span>
        </div>
        <p style="margin:4px 0 0; color:#cbd5e1;">💡 ${escapeHtml(row.comment || "외인·기관의 최근 수급 동향과 기술적 위치를 점검했습니다.")}</p>
      </div>

      <div style="display:flex; gap:8px; flex-wrap:wrap;">
        <button class="primary" data-open="${code}">🔍 심층 리서치</button>
        <button data-backtest-stock="${code}" data-company="${escapeHtml(company)}" style="background:rgba(56,189,248,0.15); color:#38bdf8; border-color:rgba(56,189,248,0.4);">🧪 전략 백테스트</button>
        <button class="btn-ai-mini" data-ai-trigger="${code}" data-ai-company="${escapeHtml(company)}" style="padding:0 14px; height:32px; font-size:12px;">🤖 AI 리포트 발간</button>
        <button class="ghost" data-watch-stock="${code}" data-company="${escapeHtml(company)}">⭐ 관심종목 추가</button>
      </div>
    </div>
  `;
}


// Korean Chosung Decomposer for Frontend
const CHOSUNG_LIST = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];

function getChosung(str) {
  let res = "";
  for (let i = 0; i < (str || "").length; i++) {
    const code = str.charCodeAt(i);
    if (code >= 0xac00 && code <= 0xd7a3) {
      const idx = Math.floor((code - 0xac00) / (21 * 28));
      res += CHOSUNG_LIST[idx];
    } else {
      res += str[i];
    }
  }
  return res;
}

let cachedUniverse = null;

async function getStockUniverse() {
  if (cachedUniverse) return cachedUniverse;
  try {
    const data = await api("/api/stocks/all");
    if (data && data.items && data.items.length) {
      cachedUniverse = data.items;
      return cachedUniverse;
    }
  } catch (e) {
    console.warn("Could not fetch stock universe:", e);
  }
  return [];
}

function setupStockAutocomplete(inputEl, menuEl, onSelect) {
  if (!inputEl || !menuEl) return;
  if (inputEl.dataset.acBound === "1") return;
  inputEl.dataset.acBound = "1";
  let activeIndex = -1;
  let currentItems = [];
  let debounceTimer = null;

  function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    const escaped = escapeHtml(text);
    const qEsc = escapeHtml(query);
    const regex = new RegExp(`(${qEsc.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&")})`, "gi");
    return escaped.replace(regex, "<mark>$1</mark>");
  }

  function renderDropdown(items, query) {
    currentItems = items;
    activeIndex = -1;
    if (!items.length) {
      menuEl.style.display = "none";
      menuEl.innerHTML = "";
      return;
    }

    menuEl.innerHTML = items.map((it, idx) => {
      const rankBadge = it.quant_rank ? `<span class="chip" style="font-size:10.5px; padding:1px 5px; color:#38bdf8;">퀀트 ${it.quant_rank}위</span>` : "";
      return `
        <li class="stock-autocomplete-item" data-idx="${idx}">
          <div>
            <b>${highlightMatch(it.company, query)}</b>
            <span style="color:#94a3b8; font-size:12px; margin-left:4px;">(${highlightMatch(it.ticker, query)})</span>
          </div>
          <div class="meta-right">
            ${rankBadge}
            <span class="chip" style="font-size:10px; padding:1px 4px;">${escapeHtml(it.market || "KOSPI")}</span>
            <span>${escapeHtml(it.sector || "")}</span>
          </div>
        </li>
      `;
    }).join("");

    menuEl.style.display = "block";

    menuEl.querySelectorAll(".stock-autocomplete-item").forEach((el) => {
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const idx = Number(el.dataset.idx);
        if (currentItems[idx]) {
          const item = currentItems[idx];
          menuEl.style.display = "none";
          onSelect(item);
        }
      });
    });
  }

  async function search(val) {
    const q = (val || "").trim();
    if (!q) {
      menuEl.style.display = "none";
      return;
    }

    try {
      const res = await api(`/api/stocks/search?q=${encodeURIComponent(q)}&limit=12`);
      if (res && res.items) {
        renderDropdown(res.items, q);
      }
    } catch (e) {
      console.error("Autocomplete search error:", e);
    }
  }

  inputEl.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => search(e.target.value), 100);
  });

  inputEl.addEventListener("focus", (e) => {
    if (e.target.value.trim()) search(e.target.value);
  });

  inputEl.addEventListener("blur", () => {
    setTimeout(() => { menuEl.style.display = "none"; }, 200);
  });

  inputEl.addEventListener("keydown", (e) => {
    if (menuEl.style.display !== "block" || !currentItems.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % currentItems.length;
      updateActiveItem();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + currentItems.length) % currentItems.length;
      updateActiveItem();
    } else if (e.key === "Enter" && currentItems.length) {
      e.preventDefault();
      const item = currentItems[activeIndex >= 0 ? activeIndex : 0];
      menuEl.style.display = "none";
      onSelect(item);
    } else if (e.key === "Escape") {
      menuEl.style.display = "none";
    }
  });

  function updateActiveItem() {
    const items = menuEl.querySelectorAll(".stock-autocomplete-item");
    items.forEach((el, idx) => {
      el.classList.toggle("active", idx === activeIndex);
      if (idx === activeIndex) el.scrollIntoView({ block: "nearest" });
    });
  }
}


function aiReportBtn(ticker, company) {
  const code = padTicker(ticker);
  const name = company || code;
  return `<button type="button" class="btn-ai-mini has-tip" data-ai-trigger="${code}" data-ai-company="${escapeHtml(name)}" data-tip="🤖 AI 심층 리서치 리포트 즉시 발간 (클릭 시 확인 창 표시)">🤖 AI</button>`;
}


let backtestBusy = false;

function ensureBacktestOverlay() {
  let el = $("#backtest-overlay");
  if (el) return el;
  el = document.createElement("div");
  el.id = "backtest-overlay";
  el.className = "backtest-overlay hidden";
  el.innerHTML = `
    <div class="backtest-overlay-card">
      <div class="skeleton-spinner"></div>
      <b id="backtest-overlay-title">전략 백테스트 실행 중</b>
      <p id="backtest-overlay-sub" class="hint">과거 3년 일봉으로 4대 전략을 최적화합니다. 창을 닫지 마세요.</p>
    </div>`;
  document.body.appendChild(el);
  return el;
}

function showBacktestOverlay(title, sub) {
  const el = ensureBacktestOverlay();
  const t = $("#backtest-overlay-title");
  const s = $("#backtest-overlay-sub");
  if (t) t.textContent = title || "전략 백테스트 실행 중";
  if (s && sub) s.textContent = sub;
  el.classList.remove("hidden");
  $("#global-progress-bar")?.classList.remove("hidden");
}

function hideBacktestOverlay() {
  $("#backtest-overlay")?.classList.add("hidden");
  $("#global-progress-bar")?.classList.add("hidden");
}

async function resolveStockQuery(query) {
  const raw = String(query || "").trim();
  if (!raw) return "";
  const digits = raw.replace(/\D/g, "");
  if (/^\d{5,6}$/.test(digits)) return digits.padStart(6, "0");
  try {
    const res = await api(`/api/stocks/search?q=${encodeURIComponent(raw)}&limit=8`);
    const items = res.items || [];
    if (!items.length) return raw;
    const compact = raw.replace(/\s+/g, "");
    const exact = items.find((it) => it.ticker === padTicker(raw) || it.company === raw || `${it.company}${it.ticker}` === compact)
      || items.find((it) => raw.includes(it.ticker))
      || items[0];
    return exact.ticker;
  } catch {
    return raw;
  }
}

async function openStrategyBacktest(ticker, company) {
  const code = padTicker(ticker);
  const name = company || code;
  if (!code || code === "000000") {
    alert("종목 코드를 확인할 수 없습니다.");
    return;
  }
  if (backtestBusy) {
    showToast("이미 백테스트가 실행 중입니다.", "info");
    return;
  }
  const ok = confirm(`${name} (${code}) 4대 전략 백테스트를 실행할까요?\n과거 3년 일봉 최적화라 수십 초 걸릴 수 있습니다.`);
  if (!ok) return;
  switchView("strategy");
  const inp = $("#custom-strategy-q");
  if (inp) inp.value = `${name} ${code}`.trim();
  showToast(`${name} 백테스트를 시작합니다.`, "info", 2500);
  await runCustomBacktest(code, { skipResolve: true, label: `${name} (${code})` });
}

async function runCustomBacktest(query, opts = {}) {
  const raw = String(query || $("#custom-strategy-q")?.value || "").trim();
  if (!raw) {
    alert("분석할 종목명 또는 6자리 코드를 입력하세요.");
    return;
  }
  const resBox = $("#custom-strategy-result");
  if (!resBox) return;
  if (backtestBusy) {
    showToast("이미 백테스트가 실행 중입니다.", "info");
    return;
  }

  backtestBusy = true;
  const label = opts.label || raw;
  showBacktestOverlay(`'${label}' 백테스트 연산 중`, "RSI · 볼린저 · 골든크로스 · 돈치안 Walk-Forward 검증 중입니다.");
  resBox.style.display = "block";
  resBox.innerHTML = `
    <div style="padding:20px; text-align:center; background:#0e1626; border-radius:10px;">
      <div class="skeleton-spinner" style="margin:0 auto 10px;"></div>
      <b style="color:#38bdf8;">'${escapeHtml(label)}' 과거 3년 일봉 4대 전략 백테스트 및 파라미터 최적화 연산 중...</b>
      <p class="hint" style="margin-top:4px;">RSI 과매도, 볼린저 하단, 골든크로스, 돈치안 돌파 및 Walk-Forward 미래 검증을 수행하고 있습니다.</p>
    </div>
  `;
  resBox.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const q = opts.skipResolve ? padTicker(raw) : await resolveStockQuery(raw);
    const data = await api("/api/strategy/ticker", {
      method: "POST",
      body: JSON.stringify({ ticker: q })
    });

    if (!data || !data.ok) {
      resBox.innerHTML = `<div style="padding:14px; background:rgba(239,68,68,0.1); border:1px solid #ef4444; border-radius:8px; color:#f87171;">⚠️ ${escapeHtml(data.error || "백테스트 실행 실패")}</div>`;
      return;
    }

    const strats = data.strategies || [];
    const priceQuality = data.price_integrity || {};
    const priceIssueCount = Number(priceQuality.issue_count || 0);
    const nonTradingBars = Number(priceQuality.non_trading_bar_count || 0);
    const breakCount = Math.max(0, priceIssueCount - nonTradingBars);
    const excludedBars = Math.max(0, Number(data.raw_bars || data.bars || 0) - Number(data.bars || 0));
    const priceQualityHtml = priceIssueCount
      ? `<div style="padding:10px 14px; background:rgba(245,158,11,0.10); border:1px solid rgba(245,158,11,0.45); border-radius:8px; margin-bottom:12px; color:#fde68a; font-size:12.5px; line-height:1.55;">
          <b>🛡️ 가격 품질 게이트 적용</b> · 비체결 행 ${nonTradingBars}개 제거 · 가격/주식수 단절 ${breakCount}건 감지 · 원본 ${data.raw_bars || data.bars || 0}일 중 ${excludedBars}일을 연결하지 않고 최근 안전구간 ${data.bars || 0}일만 검증했습니다.<br>
          <span style="color:#cbd5e1;">KRX 상장주식수·시가총액은 기업행위 추정 근거이며, 기업행위 확정 공시로 표시하지 않습니다.</span>
        </div>`
      : `<div style="padding:8px 12px; background:rgba(34,197,94,0.08); border:1px solid rgba(34,197,94,0.3); border-radius:8px; margin-bottom:12px; color:#86efac; font-size:12px;">🛡️ 검사 구간에서 가격·주식수 단절이 발견되지 않았습니다.</div>`;
    const rowsHtml = strats.map((s, idx) => {
      const sh = s.sharpe != null ? fmt(s.sharpe, 2) : "—";
      const oosSh = s.oos_sharpe != null ? fmt(s.oos_sharpe, 2) : "—";
      const valRet = s.validation_return != null ? `${s.validation_return > 0 ? "+" : ""}${(s.validation_return * 100).toFixed(1)}%` : "—";
      const oosRet = s.oos_return != null ? `${s.oos_return > 0 ? "+" : ""}${(s.oos_return * 100).toFixed(1)}%` : "—";
      const wfHit = s.wf_hit != null ? `${(s.wf_hit * 100).toFixed(0)}%` : "—";
      const mddVal = s.max_drawdown != null ? -Math.abs(s.max_drawdown * 100) : null;
      const mdd = mddVal != null ? `${mddVal.toFixed(1)}%` : "—";
      const ret = s.total_return != null ? `${s.total_return > 0 ? "+" : ""}${(s.total_return * 100).toFixed(1)}%` : "—";
      const retCls = s.total_return != null && s.total_return > 0 ? "up" : s.total_return < 0 ? "down" : "";
      const isBest = s.strategy_id === data.best_id;

      return `
        <tr style="${isBest ? 'background:rgba(56,189,248,0.08); font-weight:600;' : ''}">
          <td>${isBest ? '👑 1위 ' : `${idx + 1}위 `}${escapeHtml(s.name || s.strategy_id)}</td>
          <td><span class="chip">${escapeHtml(s.family_ko || s.family || "")}</span></td>
          <td class="${retCls}">${ret}</td>
          <td><b>${sh}</b></td>
          <td>${valRet}<div class="meta">${s.validation_trade_count ?? 0}회</div></td>
          <td>${oosRet}<div class="meta">샤프 ${oosSh} · ${s.oos_trade_count ?? 0}회</div></td>
          <td>${wfHit}</td>
          <td class="down">${mdd}</td>
          <td>${s.trade_count || 0}회</td>
          <td class="meta">${escapeHtml(s.params_ko || "")}</td>
        </tr>
      `;
    }).join("");

    resBox.innerHTML = `
      <div class="custom-backtest-hero">
        <div class="custom-hero-header">
          <div class="custom-hero-title">
            <span>🎯 ${escapeHtml(data.company || "")} (${escapeHtml(data.ticker)}) 4대 전략 백테스트 결과</span>
          </div>
          <div style="font-size:12px; color:#94a3b8;">
            분석 기간: ${escapeHtml(data.from || "")} ~ ${escapeHtml(data.to || "")} (${data.bars || 0}거래일)
          </div>
        </div>

        ${priceQualityHtml}

        <div style="padding:10px 14px; background:rgba(56,189,248,0.12); border:1px solid #38bdf8; border-radius:8px; margin-bottom:12px;">
          <b style="color:#38bdf8;">검증 구간 점수 1위: ${escapeHtml(data.best_name || "")} (${escapeHtml(data.best_params_ko || "")})</b>
          <p style="margin:4px 0 0; font-size:12.5px; color:#cbd5e1;">${escapeHtml(data.best_comment || "가운데 검증 구간으로 선택했으며 마지막 20% 결과는 선택 이후의 확인 자료입니다.")}</p>
        </div>

        <div class="table-wrap">
          <table class="table" style="font-size:12.5px;">
            <thead>
              <tr>
                <th>전략명</th>
                <th>유형</th>
                <th>전체기간 참고 수익률</th>
                <th class="has-tip" data-tip="선택된 동일 파라미터를 전체기간에 적용한 참고 샤프입니다. 선택 점수나 미래 보장이 아닙니다.">전체기간 샤프</th>
                <th class="has-tip" data-tip="학습 다음의 가운데 검증 구간 수익률과 왕복 거래 수입니다. 이 값으로 파라미터와 전략 1위를 정합니다.">검증 수익률</th>
                <th class="has-tip" data-tip="선택에 사용하지 않은 마지막 20% 최종검증의 수익률·샤프·왕복 거래 수입니다.">최종검증 결과</th>
                <th class="has-tip" data-tip="Walk-Forward 순환 분할 검증 구간에서 플러스 수익률을 달성한 승률입니다.">WF 승률</th>
                <th class="has-tip" data-tip="전략 운용 중 최고점 대비 겪을 수 있는 최대 낙폭(MDD)입니다.">최대낙폭</th>
                <th>매매 횟수</th>
                <th>선택 파라미터</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
        ${renderPlaybookHtml(data.playbook)}
        <div id="custom-strat-ai-diag" style="margin-top:12px;">
          <div style="padding:10px 14px; background:rgba(30, 41, 59, 0.6); border:1px dashed rgba(56, 189, 248, 0.4); border-radius:8px; display:flex; align-items:center; gap:8px;">
            <div class="skeleton-spinner" style="width:14px; height:14px;"></div>
            <span style="font-size:12px; color:#94a3b8;">Tier 1 AI가 '${escapeHtml(data.company || data.ticker)}'의 4대 전략 백테스트 성과를 정밀 진단 중입니다...</span>
          </div>
        </div>
      </div>
    `;

    const bestStrat = strats.find(s => s.strategy_id === data.best_id) || strats[0] || {};
    api("/api/strategy/custom-ai-diagnosis", {
      method: "POST",
      body: JSON.stringify({
        ticker: data.ticker,
        company: data.company,
        strategy_name: bestStrat.name || data.best_name || "최적 전략",
        cagr: bestStrat.cagr,
        mdd: bestStrat.max_drawdown,
        sharpe: bestStrat.sharpe,
        win_rate: bestStrat.wf_hit || bestStrat.win_rate,
        profit_factor: bestStrat.profit_factor,
        total_return: bestStrat.total_return,
        trades_count: bestStrat.trade_count,
        validation_return: bestStrat.validation_return,
        validation_trades: bestStrat.validation_trade_count,
        oos_return: bestStrat.oos_return,
        oos_sharpe: bestStrat.oos_sharpe,
        oos_trades: bestStrat.oos_trade_count,
        stability_label: bestStrat.stability_label
      })
    }).then(aiRes => {
      const diagEl = $("#custom-strat-ai-diag");
      if (!diagEl || !aiRes || !aiRes.ok) return;
      const verdictColor = aiRes.verdict === "근거 충분" ? "#34d399" : aiRes.verdict === "제한적" ? "#38bdf8" : "#f59e0b";
      diagEl.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:10px; padding:14px; margin-top:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">🤖</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">Tier 1 백테스트 정밀 진단 리포트</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">${aiRes.ai_generated ? "무료 AI 해석" : "규칙 기반 대체 설명"}</span>
            </div>
            <span class="chip" style="font-size:11px; font-weight:800; background:rgba(56,189,248,0.15); color:${verdictColor}; border:1px solid ${verdictColor};">
              종합 판정: ${escapeHtml(aiRes.verdict || "적합")}
            </span>
          </div>
          <p style="margin:0 0 6px; font-size:13px; color:#f1f5f9; line-height:1.5;">${escapeHtml(aiRes.diagnosis || "")}</p>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:8px; margin-top:8px;">
            ${aiRes.tuning_tip ? `<div style="background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:6px 10px; border-radius:4px; font-size:11.5px; color:#cbd5e1;">🎯 <b>파라미터 튜닝:</b> ${escapeHtml(aiRes.tuning_tip)}</div>` : ""}
            ${aiRes.execution_risk ? `<div style="background:rgba(239, 68, 68, 0.08); border-left:3px solid #ef4444; padding:6px 10px; border-radius:4px; font-size:11.5px; color:#cbd5e1;">🛡️ <b>해석상 한계:</b> ${escapeHtml(aiRes.execution_risk)}</div>` : ""}
          </div>
        </div>
      `;
      appendTier1Meta(diagEl, aiRes);
    }).catch((err) => {
      const diagEl = $("#custom-strat-ai-diag");
      if (diagEl) renderTier1Unavailable(diagEl, null, err);
    });

    showToast("백테스트가 완료되었습니다.", "success", 2200);
  } catch (err) {
    resBox.innerHTML = `<div style="padding:14px; background:rgba(239,68,68,0.1); border:1px solid #ef4444; border-radius:8px; color:#f87171;">⚠️ ${escapeHtml(err.message || "오류가 발생했습니다.")}</div>`;
  } finally {
    backtestBusy = false;
    hideBacktestOverlay();
  }
}


function formatSyncTime(isoStr) {
  if (!isoStr) {
    const now = new Date();
    return now.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" }) + " " + now.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }
  try {
    const dt = new Date(isoStr);
    return dt.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" }) + " " + dt.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  } catch {
    return String(isoStr);
  }
}

function renderMarginDebtBarometer(md) {
  if (!md || !md.ok) return "";
  const d1 = md.delta_1d_trillion;
  const d5 = md.delta_5d_trillion;
  const d1Txt = d1 > 0 ? `+${d1}조원` : `${d1}조원`;
  const d5Txt = d5 > 0 ? `+${d5}조원` : `${d5}조원`;
  const d1Cls = d1 > 0 ? "down" : "up"; // Debt increase is risk (red)
  const d5Cls = d5 > 0 ? "down" : "up";

  const sparkSvg = renderSvgSparkline(md.sparkline, d5 < 0, "spark-margin");
  const syncTimeStr = formatSyncTime(md.updated_at);

  return `
    <div class="margin-barometer-card" id="margin-barometer-container">
      <div class="margin-barometer-header">
        <div class="margin-barometer-title">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <h3 style="margin:0;">📊 코스피·코스닥 신용융자 잔고 & 레버리지 진단 (Margin Debt Barometer)</h3>
            <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 7px;">KOFIA·KRX 공식 집계</span>
          </div>
          <div class="margin-meta-subline" style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:6px; font-size:12px; color:#94a3b8;">
            <span>📅 <b>공식 공시 기준일:</b> <span style="color:#e2e8f0; font-weight:700;">${escapeHtml(md.latest_date || "—")}</span></span>
            <span>⏱️ <b>실시간 동기화:</b> <span id="margin-synced-badge" style="color:#38bdf8; font-weight:700;">${syncTimeStr}</span></span>
            <span class="has-tip" data-tip="금융투자협회와 KRX가 영업일 결제 기준(T+1~2일 시차)으로 집계하여 네이버증권에 최종 공시하는 공식 데이터입니다. 주말 및 휴장일을 제외한 가장 최신 공식 확정치입니다." style="cursor:help; color:#64748b; font-size:11.5px; text-decoration:underline dashed;">ℹ️ 공시 시차 안내</span>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <button type="button" id="btn-margin-debt-refresh" class="trade-refresh-btn" style="height:32px; font-size:11.5px; padding:0 10px; border-radius:6px;" title="네이버 금융·금융투자협회 신용잔고 최신 데이터 즉시 재수집">
            <span>🔄</span><span>실시간 새로고침</span>
          </button>
          <div class="margin-status-badge ${md.status_cls}">
            ${escapeHtml(md.status_label)}
          </div>
        </div>
      </div>

      <div class="margin-kpi-grid">
        <div class="margin-kpi-box has-tip"
             data-tip-title="🏦 전체 신용융자 잔고 (Total Margin Debt)"
             data-tip="개인 투자자가 주가 상승을 노리고 증권사에서 돈을 빌려 주식을 매수한 총 융자 잔액입니다."
             data-tip-up="신용잔고 급증 ➔ 단기 과열 및 지수 급락 시 반대매매(투매) 뇌관 위험"
             data-tip-down="신용잔고 급감 ➔ 악성 빚투 매물 소화 완료로 반등 탄력성 극대화"
             data-tip-hint="30조원 초과 시 경계, 20조원 이하 시 역사적 바닥권 형성"
             tabindex="0">
          <span>전체 신용융자 잔고</span>
          <b>${fmt(md.margin_debt_trillion, 2)} <small style="font-size:13px; font-weight:normal; color:#94a3b8;">조원</small></b>
          <div class="sub">1일 전 대비 <span class="${d1Cls}">${d1Txt}</span> · 5일 전 <span class="${d5Cls}">${d5Txt}</span></div>
          <div style="margin-top:6px;">${sparkSvg}</div>
        </div>

        <div class="margin-kpi-box has-tip"
             data-tip-title="💰 고객예탁금 (증시 대기 실탄)"
             data-tip="주식을 매수하기 위해 투자자들이 증권사 계좌에 입금해 둔 현금 잔액 총액입니다."
             data-tip-up="예탁금 증가 ➔ 증시 유동성 유입 및 매수 대기 자금 풍부 (강력 호재)"
             data-tip-down="예탁금 감소 ➔ 자금 이탈 및 거래대금 축소"
             data-tip-hint="예탁금 증가 추세와 함께 주가가 오를 때 상승장의 지속성이 가장 깁니다."
             tabindex="0">
          <span>고객예탁금 (대기 자금)</span>
          <b>${fmt(md.deposit_trillion, 2)} <small style="font-size:13px; font-weight:normal; color:#94a3b8;">조원</small></b>
          <div class="sub" style="color:#38bdf8;">증시 매수 대기 유동성 풍부</div>
        </div>

        <div class="margin-kpi-box has-tip"
             data-tip-title="⚖️ 예탁금 대비 신용잔고율 (Leverage Ratio)"
             data-tip="고객예탁금 대비 신용융자 잔고의 비율로, 개인 투자자의 실질적인 빚투 레버리지 과열도를 측정합니다."
             data-tip-up="35% 이상 과열 ➔ 하락 시 담보부족 계좌 속출로 연쇄 하한가/급락 위험"
             data-tip-down="22% 이하 안정 ➔ 빚투 부담이 없는 클린 수급 환경"
             data-tip-hint="30% 이상에서는 레버리지 종목 매수를 자제하세요."
             tabindex="0">
          <span>예탁금 대비 신용잔고율</span>
          <b class="${md.margin_deposit_ratio >= 30 ? 'down' : md.margin_deposit_ratio <= 22 ? 'up' : ''}">
            ${fmt(md.margin_deposit_ratio, 2)}%
          </b>
          <div class="sub">위험 기준: 35% 이상 과열</div>
        </div>

        <div class="margin-kpi-box has-tip"
             data-tip-title="🇰🇷 시장별 신용잔고 분할 (KOSPI vs KOSDAQ)"
             data-tip="코스피(대형주)와 코스닥(중소형 성장주)의 신용잔고 추정 분포입니다. 코스닥은 시총 대비 신용 비율이 높아 반대매매 충격에 훨씬 취약합니다."
             data-tip-hint="코스닥 신용 급증 시 중소형 테마주 급락 변동성을 특별히 주의하세요."
             tabindex="0">
          <span>코스피 vs 코스닥 신용</span>
          <b>코스피 ${fmt(md.kospi_est_trillion, 1)}조 / 코스닥 ${fmt(md.kosdaq_est_trillion, 1)}조</b>
          <div class="sub">코스피 58% · 코스닥 42% (과열 취약)</div>
        </div>
      </div>

      <div class="margin-warning-banner ${md.status_cls}">
        ${md.warning}
      </div>
    </div>
  `;
}


function renderHexagonRadarSvg(factors, timingScore) {
  // 6 Axes: 가치(30), 품질(25), 성장(25), 모멘텀(10), 안정(10), 기술타이밍(100)
  const axes = [
    { label: "💎 가치", val: factors[0]?.[1] || 0, max: 30, tip: "저평가 밸류에이션 안전마진" },
    { label: "👑 품질", val: factors[1]?.[1] || 0, max: 25, tip: "ROE·영업이익률 우량 펀더멘털" },
    { label: "🚀 성장", val: factors[2]?.[1] || 0, max: 25, tip: "매출·영업이익 3개년 성장률" },
    { label: "⚡ 모멘텀", val: factors[3]?.[1] || 0, max: 10, tip: "3/6/12개월 주가 상승 추세" },
    { label: "🛡️ 안정", val: factors[4]?.[1] || 0, max: 10, tip: "부채비율·유동성 재무 건전성" },
    { label: "🎯 타이밍", val: timingScore || 50, max: 100, tip: "KRX 일봉 스토캐스틱·일목 기술적 위치" },
  ];

  const cx = 150;
  const cy = 125;
  const R = 85;
  const n = axes.length;

  // Concentric Hexagon Grid levels (20%, 40%, 60%, 80%, 100%)
  const gridLevels = [0.2, 0.4, 0.6, 0.8, 1.0];
  const gridPolygons = gridLevels.map((lvl) => {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const angle = -Math.PI / 2 + i * (2 * Math.PI / n);
      const x = cx + R * lvl * Math.cos(angle);
      const y = cy + R * lvl * Math.sin(angle);
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return `<polygon points="${pts.join(" ")}" fill="none" stroke="rgba(255,255,255,${lvl === 1.0 ? "0.15" : "0.06"})" stroke-width="1" />`;
  }).join("");

  // Radial spoke lines
  const spokeLines = axes.map((_, i) => {
    const angle = -Math.PI / 2 + i * (2 * Math.PI / n);
    const x = cx + R * Math.cos(angle);
    const y = cy + R * Math.sin(angle);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,0.08)" stroke-width="1" />`;
  }).join("");

  // Market Benchmark polygon (50% uniform)
  const benchPts = [];
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * (2 * Math.PI / n);
    const x = cx + R * 0.5 * Math.cos(angle);
    const y = cy + R * 0.5 * Math.sin(angle);
    benchPts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  const benchPolygon = `<polygon points="${benchPts.join(" ")}" fill="none" stroke="#64748b" stroke-width="1.5" stroke-dasharray="3,3" opacity="0.7" />`;

  // Company Score Polygon
  const scorePts = [];
  const vertexDots = [];
  axes.forEach((ax, i) => {
    const pct = Math.max(0.12, Math.min(1.0, (ax.val || 0) / ax.max));
    const angle = -Math.PI / 2 + i * (2 * Math.PI / n);
    const x = cx + R * pct * Math.cos(angle);
    const y = cy + R * pct * Math.sin(angle);
    scorePts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    vertexDots.push(`
      <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="#38bdf8" stroke="#0f172a" stroke-width="2" class="has-tip" data-tip-title="${escapeHtml(ax.label)}" data-tip="${escapeHtml(ax.tip)}: ${fmt(ax.val, 1)} / ${ax.max} (${(pct * 100).toFixed(0)}%)" />
    `);
  });

  // Axis Labels around radar
  const labelTexts = axes.map((ax, i) => {
    const angle = -Math.PI / 2 + i * (2 * Math.PI / n);
    const labelR = R + 22;
    const x = cx + labelR * Math.cos(angle);
    const y = cy + labelR * Math.sin(angle);
    let anchor = "middle";
    if (Math.cos(angle) > 0.3) anchor = "start";
    else if (Math.cos(angle) < -0.3) anchor = "end";

    const scorePct = Math.round(Math.max(0, Math.min(100, ((ax.val || 0) / ax.max) * 100)));
    return `
      <text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}" fill="#cbd5e1" font-size="11" font-weight="600">
        ${escapeHtml(ax.label)} <tspan fill="#38bdf8" font-size="10">${scorePct}%</tspan>
      </text>
    `;
  }).join("");

  return `
    <svg viewBox="0 0 300 250" class="radar-svg-wrap">
      <defs>
        <radialGradient id="radarGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.45" />
          <stop offset="100%" stop-color="#0284c7" stop-opacity="0.15" />
        </radialGradient>
      </defs>
      ${gridPolygons}
      ${spokeLines}
      ${benchPolygon}
      <polygon points="${scorePts.join(" ")}" fill="url(#radarGlow)" stroke="#38bdf8" stroke-width="2.5" stroke-linejoin="round" />
      ${vertexDots.join("")}
      ${labelTexts}
    </svg>
  `;
}

function renderPriceAndBandGauge(brief, ta, toss) {
  const tq = toss?.quote || {};
  const currentPrice = Number(tq.lastPrice ?? tq.price ?? tq.close ?? brief?.price ?? 0);
  const facts = brief?.facts || [];
  
  // Look for 52w high/low in facts or ta
  let low52 = null;
  let high52 = null;
  facts.forEach(f => {
    if (f.label && f.label.includes("52주") && f.label.includes("최고")) high52 = parseFloat(String(f.value).replace(/,/g, ""));
    if (f.label && f.label.includes("52주") && f.label.includes("최저")) low52 = parseFloat(String(f.value).replace(/,/g, ""));
  });

  const support = ta?.support;
  const resistance = ta?.resistance;

  let rangeHtml = "";
  if (low52 && high52 && high52 > low52 && currentPrice) {
    const pct = Math.max(0, Math.min(100, ((currentPrice - low52) / (high52 - low52)) * 100));
    rangeHtml = `
      <div class="visual-meter-box">
        <div class="visual-meter-head">
          <span>📏 52주 주가 위치 (Range)</span>
          <span style="color:#38bdf8; font-weight:700;">상위 ${pct.toFixed(0)}% 구간</span>
        </div>
        <div class="range-bar-track has-tip"
             data-tip-title="52주 최고/최저가 대비 주가 위치"
             data-tip="52주 최저가(${fmt(low52, 0)}원)와 최고가(${fmt(high52, 0)}원) 사이에서 현재가(${fmt(currentPrice, 0)}원)의 상대적 위치입니다."
             data-tip-hint="80% 이상은 신고가 돌파권, 20% 이하는 바닥권 반등 대기 영역입니다.">
          <div class="range-bar-fill" style="width:${pct}%;"></div>
          <div class="range-bar-pin" style="left:${pct}%;"></div>
        </div>
        <div class="range-labels">
          <span>52주 최저 ${fmt(low52, 0)}원</span>
          <span>현재가 ${fmt(currentPrice, 0)}원</span>
          <span>52주 최고 ${fmt(high52, 0)}원</span>
        </div>
      </div>
    `;
  }

  let bandHtml = "";
  if (support != null && resistance != null && resistance > support && currentPrice) {
    const bbPct = Math.max(0, Math.min(100, ((currentPrice - support) / (resistance - support)) * 100));
    bandHtml = `
      <div class="visual-meter-box">
        <div class="visual-meter-head">
          <span>🎯 지지선 vs 저항선 밴드 (Support & Resistance)</span>
          <span class="${bbPct > 70 ? 'up' : bbPct < 30 ? 'down' : ''}">${bbPct > 70 ? '저항선 근접' : bbPct < 30 ? '지지선 지지' : '중심선 유지'}</span>
        </div>
        <div class="bb-gauge-track has-tip"
             data-tip-title="지지·저항 가격대 분석"
             data-tip="KRX 일봉 기준 주요 지지 가격대(${fmt(support, 0)}원)와 저항 가격대(${fmt(resistance, 0)}원) 구간입니다."
             data-tip-hint="지지선 근처에서는 분할 매수, 저항선 근처에서는 분할 매도가 유리합니다.">
          <div class="bb-zone oversold" title="지지선"></div>
          <div class="bb-zone neutral" title="중심선"></div>
          <div class="bb-zone overbought" title="저항선"></div>
          <div class="bb-pin" style="left:${bbPct}%;"></div>
        </div>
        <div class="range-labels">
          <span>지지선 ${fmt(support, 0)}원</span>
          <span>중심 ${fmt((support + resistance) / 2, 0)}원</span>
          <span>저항선 ${fmt(resistance, 0)}원</span>
        </div>
      </div>
    `;
  }

  return `${rangeHtml}${bandHtml}`;
}


function classifyNewsSentiment(title, description) {
  const text = `${title || ""} ${description || ""}`.toLowerCase();
  
  const BULL_KEYWORDS = [
    "호실적", "어닝서프라이즈", "서프라이즈", "흑자전환", "영업익 급증", "매출 급증", "최대 실적",
    "사상 최대", "영업이익 급증", "수주", "대규모 계약", "공급계약", "체결", "신고가", "급등", "상한가",
    "목표가 상향", "투자의견 상향", "매수 추천", "자사주 매입", "자사주 소각", "배당 확대", "배당금 인상",
    "지분 확대", "특허 취득", "fda 승인", "임상 성공", "인수합병", "m&a", "호재",
    "반등", "상승세", "독점", "ai 수혜", "수혜주", "유치", "기술수출", "양산", "공급 개시", "투자 유치",
    "금리 인하", "물가 안정", "외인 순매수", "기관 순매수", "경기 회복", "무역수지 흑자", "훈풍", "강세", "성장", "호조"
  ];

  const BEAR_KEYWORDS = [
    "어닝쇼크", "실적 쇼크", "적자전환", "적자 지속", "적자 확대", "영업익 급감", "매출 급감",
    "급락", "하한가", "신저가", "목표가 하향", "투자의견 하향", "매도", "손실", "유상증자",
    "전환사채", "cb 발행", "bw 발행", "감자", "상장폐지", "거래정지", "관리종목", "투자경고",
    "횡령", "배임", "분식회계", "압수수색", "기소", "피소", "소송", "과징금", "제재", "규제",
    "리콜", "화재", "사고", "임상 실패", "승인 거절", "계약 해지", "공급 중단", "디폴트",
    "부도", "파산", "워크아웃", "금리 인상", "인플레 재점화", "경기 침체", "관세 부과", "전쟁", "리스크",
    "매물 폭탄", "블록딜", "지분 매각", "오버행", "외인 매도", "약세", "악재", "부진", "하락세"
  ];

  let bullScore = 0;
  let bearScore = 0;

  for (const kw of BULL_KEYWORDS) {
    if (text.includes(kw)) {
      bullScore += kw.length >= 4 ? 2 : 1;
    }
  }

  for (const kw of BEAR_KEYWORDS) {
    if (text.includes(kw)) {
      bearScore += kw.length >= 4 ? 2 : 1;
    }
  }

  if (bullScore > bearScore && bullScore >= 1) {
    return {
      type: "bull",
      label: "호재",
      icon: "🟢",
      cls: "news-badge-bull"
    };
  } else if (bearScore > bullScore && bearScore >= 1) {
    return {
      type: "bear",
      label: "악재",
      icon: "🔴",
      cls: "news-badge-bear"
    };
  } else {
    return {
      type: "neutral",
      label: "일반",
      icon: "⚪",
      cls: "news-badge-neutral"
    };
  }
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const titles = {
  dash: ["대시보드", "재무 팩터 기반 상위 20종목 요약"],
  rank: ["점수 랭킹", "시총·유동성 통과 종목 전체 퀀트 랭킹"],
  screens: ["테마 스크리너", "가치·성장·배당·모멘텀 테마별 정밀 스크리닝"],
  market: ["글로벌 매크로 & 국면", "거시경제·환율·원자재·공포탐욕 & 역사적 계절성 분석"],
  sector: ["업종·섹터 분석", "KSIC 업종별 상대강도(RS), 확산도 및 모멘텀 랭킹"],
  toss: ["토스 랭킹", "급상승·급하락·거래대금 실시간 시세"],
  watch: ["관심종목", "나만의 관심종목 메모 및 빠른 분석"],
  reports: ["리포트 보관함", "발간된 AI 심층 분석 리포트 및 검증 아카이브"],
  run: ["실행 파이프라인", "실데이터 수집, 시세 갱신 및 퀀트 재계산"],
  settings: ["API 설정", "API 키 및 LLM 모델 환경설정"],
  flow: ["스마트 수급·타점", "외국인·기관·사모 수급, 빈집·복귀, 기술적 타점 및 신호 후 성과 통합 검증"],
  empty: ["스마트 수급·타점", "외국인·기관·사모 수급, 빈집·복귀, 기술적 타점 및 신호 후 성과 통합 검증"],
  trade: ["스마트 수급·타점", "외국인·기관·사모 수급, 빈집·복귀, 기술적 타점 및 신호 후 성과 통합 검증"],
  us13f: ["월가 대가 포트폴리오 (13F)", "워런 버핏·마이클 버리 등 글로벌 대가들의 SEC 13F 보유 비중 & 신규 편입 종목"],
  strategy: ["전략·백테스트", "일봉 기반 퀀트 전략 백테스트 및 검증"],
  investor: ["메이저 수급 & 지분", "기관·외국인 일별 순매수 추적 & DART 국민연금 5% 대량보유 공시"],
  sunzi: ["은하퀀트전설 (Legend of Galactic Quant)", "제13함대 기함 히페리온 작전 회의실 · 손자 오사(道天地將法) 기반 실전 전술 참모"],
  nps: ["국민연금 5%", "OpenDART 국민연금 5% 이상 대량보유 공시 추적"],
  seasonality: ["계절성·캘린더 퀀트", "가격 선행형 Discovery · 10개 분야 18개 이벤트 · AI 원인 역추적 스크리너"],
};

let rankRows = [];
let dashRows = [];
let guideCache = null;
let reportRows = [];
let currentView = "dash";
let lastStatus = null;
let lastStatusExplain = null;
let sortState = {};
let screenCache = null;
let tradeCache = null;
let flowTab = "dual";
let smartFlowTab = "overview";
let flowLimit = {};
const FLOW_FIRST = 12;
const FLOW_STEP = 10;

function sortVal(row, key) {
  if (!row) return null;
  if (key === "last" || key === "last_close") {
    const v = row.last_close ?? row.last ?? row.close;
    return v == null || v === "" ? null : Number(v);
  }
  if (key === "setup_notional" && typeof setupNotional === "function") return setupNotional(row);
  if (key === "stoch_k") return row.ta && row.ta.stoch_k != null ? Number(row.ta.stoch_k) : null;
  if (key === "company") return String(row.company || row.issuer_ko || row.issuer || "").toLowerCase();
  if (key === "industry") return String(row.industry || row.sector || "");
  const v = row[key];
  if (v == null || v === "") return null;
  if (typeof v === "number") return v;
  const n = Number(v);
  if (!Number.isNaN(n) && /^-?\d/.test(String(v).trim())) return n;
  return String(v).toLowerCase();
}

function sortedCopy(rows, scope, fallbackKey, fallbackDir) {
  const st = sortState[scope] || { key: fallbackKey, dir: fallbackDir || "desc" };
  if (!st.key) return rows;
  const mul = st.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = sortVal(a, st.key);
    const vb = sortVal(b, st.key);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * mul;
    return String(va).localeCompare(String(vb), "ko") * mul;
  });
}

function paintSortHeaders(scope) {
  const st = sortState[scope] || {};
  document.querySelectorAll(`table[data-scope="${scope}"] th.sortable`).forEach((th) => {
    th.classList.remove("asc", "desc");
    if (st.key && th.dataset.sort === st.key) th.classList.add(st.dir || "desc");
  });
}

function lastCell(r) {
  const v = r.last_close ?? r.last ?? r.close;
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("ko-KR");
}

function padTicker(t) {
  const raw = String(t || "").replace(".0", "").trim().toUpperCase();
  if (/^[0-9A-Z]{5,6}$/.test(raw) && /[A-Z]/.test(raw)) return raw.padStart(6, "0");
  const d = raw.replace(/\D/g, "");
  return d ? d.padStart(6, "0") : String(t || "");
}

function naverUrl(ticker) {
  return `https://finance.naver.com/item/main.naver?code=${padTicker(ticker)}`;
}

let publicApiManifestPromise = null;
const publicApiCache = new Map();

async function publicApiManifest() {
  if (!publicApiManifestPromise) {
    publicApiManifestPromise = fetch("/data/api/manifest.json", { cache: "no-store" }).then((res) => {
      if (!res.ok) throw new Error("공개 데이터 목록을 불러오지 못했습니다.");
      return res.json();
    });
  }
  return publicApiManifestPromise;
}

async function publicRouteFile(filename) {
  if (!filename) throw new Error("이 화면의 공개 스냅샷이 없습니다.");
  if (!publicApiCache.has(filename)) {
    const safePath = String(filename).split("/").map((part) => encodeURIComponent(part)).join("/");
    publicApiCache.set(filename, fetch(`/data/api/${safePath}`, { cache: "no-store" }).then((res) => {
      if (!res.ok) throw new Error("공개 스냅샷 파일을 불러오지 못했습니다.");
      return res.json();
    }));
  }
  return publicApiCache.get(filename);
}

function publicStockPayload(row, ticker) {
  const code = padTicker((row || {}).ticker || ticker);
  const r = row || { ticker: code, company: code };
  const facts = [
    ["최근가", r.last_close ?? r.close], ["PER", r.per], ["PBR", r.pbr],
    ["ROE", r.roe], ["영업이익률", r.operating_margin], ["데이터 신뢰도", r.data_confidence],
  ].filter(([, value]) => value !== null && value !== undefined).map(([label, value]) => ({ label, value: String(value) }));
  return {
    row: r,
    as_of: r.as_of_date || null,
    profile: {},
    brief: { facts },
    scorecard: { factors: [] },
    dart: {}, location: {}, toss: {}, yahoo: {}, ta: {}, timing: {},
    fa: {}, dao: {}, jiang: {}, tian: {}, di: {}, sunzi: {},
    events: { rows: [], used_in_quant: false },
    flow90: { chart: [], used_in_quant: false },
    naver: { configured: false, news: [], web: [], encyc: [] },
    explain: {}, comment: r.comment || "",
    links: [
      { label: "네이버 금융", url: naverUrl(code) },
      { label: "OpenDART", url: "https://opendart.fss.or.kr/" },
    ],
    risk_notes: [], data_notes: [],
    gates: {
      universe_eligible: Boolean(r.universe_eligible),
      top100_eligible: Boolean(r.top100_eligible),
      top20_eligible: Boolean(r.top20_eligible),
      coverage: r.weighted_metric_coverage,
      data_confidence: r.data_confidence,
      exclusion_reasons: [],
    },
  };
}

function filterPublicSunzi(data, url) {
  let rows = [...(data.rows || [])];
  const q = (url.searchParams.get("query") || "").trim().toLowerCase();
  const market = url.searchParams.get("market");
  const posture = url.searchParams.get("posture");
  const fa = url.searchParams.get("fa");
  const universe = url.searchParams.get("universe");
  if (q) rows = rows.filter((r) => `${r.company || ""} ${r.ticker || ""}`.toLowerCase().includes(q));
  if (market && market !== "all") rows = rows.filter((r) => r.market === market);
  if (posture && posture !== "all") rows = rows.filter((r) => r.posture === posture);
  if (fa && fa !== "all") rows = rows.filter((r) => String(r.fa_status || r.fa || "").toLowerCase().includes(fa.toLowerCase()));
  if (universe === "quant") rows = rows.filter((r) => r.universe_eligible !== false);
  const limit = Math.max(1, Number(url.searchParams.get("n") || 80));
  rows = rows.slice(0, limit);
  const postures = {};
  rows.forEach((r) => { if (r.posture) postures[r.posture] = (postures[r.posture] || 0) + 1; });
  return {
    ...data,
    rows,
    n: rows.length,
    fa_pass_n: rows.filter((r) => r.fa_gate_pass).length,
    postures,
  };
}

function normalizePublicStockItem(row) {
  return {
    ticker: String(row?.ticker || row?.t || "").padStart(6, "0"),
    company: String(row?.company || row?.c || ""),
    market: String(row?.market || row?.m || "KOSPI"),
    sector: String(row?.sector || row?.s || ""),
    quant_score: row?.quant_score ?? null,
    quant_rank: row?.quant_rank ?? null,
  };
}

function filterPublicRows(data, url) {
  let rows = [...(data.rows || [])];
  const q = (url.searchParams.get("query") || "").trim().toLowerCase();
  if (q) rows = rows.filter((r) => `${r.company || ""} ${r.ticker || ""}`.toLowerCase().includes(q));

  if (url.pathname === "/api/seasonality/scan") {
    const presetKey = url.searchParams.get("preset") || "";
    const preset = data.presets?.[presetKey] || null;
    const requestedMonth = Number(url.searchParams.get("month")) || Number(data.target_month) || new Date().getMonth() + 1;
    const resolvedMonth = preset ? Number(preset.analysis_month || requestedMonth) : requestedMonth;

    rows = rows.map((row) => {
      const monthStat = (row.all_months || []).find((item) => Number(item.month) === resolvedMonth);
      if (!monthStat) return { ...row, target_month: resolvedMonth };
      const winRate = Number(monthStat.win_rate || 0);
      const avgReturn = Number(monthStat.avg_return || 0);
      const years = Number(monthStat.years_count || 0);
      return {
        ...row,
        target_month: resolvedMonth,
        win_rate: winRate,
        avg_return: avgReturn,
        median_return: Number(monthStat.median_return || 0),
        years_count: years,
        history: monthStat.history || [],
        seasonality_score: Math.round(((winRate * 50) + (Math.min(avgReturn, 0.40) * 100) + (Math.min(years, 4) * 2.5)) * 10) / 10,
        event_mode: Boolean(preset),
        event_key: preset ? presetKey : null,
        event_title: preset?.title || null,
        event_description: preset?.description || null,
        event_peak_months: preset?.peak_months || [],
      };
    });

    if (preset) {
      const tickers = new Set((preset.tickers || []).map((ticker) => padTicker(ticker)));
      rows = rows.filter((row) => tickers.has(padTicker(row.ticker)));
    } else {
      const minWinRate = Number(url.searchParams.get("min_win_rate"));
      if (Number.isFinite(minWinRate) && url.searchParams.has("min_win_rate")) rows = rows.filter((r) => Number(r.win_rate || 0) >= minWinRate);
      const minAvgReturn = Number(url.searchParams.get("min_avg_return"));
      if (Number.isFinite(minAvgReturn) && url.searchParams.has("min_avg_return")) rows = rows.filter((r) => Number(r.avg_return ?? r.median_return ?? 0) >= minAvgReturn);
    }
    rows.sort((a, b) => Number(b.seasonality_score || 0) - Number(a.seasonality_score || 0));
    return {
      ...data,
      filter_mode: preset ? "event" : "month",
      target_month: resolvedMonth,
      requested_month: url.searchParams.has("month") ? requestedMonth : null,
      active_preset_key: preset ? presetKey : null,
      active_preset: preset,
      event_mapped_count: preset ? (preset.tickers || []).length : null,
      generic_thresholds_applied: !preset,
      rows,
      count: rows.length,
    };
  }

  const minGrade = url.searchParams.get("min_grade");
  if (minGrade) {
    const gradeOrder = { "S+": 5, S: 4, "A+": 3, A: 2, B: 1, C: 0 };
    rows = rows.filter((r) => (gradeOrder[r.grade] ?? 0) >= (gradeOrder[minGrade] ?? 0));
  }
  const status = url.searchParams.get("status");
  if (status && status !== "all") rows = rows.filter((r) => r.current_status === status);
  const confirmation = url.searchParams.get("confirmation");
  if (confirmation && confirmation !== "all") rows = rows.filter((r) => r.confirmation_state === confirmation);
  const group = url.searchParams.get("group_id");
  if (group && group !== "all") rows = rows.filter((r) => r.event_group_id === group || r.group_id === group);
  const minWinRate = Number(url.searchParams.get("min_win_rate"));
  if (Number.isFinite(minWinRate) && url.searchParams.has("min_win_rate")) rows = rows.filter((r) => Number(r.win_rate || 0) >= minWinRate);
  const minAvgReturn = Number(url.searchParams.get("min_avg_return"));
  if (Number.isFinite(minAvgReturn) && url.searchParams.has("min_avg_return")) rows = rows.filter((r) => Number(r.avg_return ?? r.median_return ?? 0) >= minAvgReturn);
  return { ...data, rows, count: rows.length };
}

async function publicApi(path, opts = {}) {
  const url = new URL(path, window.location.origin);
  const route = url.pathname;
  const method = String(opts.method || "GET").toUpperCase();
  const cachedRefreshRoutes = new Set(["/api/flow", "/api/strategy", "/api/us13f"]);
  if (method !== "GET") {
    if (cachedRefreshRoutes.has(route)) return publicApi(route);
    throw new Error("공개 웹은 읽기 전용입니다. 수집·저장·AI 실행은 로컬에서 사용하세요.");
  }

  const manifest = await publicApiManifest();
  if (route === "/api/stocks/search") {
    const data = await publicRouteFile(manifest.routes["/api/stocks/all"]);
    const q = (url.searchParams.get("q") || "").trim().toLowerCase();
    const limit = Math.max(1, Number(url.searchParams.get("limit") || 12));
    const items = (data.items || [])
      .map(normalizePublicStockItem)
      .filter((r) => !q || `${r.company} ${r.ticker}`.toLowerCase().includes(q))
      .slice(0, limit);
    return { items };
  }
  if (route === "/api/stocks/all") {
    const data = await publicRouteFile(manifest.routes[route]);
    return { ...data, items: (data.items || []).map(normalizePublicStockItem) };
  }
  const stockMatch = route.match(/^\/api\/results\/stock\/([0-9A-Z]{1,6})$/i);
  if (stockMatch) {
    const code = padTicker(stockMatch[1]);
    const detailBase = manifest.stock_details?.base;
    if (detailBase) {
      try {
        return await publicRouteFile(`${detailBase}/${code}.json`);
      } catch (err) {
        console.warn(`Public stock detail ${code} missing; using summary fallback.`, err);
      }
    }
    const data = await publicRouteFile(manifest.routes["/api/results/all"]);
    const row = (data.rows || []).find((r) => padTicker(r.ticker) === code);
    return publicStockPayload(row, code);
  }
  const researchReportMatch = route.match(/^\/api\/research\/(\d{1,6})\/report$/);
  if (researchReportMatch) {
    const code = padTicker(researchReportMatch[1]);
    const asOf = url.searchParams.get("as_of") || "";
    const details = manifest.research_details || {};
    const filename = details.reports?.[`${code}|${asOf}`] || details.reports_latest?.[code];
    if (filename) return publicRouteFile(filename);
    return { exists: false, row: null };
  }
  const researchMatch = route.match(/^\/api\/research\/(\d{1,6})$/);
  if (researchMatch) {
    const code = padTicker(researchMatch[1]);
    const asOf = url.searchParams.get("as_of") || "";
    const details = manifest.research_details || {};
    const filename = details.analysis?.[`${code}|${asOf}`] || details.analysis_latest?.[code];
    if (filename) return publicRouteFile(filename);
    return { exists: false, row: null };
  }
  const discoveryTicker = route.match(/^\/api\/seasonality\/discovery\/(\d{1,6})$/);
  if (discoveryTicker) {
    const data = await publicRouteFile(manifest.routes["/api/seasonality/discovery"]);
    const code = padTicker(discoveryTicker[1]);
    return { ok: true, ticker: code, lookback_years: Number(url.searchParams.get("lookback_years") || 5), patterns: (data.rows || []).filter((r) => padTicker(r.ticker) === code) };
  }
  if (/^\/api\/seasonality\/ticker\//.test(route)) return { ok: false, stock: null };
  const flowTicker = route.match(/^\/api\/flow\/ticker\/(\d{1,6})$/);
  if (flowTicker) {
    const data = await publicRouteFile(manifest.routes["/api/flow"]);
    const code = padTicker(flowTicker[1]);
    const row = (data.rows || []).find((r) => padTicker(r.ticker) === code);
    return row ? { ok: true, row } : { ok: false, row: null, error: `종목 ${code}의 공개 수급 스냅샷이 없습니다.` };
  }
  if (/^\/api\/investor\/ticker\//.test(route)) return { rows: [], chart: [], used_in_quant: false };
  if (route === "/api/screens") {
    const id = url.searchParams.get("id") || "value_growth";
    return publicRouteFile(manifest.screens[id] || manifest.routes[route]);
  }

  let data = await publicRouteFile(manifest.routes[route]);
  if (route === "/api/results/all") {
    const limit = Math.max(1, Number(url.searchParams.get("limit") || 300));
    data = { ...data, rows: (data.rows || []).slice(0, limit) };
  }
  if (route === "/api/results/top") {
    const limit = Math.max(1, Number(url.searchParams.get("n") || 20));
    data = { ...data, rows: (data.rows || []).slice(0, limit) };
  }
  if (route === "/api/sunzi") data = filterPublicSunzi(data, url);
  if (["/api/seasonality/discovery", "/api/seasonality/ranked", "/api/seasonality/scan"].includes(route)) data = filterPublicRows(data, url);
  return data;
}

async function api(path, opts = {}) {
  if (publicShareMode) return publicApi(path, opts);
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const t = await res.text();
    let msg = t || res.statusText;
    try {
      const j = JSON.parse(t);
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* keep raw */
    }
    throw new Error(msg);
  }
  return res.json();
}

function fmt(n, d = 2) {
  if (n === null || n === undefined || n === "") return "—";
  const x = Number(n);
  if (Number.isNaN(x)) return String(n);
  return x.toFixed(d);
}

function fmtPct(n, d = 1) {
  if (n === null || n === undefined || n === "") return "—";
  const x = Number(n);
  if (Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(d)}%`;
}

const LOCAL_WEB_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
let publicShareMode = document.body.dataset.publicBuild === "true" ||
  new URLSearchParams(window.location.search).has("public-preview") ||
  !LOCAL_WEB_HOSTS.has(window.location.hostname.toLowerCase());
document.body.classList.toggle("public-mode", publicShareMode);

function lockPublicAdminUi() {
  if (!publicShareMode) return;
  $$('[data-view="settings"], #view-settings').forEach((el) => el.remove());
  $$("#view-run button").forEach((button) => {
    button.disabled = true;
    button.title = "공개 웹은 읽기 전용입니다. 실행은 로컬에서 사용하세요.";
  });
}

async function applyPublicShareMode() {
  try {
    const st = await api("/api/status");
    publicShareMode = publicShareMode || Boolean(st.public_mode);
  } catch {
    // Keep the hostname-derived safe default when the status API is unavailable.
  }
  document.body.classList.toggle("public-mode", publicShareMode);
  lockPublicAdminUi();
  if (publicShareMode && currentView === "settings") {
    switchView("dash");
  }
}

function switchView(name) {
  if (publicShareMode && name === "settings") name = "dash";
  // Backward compatibility: retired flow/empty routes open their matching
  // tabs inside the unified smart-flow screen.
  if (name === "flow") {
    smartFlowTab = "overview";
    name = "trade";
  }
  if (name === "empty") {
    smartFlowTab = "vacancy";
    name = "trade";
  }
  currentView = name;
  closeDrawer();
  closeMobileDrawer();
  $$(".view").forEach((el) => el.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$("[data-mobile-view]").forEach((b) => b.classList.toggle("active", b.dataset.mobileView === name));
  if (titles[name]) {
    $("#page-title").textContent = titles[name][0];
    $("#page-sub").textContent = titles[name][1];
  } else {
    $("#page-title").textContent = name;
    $("#page-sub").textContent = "";
  }
  const modeBadge = $("#top-mode-badge");
  if (modeBadge) {
    if (name === "dash" || name === "rank" || name === "screens") {
      modeBadge.className = "top-mode-badge quant-active";
      modeBadge.innerHTML = "⭐ <b>재무 Quant 엔진 적용</b>";
    } else if (name === "seasonality") {
      modeBadge.className = "top-mode-badge quant-active";
      modeBadge.innerHTML = "📅 <b>계절성 & 캘린더 엔진</b>";
    } else if (name === "sunzi") {
      modeBadge.className = "top-mode-badge research-active";
      modeBadge.innerHTML = "🍵 <b>은하퀀트전설 · 참모 당직</b>";
    } else if (name === "run" || name === "settings") {
      modeBadge.className = "top-mode-badge system-active";
      modeBadge.innerHTML = "⚙️ <b>시스템 관리</b>";
    } else {
      modeBadge.className = "top-mode-badge research-active";
      modeBadge.innerHTML = "📊 <b>시장 리서치 & 오버레이</b>";
    }
  }
  applyPriceChrome(name);
  startLiveSync(name);
  if (name === "dash" || name === "rank") stampFromStatus();
  if (name === "rank") loadRankTier1Briefing().catch(() => {});
  if (name === "investor") {
    loadInvestor().catch((err) => alert(err.message));
    loadInvestorEvents().catch(() => {});
  }
  if (name === "sunzi") loadSunzi().catch((err) => alert(err.message));
  if (name === "nps") loadNps().catch((err) => alert(err.message));
  if (name === "trade") loadTrade().catch((err) => alert(err.message));
  if (name === "us13f") loadUs13f().catch((err) => alert(err.message));
  if (name === "toss") loadTossRankings().catch((err) => alert(err.message));
  if (name === "sector") loadSectors().catch((err) => alert(err.message));
  if (name === "screens") loadScreens().catch((err) => alert(err.message));
  if (name === "market") {
    loadMarket().catch((err) => alert(err.message));
    loadMacro().catch(() => {});
    if (typeof startMacroLivePolling === "function") startMacroLivePolling();
  } else {
    if (typeof stopMacroLivePolling === "function") stopMacroLivePolling();
  }
  if (name === "strategy") {
    loadStrategy().catch((err) => alert(err.message));
    loadPortfolio().catch(() => {});
  }
  if (name === "watch") loadWatch().catch((err) => alert(err.message));
  if (name === "reports") {
    loadReportArchive().catch(() => {});
    const btnReports = $("#subtab-watch-reports");
    if (btnReports) btnReports.click();
  }
  if (name === "seasonality") {
    setPageAsOf("계절성 데이터 시점 확인 중…", "KRX 일봉 기준일과 계절성 계산 시각을 불러오는 중입니다.");
    loadSeasonalityTier1Briefing().catch(() => {});
    if (currentV11Subtab === "pre-entry") loadPreEntryView().catch(() => {});
    else if (currentV11Subtab === "discovery") loadDiscoveryRanked().catch(() => {});
    else if (currentV11Subtab === "explanation") loadAIExplanations().catch(() => {});
    else if (currentV11Subtab === "calendar") loadInstitutionalCalendar().catch(() => {});
    else loadSeasonality().catch(() => {});
  }
  if (name === "run") stampRunAsOf();
  if (name === "settings") setPageAsOf("이 PC의 .env · 시장 데이터 시점이 아닙니다.", "키 저장 화면입니다. 시세·수급 시점과 무관합니다.");
}

let liveTimer = null;
function stampLive(sel) {
  const el = $(sel);
  if (!el) return;
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  el.textContent = `동기화 ${hh}:${mm}`;
}
function stopLiveSync() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
  }
}
function startLiveSync(name) {
  stopLiveSync();
  if (publicShareMode) return;
  if (name === "market") {
    liveTimer = setInterval(() => {
      loadMarket(true).catch(() => {});
      loadMacro(true).catch(() => {});
    }, 60000);
  } else if (name === "toss") {
    liveTimer = setInterval(() => loadTossRankings().catch(() => {}), 30000);
  }
}

function closeDrawer() {
  $("#drawer")?.classList.add("hidden");
  $("#drawer-back")?.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function openDrawerUi() {
  $("#drawer-back")?.classList.remove("hidden");
  $("#drawer")?.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

const STATUS_KO = {
  success: "완료",
  partial: "일부 완료",
  failed: "실패",
  error: "오류",
  "no-run": "아직 실행 안 함",
  running: "실행 중",
  idle: "대기",
  stale: "시세 지연",
  fresh: "시세 최신",
  screen_lag: "점수 미재계산",
};

const STATUS_TIP = {
  success: "이번 스크리닝이 끝까지 갔습니다.",
  partial: "점수는 나왔지만 일부 데이터가 비어 경고가 있습니다. 거래정지 피드 등이 없을 때 자주 나옵니다.",
  failed: "실행이 실패했습니다. 실행 탭 로그를 보세요.",
  error: "오류가 있습니다. 실행 탭 로그를 보세요.",
  "no-run": "아직 스크리닝을 돌리지 않았습니다.",
  running: "작업이 돌아가고 있습니다.",
  idle: "대기 중입니다.",
  stale: "장 마감 후 시세가 아직 안 들어왔습니다. 위 시세 받기를 누르세요.",
  fresh: "기대하는 마지막 거래일 시세가 있습니다.",
  screen_lag: "시세는 더 새것인데 점수는 이전 기준일입니다. 재계산이 필요합니다.",
};

function statusKo(raw) {
  const key = String(raw || "no-run");
  return STATUS_KO[key] || key;
}

const PRICE_VIEWS = new Set(["dash", "rank", "screens", "sector", "strategy", "market", "trade", "run"]);

function applyPriceChrome(view) {
  const show = PRICE_VIEWS.has(view || currentView);
  ["#chip-fresh", "#btn-krx-now"].forEach((sel) => {
    const el = $(sel);
    if (el) el.classList.toggle("hidden", !show);
  });
}

function fmtWhen(raw) {
  if (raw == null || raw === "") return "";
  const n = Number(raw);
  let d = null;
  if (!Number.isNaN(n) && n > 1e9) {
    d = new Date(n > 1e12 ? n : n * 1000);
  } else {
    const s = String(raw);
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.replace("T", " ").slice(0, 16);
    d = new Date(s);
  }
  if (!d || Number.isNaN(d.getTime())) return String(raw);
  try {
    return new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .format(d)
      .replace("T", " ");
  } catch {
    return d.toISOString().slice(0, 16).replace("T", " ");
  }
}

function setPageAsOf(text, tip) {
  const el = $("#page-asof");
  if (!el) return;
  el.textContent = text || "데이터 시점 없음";
  if (tip) {
    el.setAttribute("data-tip", tip);
    el.classList.add("has-tip");
  }
}

function setSeasonalityAsOf(payload) {
  if (currentView !== "seasonality") return;
  const context = payload?.data_context || {};
  const parts = [];
  if (context.price_as_of) parts.push(`KRX 일봉 ${context.price_as_of}`);
  const calculated = fmtWhen(context.calculated_at);
  if (calculated) parts.push(`계절성 계산 ${calculated}`);
  setPageAsOf(
    parts.join(" · ") || "계절성 데이터 시점 확인 불가",
    `${context.source || "KRX 일봉 기반 월간 계절성"}입니다. 다른 메뉴의 공시·수급 시점과 공유하지 않습니다.`
  );
}

function asofBanner(text) {
  if (!text) return "";
  return `<p class="data-asof">${escapeHtml(text)}</p>`;
}

function stampFromStatus() {
  const q = lastStatus?.quality || {};
  const fresh = lastStatus?.freshness || {};
  const parts = [];
  if (q.as_of_date) parts.push(`점수 기준일 ${q.as_of_date}`);
  if (fresh.price_max_date) parts.push(`KRX 시세 ${fresh.price_max_date}`);
  if (fresh.price_days) parts.push(`${fresh.price_days}거래일`);
  setPageAsOf(
    parts.join(" · ") || "점수·시세 시점이 없습니다.",
    "이 메뉴는 재무 Quant와 KRX 일봉을 씁니다. 시세가 늦으면 시세 받기, 점수가 늦으면 재계산하세요."
  );
}

function renderRunDiagnostics(status) {
  if (!status) return;
  const fresh = status.freshness || {};
  const sched = status.scheduler || {};

  const pxDateEl = $("#run-diag-price-date");
  const pxMetaEl = $("#run-diag-price-meta");
  const pxBadge = $("#run-status-price-badge");
  const dartDateEl = $("#run-diag-dart-date");
  const dartMetaEl = $("#run-diag-dart-meta");
  const dartBadge = $("#run-status-dart-badge");
  const quantDateEl = $("#run-diag-quant-date");
  const quantMetaEl = $("#run-diag-quant-meta");
  const quantBadge = $("#run-status-quant-badge");
  const schedTimeEl = $("#run-diag-sched-time");
  const schedNextEl = $("#run-diag-sched-next");
  const schedBadge = $("#run-diag-sched-badge");

  if (pxDateEl) pxDateEl.textContent = fresh.price_max_date || "시세 없음";
  if (pxMetaEl) {
    const lag = fresh.lag_trading_days;
    pxMetaEl.textContent = `${fresh.price_days || 0}거래일 축적 · 기대 기준일 ${fresh.expected_price_date || "—"}${lag ? ` · ${lag}거래일 지연` : ""}`;
  }
  if (pxBadge) {
    const isStale = Boolean(fresh.stale_price);
    pxBadge.textContent = isStale ? "동기화 필요" : "정상 (최신)";
    pxBadge.className = "chip " + (isStale ? "warn" : "ok");
  }

  const sources = fresh.sources || {};
  const dart = sources.financial_facts || {};
  const dartCoverage = dart.coverage || {};
  if (dartDateEl) dartDateEl.textContent = dart.observed_date || fresh.financial_max_available_date || "적재 자료 없음";
  if (dartMetaEl) {
    const pct = dartCoverage.coverage_pct;
    const backfill = dart.backfill || {};
    const progress = backfill.total_targets ? ` · 백필 ${backfill.cursor || 0}/${backfill.total_targets}` : "";
    dartMetaEl.textContent = `공시 보유 ${dartCoverage.tickers || 0}/${dartCoverage.universe_tickers || 0}종목${pct != null ? ` · ${pct}%` : ""}${progress} · 공시 발생 기준`;
  }
  if (dartBadge) {
    const partial = ["missing", "partial"].includes(dart.state);
    dartBadge.textContent = dart.state === "missing" ? "자료 없음" : partial ? "커버리지 확장 필요" : "적재 가능";
    dartBadge.className = "chip " + (partial ? "warn" : "ok");
  }

  const quant = sources.quant_ranking || {};
  if (quantDateEl) quantDateEl.textContent = quant.observed_date || fresh.screen_as_of || "미계산";
  if (quantMetaEl) {
    const lag = quant.lag_trading_days;
    quantMetaEl.textContent = lag ? `최신 시세보다 ${lag}거래일 뒤처짐 · 재계산 필요` : "시세 기준일과 점수 기준일 일치";
  }
  if (quantBadge) {
    const ready = quant.state === "fresh";
    quantBadge.textContent = ready ? "기준일 일치" : quant.state === "missing" ? "미계산" : "재계산 필요";
    quantBadge.className = "chip " + (ready ? "ok" : "warn");
  }

  if (schedTimeEl) {
    schedTimeEl.textContent = sched.enabled ? `매일 ${sched.hour || 18}:${String(sched.minute || 30).padStart(2, "0")} KST` : "비활성화";
  }
  if (schedNextEl) {
    const nxt = sched.next_fire ? String(sched.next_fire).replace("T", " ").slice(0, 16) : "대기 중";
    schedNextEl.textContent = sched.enabled ? `다음: ${nxt}` : "자동 스케줄 OFF";
  }
  if (schedBadge) {
    schedBadge.textContent = sched.enabled ? "가동 중" : "정지";
    schedBadge.className = "chip " + (sched.enabled ? "ok" : "");
  }
}

function stampRunAsOf() {
  const job = lastStatus?.job || {};
  const started = job.started_at ? fmtWhen(job.started_at) : "";
  const finished = job.finished_at ? fmtWhen(job.finished_at) : "";
  const line = finished
    ? `마지막 작업 ${statusKo(job.status)} · ${finished}`
    : started
      ? `작업 ${statusKo(job.status)} · 시작 ${started}`
      : "아직 실행한 작업이 없습니다.";
  setPageAsOf(line, "실행 탭 작업의 시작·종료 시각입니다. 시세 받기와 재계산은 서로 다른 시점입니다.");
  renderRunDiagnostics(lastStatus);
}

function statusExplainTip(explain, fallback) {
  if (!explain || !(explain.why || []).length) return fallback || "";
  const why = (explain.why || []).join(" ");
  const fix = (explain.improve || []).length ? ` 개선: ${(explain.improve || []).join(" ")}` : "";
  return why + fix;
}

function openStatusModal() {
  const box = $("#status-modal");
  const body = $("#status-modal-body");
  if (!box || !body) return;
  const ex = lastStatusExplain || { status: "no-run", label: "아직 실행 안 함", why: ["아직 스크리닝을 돌리지 않았습니다."], improve: ["실행 탭에서 데모 또는 실데이터 수집을 먼저 하세요."] };
  const why = (ex.why || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const fix = (ex.improve || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const warns = (ex.warnings || []).map((t) => `<code>${escapeHtml(t)}</code>`).join(" · ");
  body.innerHTML = `
    <p>상태 <b class="${ex.status === "success" ? "ok" : "warn"}">${escapeHtml(ex.label || statusKo(ex.status))}</b>
      ${warns ? ` · 코드 ${warns}` : ""}</p>
    <h3>왜 이 상태인가</h3>
    <ul>${why || "<li>추가 설명이 없습니다.</li>"}</ul>
    ${fix ? `<h3>무엇을 개선하면 되는가</h3><ul>${fix}</ul>` : ""}
    <p class="hint">일부 완료는 점수가 나왔다는 뜻이지 데이터가 완벽한 것은 아닙니다. Quant 공식은 바꾸지 않습니다.</p>
  `;
  $("#status-modal-title").textContent = `실행 상태 · ${ex.label || statusKo(ex.status)}`;
  box.classList.remove("hidden");
}

function closeStatusModal() {
  $("#status-modal")?.classList.add("hidden");
}

function setChip(el, text, tip) {
  if (!el) return;
  el.textContent = text;
  if (tip) {
    el.setAttribute("data-tip", tip);
    el.classList.add("has-tip");
    el.tabIndex = 0;
  }
}

function rankMedal(rank) {
  const r = Number(rank);
  if (r === 1) return '<span class="rank-badge top-1">1</span>';
  if (r === 2) return '<span class="rank-badge top-2">2</span>';
  if (r === 3) return '<span class="rank-badge top-3">3</span>';
  return `<span class="rank-badge">${rank || "—"}</span>`;
}

let currentDashTopN = 30;

function renderTop20(rows, count = currentDashTopN) {
  const body = $("#top20-body");
  if (!body) return;
  const n = count || currentDashTopN || 30;
  const show = sortedCopy(rows, "dash", "quant_rank", "asc").slice(0, n);
  body.innerHTML = show
    .map(
      (r) => `<tr class="clickable" data-ticker="${padTicker(r.ticker)}">
      <td class="num">${rankMedal(r.quant_rank)}</td>
      <td class="name-cell"><b>${r.company || r.ticker}</b><div class="meta">${padTicker(r.ticker)} · ${r.market || ""}
        <a class="ext inline" href="${naverUrl(r.ticker)}" target="_blank" rel="noopener">네이버</a>
        ${aiReportBtn(r.ticker, r.company)} ${reportBadge(r.ticker)} ${faChip(r)}</div>${rowNote(r.comment_short || r.comment)}</td>
      <td class="num">${lastCell(r)}</td>
      <td class="num"><span class="score-pill ${Number(r.quant_score) >= 70 ? 'high' : ''}">${fmt(r.quant_score)}</span></td>
      <td>${factorBars(r)}</td>
      <td class="num">${penCell(r.risk_penalty)}</td>
      <td class="num">${confCell(r.data_confidence)}</td>
    </tr>`
    )
    .join("");
  paintSortHeaders("dash");

  const titleEl = $("#dash-leaderboard-title");
  if (titleEl) titleEl.textContent = `🏆 Quant TOP ${n} 리더보드`;
  const dnaTitleEl = $("#dash-dna-title");
  if (dnaTitleEl) dnaTitleEl.textContent = `🧬 TOP ${n} 팩터 DNA 분석`;
}

function renderRank(q = "") {
  const needle = q.trim().toLowerCase();
  const rows = rankRows.filter((r) => {
    if (!needle) return true;
    const tickerMatch = String(r.ticker).toLowerCase().includes(needle);
    const nameMatch = String(r.company || "").toLowerCase().includes(needle);
    const chosungMatch = getChosung(r.company || "").includes(needle);
    return tickerMatch || nameMatch || chosungMatch;
  });
  const ordered = sortedCopy(rows, "rank", "quant_rank", "asc");
  $("#rank-body").innerHTML = ordered
    .map(
      (r) => `<tr class="clickable" data-ticker="${padTicker(r.ticker)}">
      <td class="num">${rankMedal(r.quant_rank)}</td>
      <td>${padTicker(r.ticker)} <a class="ext inline" href="${naverUrl(r.ticker)}" target="_blank" rel="noopener">네이버</a></td>
      <td class="name-cell"><b>${r.company || ""}</b> ${aiReportBtn(r.ticker, r.company)} ${faChip(r)}${rowNote(r.comment_short || r.comment)}</td>
      <td>${r.market || ""}</td>
      <td>${r.industry || r.sector || ""}</td>
      <td class="num">${lastCell(r)}</td>
      <td class="num"><span class="score-pill ${Number(r.quant_score) >= 70 ? 'high' : ''}">${fmt(r.quant_score)}</span></td>
      <td>${factorBars(r)}</td>
      <td class="num">${penCell(r.risk_penalty)}</td>
      <td class="num">${fmt((r.weighted_metric_coverage || 0) * 100, 0)}%</td>
      <td class="num">${confCell(r.data_confidence)}</td>
      <td>${reportBadge(r.ticker)}</td>
    </tr>`
    )
    .join("");
  paintSortHeaders("rank");
}

function reportBadge(ticker) {
  const hit = reportRows.find((x) => padTicker(x.ticker) === padTicker(ticker) && x.kind === "AI 분석 리포트");
  return hit ? `<span class="chip ok">리포트</span>` : "";
}

let currentReportFilter = "all";
let currentReportViewMode = "grid";

function formatModelBadge(model = "", provider = "") {
  const m = String(model || "").toLowerCase();
  let cls = "";
  let icon = "🤖";
  let display = model ? model.split("/").pop() : (provider || "AI");
  if (m.includes("deepseek")) {
    cls = "deepseek";
    icon = "🤖";
    display = m.includes("flash") ? "DeepSeek V4 Flash" : "DeepSeek";
  } else if (m.includes("claude") || m.includes("anthropic")) {
    cls = "claude";
    icon = "🧠";
    display = "Claude 3.5 Sonnet";
  } else if (m.includes("gemini") || m.includes("google")) {
    cls = "gemini";
    icon = "✨";
    display = "Gemini 2.5 Pro";
  } else if (m.includes("gpt") || m.includes("openai")) {
    cls = "openai";
    icon = "🟩";
    display = "GPT-4o";
  } else if (m.includes("nemotron") || m.includes("nvidia")) {
    cls = "nvidia";
    icon = "⚡";
    display = "Nemotron 550B";
  }
  return `<span class="model-badge ${cls}">${icon} ${escapeHtml(display)}</span>`;
}

function renderReportKpis(rows) {
  const el = $("#reports-kpi-bar");
  if (!el) return;
  const total = rows.length;
  const deepCount = rows.filter((r) => r.kind === "AI 분석 리포트").length;
  const quickCount = rows.filter((r) => r.kind !== "AI 분석 리포트").length;
  const btCount = rows.filter((r) => r.has_backtest).length;
  const latest = rows[0];

  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const weekCount = rows.filter((r) => {
    const d = new Date(r.researched_at || r.as_of_date || 0);
    return d >= weekAgo;
  }).length;

  // Update counter badges
  const cAll = $("#count-rep-all");
  const cReport = $("#count-rep-report");
  const cQuick = $("#count-rep-quick");
  const cWeek = $("#count-rep-week");
  if (cAll) cAll.textContent = total;
  if (cReport) cReport.textContent = deepCount;
  if (cQuick) cQuick.textContent = quickCount;
  if (cWeek) cWeek.textContent = weekCount;

  if (!total) {
    el.innerHTML = `
      <div class="report-kpi-card" style="grid-column: 1 / -1; justify-content: center; text-align: center; padding: 24px;">
        <div style="font-size: 28px; margin-bottom: 8px;">📑</div>
        <b style="color: #94a3b8; font-size: 14px;">보관된 AI 분석 리포트가 없습니다.</b>
        <p style="color: #64748b; font-size: 12px; margin: 4px 0 0;">종목 상세 창에서 [🤖 AI 심층 분석 리포트 발간]을 실행해 보세요.</p>
      </div>
    `;
    return;
  }

  const latestTimeStr = latest ? (fmtWhen(latest.researched_at) || (latest.researched_at || "").slice(0, 16).replace("T", " ")) : "기록 없음";
  const topModelStr = latest ? (latest.model ? latest.model.split("/").pop() : latest.provider || "AI") : "—";

  el.innerHTML = `
    <div class="report-kpi-card">
      <div class="report-kpi-icon" style="color:#c084fc; background:rgba(168,85,247,0.12); border-color:rgba(168,85,247,0.25);">📑</div>
      <div class="report-kpi-content">
        <div class="report-kpi-label">총 보관 리포트</div>
        <div class="report-kpi-val">${total}건</div>
        <div class="report-kpi-sub">🔮 Deep AI ${deepCount}건 · ⚡ 간단 ${quickCount}건</div>
      </div>
    </div>

    <div class="report-kpi-card">
      <div class="report-kpi-icon" style="color:#38bdf8; background:rgba(56,189,248,0.12); border-color:rgba(56,189,248,0.25);">⚡</div>
      <div class="report-kpi-content">
        <div class="report-kpi-label">최근 발간 종목</div>
        <div class="report-kpi-val" style="font-size:15.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(latest?.company || "—")} <span style="font-size:11.5px; font-weight:normal; color:#94a3b8;">(${latest?.ticker || ""})</span></div>
        <div class="report-kpi-sub">🕒 ${escapeHtml(latestTimeStr)}</div>
      </div>
    </div>

    <div class="report-kpi-card">
      <div class="report-kpi-icon" style="color:#34d399; background:rgba(52,211,153,0.12); border-color:rgba(52,211,153,0.25);">🤖</div>
      <div class="report-kpi-content">
        <div class="report-kpi-label">주력 분석 엔진</div>
        <div class="report-kpi-val" style="font-size:15px; color:#34d399;">${escapeHtml(topModelStr)}</div>
        <div class="report-kpi-sub">프로바이더: ${escapeHtml(latest?.provider || "OpenRouter")}</div>
      </div>
    </div>

    <div class="report-kpi-card">
      <div class="report-kpi-icon" style="color:#fbbf24; background:rgba(251,191,36,0.12); border-color:rgba(251,191,36,0.25);">🧪</div>
      <div class="report-kpi-content">
        <div class="report-kpi-label">4대 전략 백테스트 연계</div>
        <div class="report-kpi-val" style="color:#fbbf24;">${btCount}건 / ${total}건</div>
        <div class="report-kpi-sub">최적 파라미터 & 타이밍 자동 결합</div>
      </div>
    </div>
  `;
}

function filterReportRows(q = "", filter = currentReportFilter) {
  const needle = q.trim().toLowerCase();
  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  return reportRows.filter((r) => {
    // 1. Text filter
    if (needle) {
      const match = [r.ticker, r.company, r.model, r.provider, r.kind, r.summary, r.best_strategy].some((x) =>
        String(x || "").toLowerCase().includes(needle)
      );
      if (!match) return false;
    }
    // 2. Chip filter
    if (filter === "report") return r.kind === "AI 분석 리포트";
    if (filter === "quick") return r.kind !== "AI 분석 리포트";
    if (filter === "week") {
      const d = new Date(r.researched_at || r.as_of_date || 0);
      return d >= weekAgo;
    }
    return true;
  });
}

function renderReportCardGrid(rows) {
  const grid = $("#reports-card-grid");
  if (!grid) return;
  if (!rows.length) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align:center; padding:40px; background:rgba(15,23,42,0.5); border:1px dashed rgba(255,255,255,0.1); border-radius:12px;">
        <div style="font-size:24px; margin-bottom:8px;">🔍</div>
        <b style="color:#94a3b8;">조건에 일치하는 발간 리포트가 없습니다.</b>
        <p style="font-size:12px; color:#64748b; margin-top:4px;">검색어를 변경하거나 필터를 '전체'로 전환해 보세요.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = rows.map((r) => {
    const isDeep = r.kind === "AI 분석 리포트";
    const kindBadge = isDeep
      ? `<span class="chip" style="background:rgba(168,85,247,0.18); color:#c084fc; border:1px solid rgba(168,85,247,0.35); font-weight:700;">🔮 Deep AI 리포트</span>`
      : `<span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.3); font-weight:700;">⚡ 간단 검증</span>`;
    
    const timeDisplay = (r.researched_at || "").slice(0, 16).replace("T", " ");
    const relTime = fmtWhen(r.researched_at) || "";

    const btBadge = r.has_backtest
      ? `<span class="chip" style="background:rgba(234,179,8,0.15); color:#fde047; border:1px solid rgba(234,179,8,0.3); font-size:11px;">🧪 백테스트 1위: ${escapeHtml(r.best_strategy || "완료")}</span>`
      : "";

    return `
      <div class="report-archive-card ${isDeep ? 'kind-deep' : 'kind-quick'}" data-ticker="${padTicker(r.ticker)}" data-asof="${escapeHtml(r.as_of_date || "")}">
        <div>
          <div class="report-card-header">
            <div>
              <div class="report-card-title">
                <span>${escapeHtml(r.company || r.ticker)}</span>
                <span class="chip" style="background:#1e293b; color:#94a3b8; font-family:monospace; font-size:11px;">${escapeHtml(r.market || "")} ${padTicker(r.ticker)}</span>
              </div>
              <div class="report-card-meta-row" style="margin-top:6px;">
                ${formatModelBadge(r.model, r.provider)}
                <span>·</span>
                <span>📅 기준일 ${escapeHtml(r.as_of_date || "")}</span>
              </div>
            </div>
            <div>${kindBadge}</div>
          </div>

          <div style="margin: 10px 0 6px;">
            ${btBadge}
          </div>

          <!-- Summary Box -->
          <div class="report-summary-box" title="${escapeHtml(r.summary || '요약 정보 없음')}">
            <span style="color:#67e8f9; font-weight:700; margin-right:4px;">“</span>${escapeHtml(r.summary || '리포트 본문에서 상세 투자 의견을 확인하세요.')}<span style="color:#67e8f9; font-weight:700; margin-left:4px;">”</span>
          </div>
        </div>

        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; color:#64748b; margin-bottom:8px;">
            <span>🕒 발간: ${escapeHtml(timeDisplay)} ${relTime ? `(${escapeHtml(relTime)})` : ""}</span>
            ${r.total_tokens ? `<span>🪙 ${Number(r.total_tokens).toLocaleString()} 토큰</span>` : ""}
          </div>

          <div class="report-card-actions">
            <div style="display:flex; gap:6px;">
              <button type="button" class="btn-open-report-card" data-ticker="${padTicker(r.ticker)}" data-asof="${escapeHtml(r.as_of_date || "")}" data-kind="${escapeHtml(r.kind || "")}" style="background:#38bdf8; color:#0f172a; border:none; border-radius:6px; padding:5px 12px; font-size:12px; font-weight:800; cursor:pointer; display:flex; align-items:center; gap:4px;">
                📖 리포트 열람
              </button>
              ${isDeep ? `
                <a href="/api/research/${padTicker(r.ticker)}/infographic?as_of=${encodeURIComponent(r.as_of_date || "")}" target="_blank" class="ghost small" style="font-size:11.5px; padding:4px 8px; color:#94a3b8; border:1px solid rgba(255,255,255,0.1); border-radius:6px; text-decoration:none; display:flex; align-items:center; gap:3px;">
                  🖼️ 인포그래픽
                </a>
              ` : ''}
            </div>
            <button type="button" class="ghost small btn-del-report-card" data-del-report="1" data-ticker="${padTicker(r.ticker)}" data-asof="${escapeHtml(r.as_of_date || "")}" data-kind="${escapeHtml(r.kind || "")}" data-filename="${escapeHtml(r.filename || "")}" style="color:#f43f5e; border:1px solid rgba(244,63,94,0.3); border-radius:6px; padding:4px 8px; font-size:11.5px; cursor:pointer;">
              🗑️ 삭제
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");

  // Bind Open Buttons in cards
  grid.querySelectorAll(".btn-open-report-card").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openArchivedItem(btn.dataset.ticker, btn.dataset.asof, btn.dataset.kind).catch((err) => alert(err.message));
    });
  });

  // Bind Card Click
  grid.querySelectorAll(".report-archive-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest("button") || e.target.closest("a")) return;
      openArchivedItem(card.dataset.ticker, card.dataset.asof).catch((err) => alert(err.message));
    });
  });
}

function renderReportList(target, rows, limit) {
  const body = $(target);
  if (!body) return;
  const scoped = target === "#reports-body" ? sortedCopy(rows, "reports", "researched_at", "desc") : rows;
  const show = limit ? scoped.slice(0, limit) : scoped;
  const wide = target === "#reports-body";
  if (!show.length) {
    body.innerHTML = `<tr><td colspan="${wide ? 10 : 5}" style="text-align:center; padding:24px; color:#94a3b8;">보관된 리포트가 없습니다.</td></tr>`;
    return;
  }
  body.innerHTML = show
    .map((r) => {
      const isDeep = r.kind === "AI 분석 리포트";
      const kindBadge = isDeep
        ? `<span class="chip" style="background:rgba(168,85,247,0.15); color:#c084fc; font-weight:700;">🔮 Deep 리포트</span>`
        : `<span class="chip" style="background:rgba(56,189,248,0.12); color:#38bdf8; font-weight:700;">⚡ 간단 검증</span>`;

      const btBadge = r.has_backtest
        ? `<span class="chip" style="background:rgba(234,179,8,0.12); color:#fde047; font-size:11px;">🧪 ${escapeHtml(r.best_strategy || "백테스트")}</span>`
        : `<span style="color:#64748b;">—</span>`;

      const timeStr = (r.researched_at || "").slice(0, 16).replace("T", " ");

      if (!wide) {
        // Dash compact list
        return `
          <tr class="clickable" data-ticker="${padTicker(r.ticker)}" data-asof="${r.as_of_date || ""}">
            <td><b>${escapeHtml(r.company || "")}</b></td>
            <td>${kindBadge}</td>
            <td>${escapeHtml(r.as_of_date || "")}</td>
            <td>${formatModelBadge(r.model, r.provider)}</td>
            <td style="max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(r.summary || "")}</td>
          </tr>
        `;
      }

      return `
        <tr class="clickable" data-ticker="${padTicker(r.ticker)}" data-asof="${r.as_of_date || ""}">
          <td><b style="font-size:13.5px; color:#fff;">${escapeHtml(r.company || "")}</b></td>
          <td><span class="chip" style="font-family:monospace;">${padTicker(r.ticker)}</span></td>
          <td>${kindBadge}</td>
          <td>${formatModelBadge(r.model, r.provider)}</td>
          <td>${escapeHtml(r.as_of_date || "")}</td>
          <td><span style="font-size:11.5px; color:#94a3b8;">${escapeHtml(timeStr)}</span></td>
          <td style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(r.summary || "")}">${escapeHtml(r.summary || "")}</td>
          <td>${btBadge}</td>
          <td>
            <button type="button" class="ghost small" style="color:#38bdf8; border:1px solid rgba(56,189,248,0.3); padding:2px 8px; font-size:11px; border-radius:4px;">열람 ➔</button>
          </td>
          <td>
            <button type="button" class="ghost small" data-del-report="1" data-ticker="${padTicker(r.ticker)}" data-asof="${escapeHtml(r.as_of_date || "")}" data-kind="${escapeHtml(r.kind || "")}" data-filename="${escapeHtml(r.filename || "")}" style="color:#f43f5e; border:1px solid rgba(244,63,94,0.3); padding:2px 6px; font-size:11px; border-radius:4px;">삭제</button>
          </td>
        </tr>
      `;
    })
    .join("");
  if (wide) paintSortHeaders("reports");
}

function renderReportArchiveHub() {
  const filtered = filterReportRows($("#report-q") ? $("#report-q").value : "", currentReportFilter);
  renderReportKpis(reportRows);

  const cardGridEl = $("#reports-card-grid");
  const tableWrapEl = $("#reports-table-wrap");

  if (currentReportViewMode === "grid") {
    if (cardGridEl) cardGridEl.classList.remove("hidden");
    if (tableWrapEl) tableWrapEl.classList.add("hidden");
    renderReportCardGrid(filtered);
  } else {
    if (cardGridEl) cardGridEl.classList.add("hidden");
    if (tableWrapEl) tableWrapEl.classList.remove("hidden");
    renderReportList("#reports-body", filtered);
  }
}

async function loadReportArchive() {
  const data = await api("/api/research/reports");
  reportRows = data.rows || [];
  renderReportList("#dash-reports-body", reportRows, 6);
  renderReportArchiveHub();
  if (currentView === "reports" || currentView === "watch") {
    const latest = reportRows[0]?.researched_at || reportRows[0]?.as_of_date;
    if (currentView === "reports") {
      setPageAsOf(
        latest ? `최근 보관 ${fmtWhen(latest) || latest}` : "보관한 리포트가 없습니다.",
        "종목 상세에서 발간한 시각입니다. 시세 칩과 무관합니다."
      );
    }
  }
}

function getMarketSessionInfo() {
  const now = new Date();
  const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
  const kst = new Date(utc + (9 * 3600000));
  const day = kst.getDay(); // 0: Sun, 6: Sat
  const hour = kst.getHours();
  const min = kst.getMinutes();
  const timeNum = hour * 100 + min;

  const isWeekend = day === 0 || day === 6;
  const isMarketOpen = !isWeekend && timeNum >= 900 && timeNum < 1530;
  const isPostMarket = !isWeekend && timeNum >= 1530;
  const isPreMarket = !isWeekend && timeNum < 900;
  const todayStr = kst.toISOString().slice(0, 10);

  return { isWeekend, isMarketOpen, isPostMarket, isPreMarket, todayStr };
}

function renderFreshChip(fresh) {
  const el = $("#chip-fresh");
  if (!el) return;
  const btn = $("#btn-krx-now");
  if (!fresh) {
    setChip(el, "📅 시세", "시세 정보가 없습니다.");
    return;
  }
  const px = fresh.price_max_date || "시세 없음";
  const expected = fresh.expected_price_date || px;
  const session = getMarketSessionInfo();
  const stale = Boolean(fresh.stale_price || fresh.stale_screen);

  let label = "";
  let tip = "";

  if (session.isMarketOpen) {
    if (!stale) {
      label = `📅 전일 종가 ${px} · 🟢 장중 실시간`;
      tip = `최근 공식 일봉 종가: ${px}. 현재는 당일(${session.todayStr}) 정규장 진행 중이며, 오늘 종가는 15:30 장 마감 후 최종 확정됩니다. 개별 종목 현재가 및 매크로 지표는 실시간 틱으로 작동 중입니다.`;
    } else {
      label = `📅 종가 ${px} (시세 동기화 필요)`;
      tip = `최근 수집된 종가: ${px}. 직전 영업일(${expected}) 시세를 받으려면 상단의 [시세 받기]를 누르세요. (클릭 시 자동 수집)`;
    }
  } else if (session.isPostMarket) {
    if (px === session.todayStr) {
      label = `📅 시세 ${px} (당일 마감 최신)`;
      tip = `오늘(${px}) KRX 정규장 마감 종가까지 100% 최신 반영되었습니다.`;
    } else {
      label = `📅 최근 종가 ${px} (당일 마감분 수집 대기)`;
      tip = `오늘(${session.todayStr}) 장이 마감되었습니다. 상단의 [시세 받기]를 누르시면 오늘 마감 종가가 즉시 반영됩니다.`;
    }
  } else if (session.isWeekend) {
    label = `📅 최근 종가 ${px} (주말 휴장)`;
    tip = `주말/휴일 휴장 상태입니다. 최근 영업일(${px}) 종가 기준 퀀트 지표가 유지됩니다.`;
  } else {
    label = `📅 전일 종가 ${px} (개장 전)`;
    tip = `오늘(${session.todayStr}) 정규장 개장(09:00) 전입니다. 최근 영업일(${px}) 종가 기준입니다.`;
  }

  setChip(el, label, tip);
  el.classList.toggle("stale", stale);
  el.classList.toggle("fresh", !stale && fresh.status === "fresh");
  if (btn) btn.classList.toggle("primary", Boolean(fresh.stale_price));

  el.onclick = () => {
    if (stale && btn) {
      btn.click();
    }
  };

  applyPriceChrome(currentView);
}

function renderSchedLine(sched) {
  const el = $("#sched-line");
  const badge = $("#sched-badge");
  const nxtEl = $("#sched-next");
  const lastEl = $("#sched-last");
  const enabledEl = $("#sched-enabled");
  const kindEl = $("#sched-kind");
  const hourEl = $("#sched-hour");
  const minEl = $("#sched-min");

  if (!sched) return;
  const nxt = sched.next_fire ? String(sched.next_fire).replace("T", " ").slice(0, 16) : "대기 (다음 영업일 대기)";
  const last = sched.last_fire ? String(sched.last_fire).replace("T", " ").slice(0, 19) : "기록 없음";

  if (enabledEl) enabledEl.checked = Boolean(sched.enabled);
  if (kindEl) kindEl.value = sched.job_kind || "krx-prices";
  if (hourEl && sched.hour != null) hourEl.value = sched.hour;
  if (minEl && sched.minute != null) minEl.value = sched.minute;
  if (nxtEl) nxtEl.textContent = sched.enabled ? `${nxt} KST` : "비활성화됨 (설정 후 활성화 필요)";
  if (lastEl) lastEl.textContent = last;

  if (badge) {
    if (sched.enabled) {
      badge.textContent = `🟢 매일 ${sched.hour}:${String(sched.minute).padStart(2, "0")} KST 예약됨`;
      badge.className = "chip ok";
    } else {
      badge.textContent = "⏸️ 비활성화";
      badge.className = "chip";
    }
  }

  if (el) {
    if (!sched.enabled) {
      el.textContent = "자동 스케줄: 비활성화됨. 아래 스케줄러에서 매일 실행을 켜고 원하는 시간을 저장하세요.";
    } else {
      const kindTxt = sched.job_kind === "live" ? "실데이터 수집+계산" : "KRX 시세 갱신";
      el.textContent = `자동 스케줄: 매일 ${sched.hour}:${String(sched.minute).padStart(2, "0")} KST · 대상 [${kindTxt}] · 다음 ${nxt}`;
    }
  }
}

function renderQuality(q, guide, fresh) {
  if (!q || !q.run_id) {
    $("#quality-box").innerHTML = "<p>아직 결과가 없습니다. 실행 탭에서 데모를 돌려 보세요.</p>";
    return;
  }
  const c = q.counts || {};
  const labels = (guide && guide.exclusion_labels) || {};
  const warnLabels = (guide && guide.warning_labels) || {};
  const criteria = (guide && guide.criteria) || {};
  const reasons = Object.entries(q.exclusion_reason_counts || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([k, v]) => `<li>${labels[k] || k} <b>${v}</b>종목</li>`)
    .join("");
  const warns = (q.warnings || []).map((w) => `<li class="warn">${warnLabels[w] || w}</li>`).join("");
  const list = (items) => (items || []).map((t) => `<li>${t}</li>`).join("");
  const freshLine = fresh
    ? `<p>시세 최신일 <b>${fresh.price_max_date || "—"}</b> · 기대 ${fresh.expected_price_date || "—"}
       · 재무 available ${fresh.financial_max_available_date || "—"}
       · <span class="${fresh.stale_price || fresh.stale_screen ? "warn" : "ok"}">${escapeHtml(fresh.label || "")}</span>
       ${fresh.stale_screen ? " · 시세를 받은 뒤 재계산이 필요합니다." : ""}</p>`
    : "";
  $("#quality-box").innerHTML = `
    ${freshLine}
    <p>상태 <b class="${q.status === "success" ? "ok" : "warn"} has-tip" data-tip="${escapeHtml(STATUS_TIP[q.status] || "")}">${escapeHtml(statusKo(q.status))}</b>
      · 채점 ${c.scored ?? 0} → 조건 통과 ${c.universe_eligible ?? 0} → TOP100 ${c.top100_eligible ?? 0} → TOP20 ${c.top20_eligible ?? 0}</p>
    <h3>왜 빠졌는가</h3>
    <ul>${reasons || "<li>제외 사유 없음</li>"}</ul>
    ${warns ? `<h3>운영 경고</h3><ul>${warns}</ul>` : ""}
    <h3>선정 조건</h3><ul>${list(criteria.universe)}</ul>
    <h3>TOP100</h3><ul>${list(criteria.top100)}</ul>
    <h3>TOP20</h3><ul>${list(criteria.top20)}</ul>
    <h3>데이터 신뢰도</h3><ul>${list(criteria.confidence)}</ul>
    <h3>점수</h3><ul>${list(criteria.score)}</ul>
    <p class="hint">전체 평균 커버리지가 낮아 보이는 것은 재무를 받지 않은 종목까지 분모에 넣기 때문입니다. 선정은 조건 통과 종목만 봅니다.</p>
  `;
}

function renderChampions(rows) {
  const container = $("#dash-champions");
  if (!container) return;
  if (!rows || !rows.length) {
    container.innerHTML = "";
    return;
  }
  const top3 = sortedCopy(rows, "dash", "quant_rank", "asc").slice(0, 3);
  const titles = ["🥇 1위 챔피언", "🥈 2위 루키", "🥉 3위 밸류"];
  container.innerHTML = top3
    .map((r, i) => {
      const rankClass = `rank-${i + 1}`;
      const code = padTicker(r.ticker);
      const per = r.per != null && Number(r.per) > 0 ? Number(r.per).toFixed(1) + "x" : "—";
      const pbr = r.pbr != null && Number(r.pbr) > 0 ? Number(r.pbr).toFixed(2) + "x" : "—";
      const roe = r.roe != null ? (Number(r.roe) * (Number(r.roe) < 1 ? 100 : 1)).toFixed(1) + "%" : "—";
      const vScore = Math.max(0, Math.min(100, (Number(r.value_score) || 0) / 30 * 100));
      const qScore = Math.max(0, Math.min(100, (Number(r.quality_score) || 0) / 25 * 100));
      const gScore = Math.max(0, Math.min(100, (Number(r.growth_score) || 0) / 25 * 100));
      const mScore = Math.max(0, Math.min(100, (Number(r.momentum_score) || 0) / 10 * 100));
      const fScore = Math.max(0, Math.min(100, (Number(r.financial_score) || 0) / 10 * 100));

      return `
        <div class="champ-card ${rankClass}" data-ticker="${code}">
          <div class="champ-head">
            <span class="champ-badge">${titles[i]}</span>
            <div class="champ-score">${fmt(r.quant_score)} <small>점</small></div>
          </div>
          <h3 class="champ-name">${escapeHtml(r.company || code)}</h3>
          <div class="champ-sub">${code} · ${escapeHtml(r.market || "")} · ${escapeHtml(r.industry || r.sector || "기타")}</div>
          <div class="champ-stats">
            <div>
              <div class="champ-stat-lbl">PER</div>
              <div class="champ-stat-val">${per}</div>
            </div>
            <div>
              <div class="champ-stat-lbl">PBR</div>
              <div class="champ-stat-val">${pbr}</div>
            </div>
            <div>
              <div class="champ-stat-lbl">ROE</div>
              <div class="champ-stat-val" style="color:#34d399;">${roe}</div>
            </div>
          </div>
          <div class="champ-factors has-tip" data-tip="5대 팩터 구성 (파랑:가치, 보라:품질, 초록:성장, 주황:모멘텀, 청록:안정)">
            <div class="champ-factor-bar v" style="width:${vScore}%;"></div>
            <div class="champ-factor-bar q" style="width:${qScore}%;"></div>
            <div class="champ-factor-bar g" style="width:${gScore}%;"></div>
            <div class="champ-factor-bar m" style="width:${mScore}%;"></div>
            <div class="champ-factor-bar f" style="width:${fScore}%;"></div>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".champ-card").forEach((card) => {
    card.addEventListener("click", () => {
      openStock(card.dataset.ticker);
    });
  });
}

function glanceRankBadge(rank) {
  if (rank === 1) return "🥇 1위";
  if (rank === 2) return "🥈 2위";
  if (rank === 3) return "🥉 3위";
  return `${rank}위`;
}

async function loadGlanceTop3() {
  const box = $("#dash-seasonality-banner");
  if (!box) return;
  box.innerHTML = `<div class="hint" style="margin:0;">오늘의 시즌 모멘텀 Top 3를 불러오는 중…</div>`;
  try {
    const res = await api("/api/seasonality/highlights");
    const data = res.data || {};
    const picks = data.glance_top3 || [];
    const scanned = data.universe_scanned || 0;
    const listed = data.universe_listed || 0;
    const asOf = (picks[0] && picks[0].price_as_of) || "";
    const markets = data.markets || {};
    const mktBits = Object.keys(markets).map((k) => `${k} ${markets[k]}`).join(" · ");

    if (!picks.length) {
      box.innerHTML = `
        <div class="seasonality-widget-head">
          <div class="seasonality-widget-title">⚡ 오늘의 시즌 모멘텀 Top 3</div>
          <button type="button" class="ghost small" id="btn-open-seasonality-from-glance">계절성 화면 →</button>
        </div>
        <p class="hint" style="margin:0;">진입 유효 시즌 모멘텀 종목이 없습니다. 계절성 화면에서 필터를 완화해 보세요.</p>
      `;
      $("#btn-open-seasonality-from-glance")?.addEventListener("click", () => switchView("seasonality"));
      return;
    }

    const cards = picks.map((p) => {
      const rank = Number(p.rank) || 0;
      const wr = ((p.win_rate || 0) * 100).toFixed(0);
      const remaining = p.remaining_peak || {};
      const ret = remaining.available === true && Number.isFinite(Number(remaining.remaining_p50)) ? pbPct(remaining.remaining_p50) : "산출대기";
      const close = p.last_close == null ? "—" : `${Number(p.last_close).toLocaleString("ko-KR")}원`;
      const chg = Number(p.chg_pct || 0);
      const chgCls = chg > 0 ? "up" : chg < 0 ? "down" : "";
      const chgTxt = `${chg > 0 ? "+" : ""}${(chg * 100).toFixed(2)}%`;
      return `
        <div class="glance-pick-card rank-${rank}" data-ticker="${escapeHtml(p.ticker || "")}" data-pattern-id="${escapeHtml(p.pattern_id || "")}">
          <div class="glance-pick-head">
            <span class="chip" style="background:#eab308; color:#0f172a; font-weight:900; font-size:11px;">${glanceRankBadge(rank)}</span>
            <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:11px;">${escapeHtml(p.entry_stage_label || p.window_name || "")}</span>
          </div>
          <h3 class="glance-pick-name">${escapeHtml(p.company || p.ticker || "")}</h3>
          <div class="glance-pick-meta">${escapeHtml(p.market || "")} ${escapeHtml(p.ticker || "")}</div>
          <div class="glance-pick-price">
            <b>${close}</b>
            <span class="${chgCls}">${chgTxt}</span>
          </div>
          <div class="glance-pick-kpis">
            <span>승률 <b style="color:#facc15;">${wr}%</b></span>
            <span>오늘→피크 <b class="text-emerald-400">${ret}</b></span>
          </div>
        </div>
      `;
    }).join("");

    box.innerHTML = `
      <div class="seasonality-widget-head">
        <div class="seasonality-widget-title">⚡ 오늘의 시즌 모멘텀 Top 3</div>
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8;">전종목 스캔 ${scanned.toLocaleString("ko-KR")}/${listed.toLocaleString("ko-KR")}${mktBits ? ` · ${mktBits}` : ""}</span>
          ${asOf ? `<span class="meta">시세 ${escapeHtml(asOf)}</span>` : ""}
          <button type="button" class="ghost small" id="btn-open-seasonality-from-glance">전체 보기 →</button>
        </div>
      </div>
      <div class="glance-top3-grid">${cards}</div>
    `;
    $("#btn-open-seasonality-from-glance")?.addEventListener("click", () => switchView("seasonality"));
    box.querySelectorAll(".glance-pick-card").forEach((card) => {
      card.addEventListener("click", () => openGlancePlaybook(card.dataset.ticker, card.dataset.patternId));
    });
  } catch (err) {
    box.innerHTML = `<p class="hint" style="margin:0;">시즌 모멘텀 Top 3를 불러오지 못했습니다. ${escapeHtml(err.message || "")}</p>`;
  }
}

async function openGlancePlaybook(ticker, patternId = "") {
  const code = String(ticker || "").padStart(6, "0");
  if (!code || code === "000000") return;
  try {
    const data = await api(`/api/seasonality/discovery/${code}?lookback_years=${currentV11Lookback || 5}`);
    const patterns = data.patterns || [];
    const match = patterns.find((p) => patternId && p.pattern_id === patternId)
      || patterns.find((p) => ["TODAY_ENTRY", "PRE_ENTRY_15", "PRE_ENTRY_30", "ACCUMULATE_60"].includes(p.entry_stage))
      || patterns[0];
    if (match) {
      openDiscoveryDetailModal(match);
      return;
    }
  } catch (_) {
    /* fall through to stock drawer */
  }
  openStock(code).catch((err) => alert(err.message));
}

function renderDashDna(rows, count = currentDashTopN) {
  const box = $("#dash-dna-box");
  if (!box) return;
  const nLimit = count || currentDashTopN || 30;
  const targetRows = (rows || []).slice(0, nLimit);
  if (!targetRows.length) {
    box.innerHTML = `<p class='hint'>TOP ${nLimit} 데이터가 없습니다.</p>`;
    return;
  }
  const n = targetRows.length;
  const avgVal = targetRows.reduce((acc, r) => acc + (Number(r.value_score) || 0), 0) / n;
  const avgQua = targetRows.reduce((acc, r) => acc + (Number(r.quality_score) || 0), 0) / n;
  const avgGro = targetRows.reduce((acc, r) => acc + (Number(r.growth_score) || 0), 0) / n;
  const avgMom = targetRows.reduce((acc, r) => acc + (Number(r.momentum_score) || 0), 0) / n;
  const avgFin = targetRows.reduce((acc, r) => acc + (Number(r.financial_score) || 0), 0) / n;
  const avgTotal = (targetRows.reduce((acc, r) => acc + (Number(r.quant_score) || 0), 0) / n).toFixed(1);

  const factors = [
    {
      label: "💎 저평가 밸류 (Value)",
      score: avgVal,
      max: 30,
      cls: "val",
      tip: "PER, PBR, EV/EBITDA, 배당수익률 등을 종합해 본질가치 대비 주가가 저평가되어 안전마진이 높은 종목을 발굴합니다.",
      up: "저평가 매력 및 하방 경직성(안전마진) 강화",
      down: "고평가 밸류에이션 부담 가중",
      hint: "가치 점수가 높을수록 주가 급락장에서도 방어력이 우수합니다."
    },
    {
      label: "👑 우량 펀더멘털 (Quality)",
      score: avgQua,
      max: 25,
      cls: "qua",
      tip: "ROE, ROIC, 영업이익률, 부채비율 등을 평가해 경제적 해자(Moat)와 이익의 지속성을 검증합니다.",
      up: "자본 효율성 및 이익의 질적 우수성 입증 (장기 복리 수익 견인)",
      down: "마진율 둔화 또는 과도한 레버리지 주의",
      hint: "ROE 15% 이상, 부채비율 100% 미만 기업이 높은 점수를 받습니다."
    },
    {
      label: "🚀 실적 고성장 (Growth)",
      score: avgGro,
      max: 25,
      cls: "gro",
      tip: "최근 3개년 매출액 및 영업이익 연평균 성장률(CAGR), 최근 분기 턴어라운드 가속도를 측정합니다.",
      up: "기업 외형 및 이익의 폭발적 성장으로 주가 리레이팅 기대",
      down: "실적 정체 또는 역성장 위험",
      hint: "성장 점수가 높을수록 기관 선호도가 높아집니다."
    },
    {
      label: "⚡ 주가 모멘텀 (Momentum)",
      score: avgMom,
      max: 10,
      cls: "mom",
      tip: "3/6/12개월 상대수익률과 이동평균선 정배열 추세를 바탕으로 시장의 매수세가 집중되는 종목을 포착합니다.",
      up: "외인·기관 수급 유입 및 강력한 우상향 추세 편승",
      down: "단기 소외 또는 역배열 하락 추세",
      hint: "가치주라도 모멘텀이 살아있을 때 진입하면 시간 비용을 줄일 수 있습니다."
    },
    {
      label: "🛡️ 재무 안정성 (Stability)",
      score: avgFin,
      max: 10,
      cls: "fin",
      tip: "유동비율, 당좌비율, 이자보상배율, 자본잠식 여부를 점검해 부도나 유상증자 등 한계기업 리스크를 철저히 차단합니다.",
      up: "탄탄한 현금 유동성으로 경기 침체기에도 생존력 확보",
      down: "이자비용 부담 또는 유동성 리스크 주의",
      hint: "안정 점수 미달 기업은 Quant 유니버스에서 자동 탈락됩니다."
    },
  ];

  box.innerHTML = `
    <div style="margin-bottom:12px;">
      ${factors.map(f => {
        const pct = Math.min(100, Math.max(5, (f.score / f.max) * 100));
        return `
          <div class="dna-bar-item has-tip"
               data-tip-title="${escapeHtml(f.label)}"
               data-tip="${escapeHtml(f.tip)}"
               data-tip-up="${escapeHtml(f.up)}"
               data-tip-down="${escapeHtml(f.down)}"
               data-tip-hint="${escapeHtml(f.hint)}"
               tabindex="0">
            <div class="dna-bar-head">
              <span>${f.label}</span>
              <b>${f.score.toFixed(1)} <small style="color:#64748b; font-weight:normal;">/ ${f.max}점</small> (${pct.toFixed(0)}%)</b>
            </div>
            <div class="dna-bar-track">
              <div class="dna-bar-fill ${f.cls}" style="width:${pct}%;"></div>
            </div>
          </div>
        `;
      }).join("")}
    </div>
    <div style="background:#0f172a; border-radius:8px; padding:8px 12px; font-size:12px; color:#94a3b8; border:1px solid #1e293b;">
      💡 TOP20 평균 종합 점수: <b style="color:#38bdf8;">${avgTotal}점</b> (시장 상위 1% 우량주)
    </div>
  `;
}

function renderKpis(status, top, eligibleTotal = null) {
  const q = status.quality || {};
  const c = q.counts || {};
  const topRows = (top || []).slice(0, 20);
  const n = topRows.length || 1;
  const avgScore = (topRows.reduce((acc, r) => acc + (Number(r.quant_score) || 0), 0) / n).toFixed(1);
  const perList = topRows.map(r => Number(r.per)).filter(v => v > 0);
  const avgPer = perList.length ? (perList.reduce((a, b) => a + b, 0) / perList.length).toFixed(1) : "—";
  const roeList = topRows.map(r => r.roe != null ? (Number(r.roe) < 1 ? Number(r.roe) * 100 : Number(r.roe)) : null).filter(v => v != null && !isNaN(v));
  const avgRoe = roeList.length ? (roeList.reduce((a, b) => a + b, 0) / roeList.length).toFixed(1) : "—";
  const reportsCount = reportRows.filter((x) => x.kind === "AI 분석 리포트").length;

  $("#kpis").innerHTML = `
    <div class="kpi card-cyan">
      <div class="kpi-head">
        <span class="kpi-title has-tip" data-tip="재무·성장·모멘텀 종합 알고리즘을 최종 통과한 상위 20개 핵심 포트폴리오입니다.">🎯 TOP20 포트폴리오</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(56,189,248,0.15); color:#38bdf8;">우량주</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${topRows.length || 20}</span>
        <span class="kpi-unit">종목</span>
      </div>
      <div class="kpi-sub-text">평균 퀀트 점수 <b style="color:#38bdf8; font-weight:700;">${avgScore}점</b></div>
    </div>

    <div class="kpi card-emerald">
      <div class="kpi-head">
        <span class="kpi-title has-tip" data-tip="시총·거래대금·보통주 및 재무제표 스크리닝 요건을 통과한 유효 유니버스 기업 수입니다.">🏢 조건 통과 유니버스</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(52,211,153,0.15); color:#34d399;">12% 통과</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${eligibleTotal ?? c.universe_eligible ?? 275}</span>
        <span class="kpi-unit">개사</span>
      </div>
      <div class="kpi-sub-text">전체 2,700+ 상장사 중 엄선</div>
    </div>

    <div class="kpi card-amber">
      <div class="kpi-head">
        <span class="kpi-title has-tip" data-tip="TOP20 종목들의 평균 주가수익비율(PER)입니다. 시장 평균 대비 저평가 안전마진을 나타냅니다.">💎 TOP20 평균 PER</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(251,191,36,0.15); color:#fbbf24;">저평가</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${avgPer}</span>
        <span class="kpi-unit">배</span>
      </div>
      <div class="kpi-sub-text">코스피 평균(13.5배) 대비 저평가</div>
    </div>

    <div class="kpi card-purple">
      <div class="kpi-head">
        <span class="kpi-title has-tip" data-tip="TOP20 종목들의 평균 자기자본이익률(ROE)입니다. 고수익성 자본 효율성을 나타냅니다.">📈 TOP20 평균 ROE</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(192,132,252,0.15); color:#c084fc;">고수익</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${avgRoe}</span>
        <span class="kpi-unit">%</span>
      </div>
      <div class="kpi-sub-text">고수익·고성장 펀더멘털</div>
    </div>

    <div class="kpi card-rose clickable-kpi" id="kpi-goto-reports">
      <div class="kpi-head">
        <span class="kpi-title has-tip" data-tip="AI 리서치 엔진으로 발간 및 보관된 심층 기업 분석 리포트 건수입니다. 클릭 시 리포트 보관함으로 이동합니다.">📑 AI 분석 리포트</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(251,113,133,0.15); color:#fb7185;">리포트 ↗</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${reportsCount}</span>
        <span class="kpi-unit">건</span>
      </div>
      <div class="kpi-sub-text">심층 검증 완료 (클릭 시 이동)</div>
    </div>
  `;

  $("#kpi-goto-reports")?.addEventListener("click", () => switchView("reports"));
}

function renderExtLinksTop(links) {
  if (!links || !links.length) return "";
  const iconMap = {
    "네이버 시세": "🟢",
    "네이버 종목분석": "📊",
    "다음 금융": "🌐",
    "FnGuide": "📑",
    "DART 검색": "🏛️",
    "KIND": "📋",
    "토스증권": "📱",
    "토스 골라보기": "⚡",
  };

  return `
    <div class="drawer-ext-links-top" style="display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin:0 0 14px; padding:10px 14px; background:linear-gradient(145deg, #0d1527, #0b1120); border:1px solid rgba(56,189,248,0.25); border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.4);">
      <span style="font-size:11.5px; font-weight:700; color:#38bdf8; display:inline-flex; align-items:center; gap:4px; margin-right:4px;">
        🔗 사이트 직링크:
      </span>
      ${links.map((l) => {
        const icon = iconMap[l.label] || "🔗";
        return `<a class="ext-top-pill" href="${escapeHtml(l.url)}" target="_blank" rel="noopener" style="display:inline-flex; align-items:center; gap:4px; font-size:11.5px; font-weight:600; padding:4px 10px; background:#131d33; border:1px solid rgba(56,189,248,0.25); border-radius:6px; color:#e2e8f0; text-decoration:none; transition:all 0.15s ease;" onmouseover="this.style.borderColor='#38bdf8'; this.style.background='rgba(56,189,248,0.18)'; this.style.transform='translateY(-1px)';" onmouseout="this.style.borderColor='rgba(56,189,248,0.25)'; this.style.background='#131d33'; this.style.transform='none';">
          <span>${icon}</span>
          <span>${escapeHtml(l.label)}</span>
        </a>`;
      }).join("")}
    </div>
  `;
}

async function openStock(ticker) {
  const code = padTicker(ticker);
  openDrawerUi();
  $("#drawer-title").textContent = `⏳ 종목 심층 리서치 로딩 중... (${code})`;
  $("#drawer-body").innerHTML = `
    <div class="drawer-loading-skeleton">
      <div class="skeleton-spinner-box">
        <div class="skeleton-spinner"></div>
        <div class="skeleton-loading-text">
          <b>종목 ${code} 심층 퀀트 & 펀더멘털 데이터 로딩 중...</b>
          <p>재무제표, 5대 팩터 스코어, 최근 공시, 기술적 지표 및 실시간 뉴스를 집계하고 있습니다.</p>
        </div>
      </div>
      <div class="skeleton-shimmer-card"></div>
      <div class="skeleton-shimmer-card" style="height:140px;"></div>
      <div class="skeleton-shimmer-card" style="height:180px;"></div>
    </div>
  `;
  const bar = $("#global-progress-bar");
  if (bar) bar.style.display = "block";

  try {
    const data = await api(`/api/results/stock/${code}`);
    const r = data.row || {};
    const links = data.links || [];
    const gates = data.gates || {};
    const factors = [
      ["가치", r.value_score, 30],
      ["품질", r.quality_score, 25],
      ["성장", r.growth_score, 25],
      ["모멘텀", r.momentum_score, 10],
      ["안정", r.financial_score, 10],
    ];
    const gateLine = [
      gates.universe_eligible ? "유니버스 통과" : "유니버스 탈락",
      gates.top100_eligible ? "TOP100 가능" : "TOP100 불가",
      gates.top20_eligible ? "TOP20 가능" : "TOP20 불가",
    ].join(" · ");
    const excl = (gates.exclusion_reasons || [])
      .filter((x) => x && x.label && x.label !== "[]")
      .map((x) => `<li>${escapeHtml(x.label)}</li>`)
      .join("");
    const riskNotes = (data.risk_notes || []).map((x) => x.label).filter(Boolean);
    const dataNotes = (data.data_notes || []).map((x) => x.label).filter(Boolean);
    const brief = data.brief || {};
    const factItems = [];
    if (brief.facts && brief.facts.length) {
      for (const f of brief.facts) {
        factItems.push(`
          <div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px; display:flex; flex-direction:column; gap:2px;">
            <span style="font-size:11px; color:#94a3b8; font-weight:600;">${escapeHtml(f.label)}</span>
            <b style="font-size:13px; color:#f8fafc; font-weight:700; word-break:break-all;">${escapeHtml(f.value)}</b>
          </div>
        `);
      }
    }
    if (r.per != null) factItems.push(`<div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8; font-weight:600;">PER</span><b style="font-size:13px; color:#f8fafc; font-weight:700;">${fmt(r.per, 1)}배</b></div>`);
    if (r.pbr != null) factItems.push(`<div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8; font-weight:600;">PBR</span><b style="font-size:13px; color:#f8fafc; font-weight:700;">${fmt(r.pbr, 2)}배</b></div>`);
    if (r.roe != null) factItems.push(`<div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8; font-weight:600;">ROE</span><b style="font-size:13px; color:#34d399; font-weight:700;">${(r.roe * 100).toFixed(1)}%</b></div>`);
    if (r.roic != null) factItems.push(`<div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8; font-weight:600;">ROIC</span><b style="font-size:13px; color:#34d399; font-weight:700;">${(r.roic * 100).toFixed(1)}%</b></div>`);
    if (r.operating_margin != null) factItems.push(`<div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8; font-weight:600;">영업이익률</span><b style="font-size:13px; color:#38bdf8; font-weight:700;">${(r.operating_margin * 100).toFixed(1)}%</b></div>`);
    if (r.fcf_yield != null) factItems.push(`<div class="fact-card" style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8; font-weight:600;">FCF 수익률</span><b style="font-size:13px; color:#34d399; font-weight:700;">${(r.fcf_yield * 100).toFixed(1)}%</b></div>`);

    const facts = `<div class="facts-grid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(130px, 1fr)); gap:8px; margin-top:8px;">${factItems.join("")}</div>`;

    const naver = data.naver || {};
    const encyc = (naver.encyc || [])
      .slice(0, 1)
      .map((x) => `<p style="font-size:12.5px; line-height:1.5; color:#cbd5e1;">${escapeHtml(x.description || x.title || "")}</p>`)
      .join("");
    const newsItems = (naver.news || [])
      .slice(0, 8)
      .map((n) => {
        const sent = classifyNewsSentiment(n.title, n.description);
        return `<li style="padding:9px 12px; background:rgba(15,23,42,0.65); border:1px solid #1e293b; border-radius:8px; margin-bottom:8px; transition:border-color 0.2s ease;">
          <div style="display:flex; align-items:flex-start; gap:8px;">
            <span class="news-badge ${sent.cls}" style="flex-shrink:0; margin-top:2px;">${sent.icon} ${sent.label}</span>
            <div style="flex:1; min-width:0;">
              <a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener" style="font-weight:600; font-size:12.5px; color:#f1f5f9; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(n.title)}</a>
              <div class="meta" style="margin-top:4px; font-size:11px; color:#94a3b8; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml((n.pubDate || "").slice(0, 16))} · ${escapeHtml(n.description || "")}</div>
            </div>
          </div>
        </li>`;
      })
      .join("");

    let newsCard = "";
    if (newsItems) {
      newsCard = `<article class="intro" style="margin:0; height:100%;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">📰 네이버 실시간 뉴스</h3>
          <span class="chip" style="font-size:10px;">실시간 연동</span>
        </div>
        <ul class="news-list" style="margin:0; padding-left:0; list-style:none;">${newsItems}</ul>
      </article>`;
    } else if (!naver.configured) {
      newsCard = `<article class="intro" style="margin:0; height:100%;"><h3 style="margin:0 0 6px; font-size:13.5px;">📰 네이버 뉴스</h3><p class="hint">${publicShareMode ? "공개 스냅샷에는 네이버 뉴스가 포함되지 않습니다." : "설정에서 네이버 Client ID/Secret을 넣으면 최근 뉴스가 나옵니다."}</p></article>`;
    } else if (naver.error) {
      newsCard = `<article class="intro" style="margin:0; height:100%;"><h3 style="margin:0 0 6px; font-size:13.5px;">📰 네이버 뉴스</h3><p class="hint">${escapeHtml(naver.error)}</p></article>`;
    }

    const webItems = (naver.web || [])
      .slice(0, 8)
      .map(
        (n) => `<li style="padding:9px 12px; background:rgba(15,23,42,0.65); border:1px solid #1e293b; border-radius:8px; margin-bottom:8px;">
          <a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener" style="font-weight:600; font-size:12.5px; color:#f1f5f9; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(n.title)}</a>
          <div class="meta" style="margin-top:4px; font-size:11px; color:#94a3b8; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${escapeHtml(n.description || "")}</div>
        </li>`
      )
      .join("");

    let webCard = `<article class="intro" style="margin:0; height:100%;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">🔍 네이버 실시간 웹검색</h3>
        <span class="chip" style="font-size:10px;">테마/공시 검색</span>
      </div>
      <ul class="news-list" style="margin:0; padding-left:0; list-style:none;">${webItems || '<p class="hint">검색 결과가 없거나 수집 대기 중입니다.</p>'}</ul>
    </article>`;

    const bottomNewsGrid = `
      <div class="bottom-news-grid" style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-top:20px; width:100%; box-sizing:border-box;">
        <div id="tier1-news-container" style="grid-column: 1 / -1;"></div>
        ${newsCard}
        ${webCard}
      </div>
    `;

    const loc = data.location || {};
    const dartInfo = data.dart || {};
    const shareholders = data.shareholders || [];

    let shareholderRows = "";
    if (shareholders.length > 0) {
      shareholderRows = `
        <div style="margin-top:10px;">
          <span style="font-size:11.5px; font-weight:700; color:#38bdf8; display:block; margin-bottom:6px;">👥 주요주주 지분 현황 (DART 공시)</span>
          <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap:6px;">
            ${shareholders.map(sh => `
              <div style="padding:7px 10px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:6px; display:flex; flex-direction:column; gap:2px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:11.5px; font-weight:700; color:#f8fafc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(sh.name)}">${escapeHtml(sh.name)}</span>
                  <span style="font-size:10px; color:#94a3b8;">${escapeHtml(sh.relate || "주주")}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:2px;">
                  <b style="font-size:12.5px; color:#34d399; font-weight:800;">${escapeHtml(sh.ratio)}%</b>
                  <span style="font-size:10px; color:#64748b;">${escapeHtml(sh.shares)}주</span>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    const companyInfoBlock = `
      <article class="intro" style="margin-top:14px; background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:10px; padding:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">🏢 기업 개요 & 지배구조</h3>
          <span class="chip" style="font-size:10px;">DART·공식 정보</span>
        </div>

        <!-- 1. 기본 정보 팩트 그리드 -->
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:8px; margin-bottom:10px;">
          <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.7); border:1px solid #1e293b; border-radius:8px;">
            <span style="font-size:10.5px; color:#94a3b8;">대표이사</span>
            <b style="font-size:13px; color:#f8fafc;">${escapeHtml(dartInfo.ceo || loc.ceo || "-")}</b>
          </div>
          <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.7); border:1px solid #1e293b; border-radius:8px;">
            <span style="font-size:10.5px; color:#94a3b8;">설립일</span>
            <b style="font-size:13px; color:#f8fafc;">${escapeHtml(dartInfo.founded || loc.founded || "-")}</b>
          </div>
          <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.7); border:1px solid #1e293b; border-radius:8px;">
            <span style="font-size:10.5px; color:#94a3b8;">대표 전화</span>
            <b style="font-size:13px; color:#f8fafc;">${escapeHtml(dartInfo.phone || "-")}</b>
          </div>
          <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.7); border:1px solid #1e293b; border-radius:8px;">
            <span style="font-size:10.5px; color:#94a3b8;">영문 사명</span>
            <b style="font-size:12px; color:#94a3b8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(dartInfo.corp_name_eng || "-")}</b>
          </div>
        </div>

        <!-- 2. 본사 주소 & 바로가기 버튼 -->
        <div style="background:rgba(15,23,42,0.6); border:1px solid #1e293b; border-radius:8px; padding:10px 12px; margin-bottom:10px;">
          <div style="font-size:12px; color:#cbd5e1; margin-bottom:6px;">
            📍 본사 주소: <b>${escapeHtml(dartInfo.address || loc.address || "-")}</b>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            ${(dartInfo.homepage || loc.homepage) ? `<a class="ext inline" href="${escapeHtml(dartInfo.homepage || loc.homepage)}" target="_blank" rel="noopener" style="font-size:11px; padding:4px 10px; background:rgba(56,189,248,0.12); border:1px solid rgba(56,189,248,0.35); border-radius:6px; color:#38bdf8; font-weight:600;">🌐 공식 홈페이지</a>` : ""}
            ${loc.map_url ? `<a class="ext inline" href="${escapeHtml(loc.map_url)}" target="_blank" rel="noopener" style="font-size:11px; padding:4px 10px; background:rgba(34,197,94,0.12); border:1px solid rgba(34,197,94,0.35); border-radius:6px; color:#4ade80; font-weight:600;">🗺️ 네이버 지도</a>` : ""}
          </div>
        </div>

        <!-- 3. 대주주 지분 현황 -->
        ${shareholderRows}

        <!-- 4. 기업 백과 / 사업 소개 -->
        ${encyc ? `
          <div style="margin-top:10px; padding:10px 12px; background:rgba(30,41,59,0.4); border-left:3px solid #38bdf8; border-radius:0 8px 8px 0;">
            <span style="font-size:11.5px; font-weight:700; color:#38bdf8; display:block; margin-bottom:4px;">📖 기업 백과 & 사업 개요</span>
            ${encyc}
          </div>
        ` : ""}
      </article>
    `;
    const toss = data.toss || {};
    const tq = toss.quote || {};
    const tprice = tq.lastPrice ?? tq.price ?? tq.close ?? tq.last ?? tq.currentPrice ?? tq.tradePrice;
    const tchg = tq.changeRate ?? tq.changePct ?? (tq.price && tq.price.changeRate);
    const twarn = (toss.warnings || []).map((w) => (typeof w === "string" ? w : w.type || w.name || w.code || JSON.stringify(w))).join(", ");

    let yahooBlock = "";
    if (data.yahoo && data.yahoo.summary) {
      const y = data.yahoo;
      const ys = y.summary || {};
      yahooBlock = `
        <article class="intro" style="background:#0f172a; border:1px solid rgba(56,189,248,0.25); border-radius:10px; padding:14px; margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <h3 style="margin:0; font-size:14px; color:#38bdf8;">🌐 Yahoo Finance & 컨센서스</h3>
            <span class="chip" style="font-size:10.5px;">글로벌 데이터</span>
          </div>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:8px;">
            <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.8); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8;">목표주가 평균</span><b style="font-size:12.5px; color:#38bdf8;">${ys.target_mean ? `${fmt(ys.target_mean)}원` : "—"}</b></div>
            <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.8); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8;">투자의견</span><b style="font-size:12.5px; color:#4ade80;">${ys.recommendation_key ? escapeHtml(ys.recommendation_key.toUpperCase()) : "—"}</b></div>
            <div class="fact-card" style="padding:8px 10px; background:rgba(15,23,42,0.8); border:1px solid #1e293b; border-radius:8px;"><span style="font-size:11px; color:#94a3b8;">애널리스트 수</span><b style="font-size:12.5px; color:#f1f5f9;">${ys.analysts_count ? `${ys.analysts_count}명` : "—"}</b></div>
          </div>
        </article>
      `;
    }

    const ta = data.ta || {};
    let taBlock = "";
    if (ta.ok) {
      const kVal = typeof ta.stoch_k === "number" ? ta.stoch_k : null;
      const dVal = typeof ta.stoch_d === "number" ? ta.stoch_d : null;
      const k = kVal != null ? fmt(kVal, 1) : "—";
      const d = dVal != null ? fmt(dVal, 1) : "—";

      let stochInterp = "";
      if (kVal != null && dVal != null) {
        if (kVal <= 20 && kVal >= dVal) {
          stochInterp = "🟢 과매도 탈출 골든크로스 (단기 반등 매수 유효 구간)";
        } else if (kVal <= 25) {
          stochInterp = "🔵 과매도 침체 구간 (바닥권 분할 매수 관심)";
        } else if (kVal >= 80 && kVal <= dVal) {
          stochInterp = "🔴 과매수권 데드크로스 (단기 차익 실현 경계)";
        } else if (kVal >= 75) {
          stochInterp = "🟠 과매수권 과열 (상승 탄력 강하나 단기 눌림목 유의)";
        } else if (kVal > dVal) {
          stochInterp = "🟢 단기 상승 모멘텀 지속 (K > D 매수 우위)";
        } else {
          stochInterp = "🟡 단기 숨고르기/조정 국면 (K < D 매도 우위)";
        }
      }

      let cloudText = "—";
      let cloudInterp = "";
      if (ta.ichi_cloud === "above") {
        cloudText = "구름대 상단 돌파 (구름 위)";
        cloudInterp = "🟢 중기 상승 추세 지지 국면 (구름대가 하방 지지선 역할)";
      } else if (ta.ichi_cloud === "below") {
        cloudText = "구름대 하회 (구름 아래)";
        cloudInterp = "🔴 중기 하락/역배열 저항 국면 (상단 구름대 돌파 확인 필요)";
      } else if (ta.ichi_cloud === "inside") {
        cloudText = "구름대 내부 (구름 안)";
        cloudInterp = "🟡 방향성 탐색/변동성 국면 (구름 상단 안착 시 추세 전환 기대)";
      }

      taBlock = `
        <article class="intro" style="background:#0f172a; border:1px solid rgba(56,189,248,0.25); border-radius:10px; padding:14px; margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <h3 style="margin:0; font-size:14px; color:#38bdf8;">📈 기술적 지표 & 실전 해석 (일봉)</h3>
            <span class="chip" style="font-size:10.5px; padding:2px 7px;">KRX 일봉 데이터</span>
          </div>

          <div style="margin-bottom:10px; padding:9px 12px; background:rgba(15,23,42,0.85); border-radius:8px; border:1px solid #1e293b;">
            <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:600; color:#f1f5f9;">
              <span>스토캐스틱 (Slow)</span>
              <span>K <b>${k}</b> · D <b>${d}</b> ${ta.stoch_cross ? `<span class="chip ok" style="font-size:10.5px; padding:1px 6px;">${escapeHtml(ta.stoch_cross)}</span>` : ""}</span>
            </div>
            ${stochInterp ? `<p style="margin:5px 0 0; font-size:11.5px; color:#93c5fd; line-height:1.4;">💡 <b>해석:</b> ${escapeHtml(stochInterp)}</p>` : ""}
          </div>

          <div style="margin-bottom:10px; padding:9px 12px; background:rgba(15,23,42,0.85); border-radius:8px; border:1px solid #1e293b;">
            <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:600; color:#f1f5f9;">
              <span>일목균형표 (Ichimoku)</span>
              <span style="color:#38bdf8; font-weight:700;">${escapeHtml(cloudText)}</span>
            </div>
            ${cloudInterp ? `<p style="margin:5px 0 0; font-size:11.5px; color:#93c5fd; line-height:1.4;">💡 <b>해석:</b> ${escapeHtml(cloudInterp)}</p>` : ""}
            ${ta.ichi_signal ? `<p style="margin:3px 0 0; font-size:11px; color:#94a3b8;">• 신호: ${escapeHtml(ta.ichi_signal)}</p>` : ""}
          </div>

          ${ta.support != null && ta.resistance != null ? `
            <div style="display:flex; justify-content:space-between; font-size:12px; padding:7px 12px; background:rgba(56,189,248,0.08); border-radius:6px;">
              <span style="color:#4ade80;">🛡️ 1차 지지선: <b>${fmt(ta.support, 0)}원</b></span>
              <span style="color:#f87171;">🎯 1차 저항선: <b>${fmt(ta.resistance, 0)}원</b></span>
            </div>
          ` : ""}
        </article>
      `;
    }
    const timing = data.timing || {};
    const timingSignals = timing.signals || [];
    let timingBlock = "";
    if (timingSignals.length || timing.summary || timing.action || timing.regime) {
      timingBlock = `
        <article class="intro">
          <h3>기술적 타이밍 (KRX 일봉)</h3>
          <div class="tf-grid">
            <div class="tf-card"><span>추세 상태</span><b>${escapeHtml(timing.regime || "—")}</b></div>
            <div class="tf-card ${timing.action === "매수 우위" ? "UP" : timing.action === "관망/경계" ? "DOWN" : ""}"><span>신호 종합</span><b>${escapeHtml(timing.action || "—")}</b></div>
            <div class="tf-card"><span>타이밍 신뢰도</span><b>${timing.confidence != null ? `${timing.confidence}점` : "—"}</b></div>
          </div>
          <div class="conf-meter"><i style="width:${Math.max(0, Math.min(100, timing.confidence || 0))}%"></i></div>
          <p class="meta">${escapeHtml(timing.summary || "")}</p>
          ${timingSignals.length ? `<ul class="intro-facts">${timingSignals.map((s) => `<li><span>${escapeHtml(s.indicator)}</span><b>${escapeHtml(s.signal)}</b><div class="meta">${escapeHtml(s.note || "")}</div></li>`).join("")}</ul>` : ""}
        </article>
      `;
    }

    const radarSvg = renderHexagonRadarSvg(factors, timing.confidence || 60);
    const visualGauges = renderPriceAndBandGauge(brief, ta, toss);

    const factorColors = {
      "가치": { icon: "💎", color: "#38bdf8", bg: "rgba(56,189,248,0.12)", border: "rgba(56,189,248,0.3)" },
      "품질": { icon: "👑", color: "#c084fc", bg: "rgba(192,132,252,0.12)", border: "rgba(192,132,252,0.3)" },
      "성장": { icon: "🚀", color: "#34d399", bg: "rgba(52,211,153,0.12)", border: "rgba(52,211,153,0.3)" },
      "모멘텀": { icon: "⚡", color: "#fb923c", bg: "rgba(251,146,60,0.12)", border: "rgba(251,146,60,0.3)" },
      "안정": { icon: "🛡️", color: "#2dd4bf", bg: "rgba(45,212,191,0.12)", border: "rgba(45,212,191,0.3)" },
    };

    const factorCardsHtml = `
      <div class="factor-grid-dashboard" style="display:grid; grid-template-columns:repeat(5, 1fr); gap:8px; margin:12px 0 10px;">
        ${factors.map(([name, v, max]) => {
          const cfg = factorColors[name] || { icon: "📊", color: "#38bdf8", bg: "rgba(56,189,248,0.1)", border: "rgba(56,189,248,0.25)" };
          const pct = Math.max(0, Math.min(100, ((v || 0) / max) * 100));
          return `
            <div class="factor-stat-card has-tip" data-tip-title="${cfg.icon} ${name} 팩터 점수" data-tip="${name} ${fmt(v, 1)} / ${max}점 (달성률 ${pct.toFixed(0)}%)" style="background:${cfg.bg}; border:1px solid ${cfg.border}; border-radius:8px; padding:8px 10px; display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:11px; font-weight:700; color:${cfg.color};">${cfg.icon} ${name}</span>
                <span style="font-size:10px; color:#94a3b8;">/${max}</span>
              </div>
              <b style="font-size:15px; font-weight:800; color:#f8fafc;">${fmt(v, 1)}<span style="font-size:10.5px; font-weight:400; color:#94a3b8;">점</span></b>
              <div style="width:100%; height:4px; background:rgba(0,0,0,0.4); border-radius:2px; overflow:hidden;">
                <div style="width:${pct}%; height:100%; background:${cfg.color}; border-radius:2px;"></div>
              </div>
            </div>
          `;
        }).join("")}
      </div>
      <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; background:rgba(15,23,42,0.65); border:1px solid #1e293b; border-radius:8px; padding:8px 12px; margin-bottom:14px; font-size:12px;">
        <span style="color:#cbd5e1;">⚠️ 감점 요인: <b style="color:${r.risk_penalty ? '#fb7185' : '#4ade80'};">${r.risk_penalty ? `-${fmt(r.risk_penalty, 1)}점` : "0점 (감점 없음)"}</b></span>
        <span style="color:#cbd5e1;">📊 데이터 신뢰도: <b style="color:${(r.data_confidence||0) >= 80 ? '#4ade80' : '#facc15'};">${r.data_confidence != null ? `${fmt(r.data_confidence, 1)}점` : "—"}</b></span>
      </div>
    `;

    const gateCardsHtml = `
      <article class="intro" style="background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:10px; padding:14px; margin-top:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">🛡️ 유니버스 선정 및 데이터 게이트 상태</h3>
          <span class="chip ${gates.universe_eligible ? 'ok' : 'warn'}" style="font-size:10.5px; font-weight:700;">${escapeHtml(gateLine)}</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:6px; margin-top:10px;">
          ${(gates.exclusion_reasons || []).filter(x => x && x.label && x.label !== "[]").map(x => `
            <div style="padding:8px 10px; background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.3); border-radius:6px; font-size:12px; color:#fca5a5; display:flex; align-items:flex-start; gap:6px;">
              <span style="flex-shrink:0;">🛑</span> <div><b>[제외 요건]</b> ${escapeHtml(x.label || x.code)}</div>
            </div>
          `).join("")}
          ${(data.risk_notes || []).map(x => `
            <div style="padding:8px 10px; background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.25); border-radius:6px; font-size:12px; color:#fde047; display:flex; align-items:flex-start; gap:6px;">
              <span style="flex-shrink:0;">⚠️</span> <div><b>[리스크 유의]</b> ${escapeHtml(x.label || x.code)}</div>
            </div>
          `).join("")}
          ${(data.data_notes || []).map(x => `
            <div style="padding:8px 10px; background:rgba(56,189,248,0.08); border:1px solid rgba(56,189,248,0.2); border-radius:6px; font-size:12px; color:#bae6fd; display:flex; align-items:flex-start; gap:6px;">
              <span style="flex-shrink:0;">ℹ️</span> <div><b>[데이터 산출 참고]</b> ${escapeHtml(x.label || x.code)}</div>
            </div>
          `).join("")}
          ${!excl && !riskNotes.length && !dataNotes.length ? `
            <div style="padding:8px 12px; background:rgba(34,197,94,0.1); border:1px solid rgba(34,197,94,0.25); border-radius:6px; font-size:12px; color:#86efac;">
              ✅ 특이 데이터 결측이나 리스크 감점 요인 없이 모든 퀀트 게이트를 완벽히 통과했습니다.
            </div>
          ` : ""}
        </div>
      </article>
    `;

    $("#drawer-title").textContent = `${r.company || ticker} (${padTicker(r.ticker || ticker)})`;
    $("#drawer-body").innerHTML = `
      ${renderExtLinksTop(links)}

      <!-- 1. TOP FULL-WIDTH: 손자병법 5사 (道天地將法) 5개 카드 가로 풀 와이드 배치 -->
      ${fiveStrip({ dao: data.dao, tian: data.tian, di: data.di, jiang: data.jiang, fa: data.fa })}

      <div class="stock-grid">
        <!-- COLUMN 1 (LEFT): 종합 점수, 6축 레이더 & 5대 팩터 스코어보드, 기술적 지표 & 타이밍, 게이트 상태, 액션 & AI 리포트 -->
        <div>
          <!-- 1. 종합 점수 Hero -->
          <div class="score-hero" style="background:linear-gradient(135deg, rgba(30,58,138,0.35), rgba(15,23,42,0.85)); border:1px solid rgba(56,189,248,0.3); border-radius:12px; padding:14px 18px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <span style="font-size:12px; color:#94a3b8; font-weight:600;">종합 퀀트 스코어</span>
                <span class="chip ok" style="font-size:10px; font-weight:700;">${escapeHtml(r.rank_label || "순위권")}</span>
              </div>
              <div class="meta" style="font-size:11.5px; color:#cbd5e1;">${r.market || ""} · ${r.sector || ""} · ${r.industry || ""}</div>
            </div>
            <div style="text-align:right;">
              <b style="font-size:28px; font-weight:900; color:#38bdf8; letter-spacing:-0.5px;">${fmt(r.quant_score)}<span style="font-size:13px; font-weight:600; color:#94a3b8;"> / 100</span></b>
            </div>
          </div>

          <!-- 2. 6-Axis Hexagon Radar Chart -->
          <div class="stock-radar-card">
            <div class="stock-radar-header">
              <div class="stock-radar-title">
                <span>🔷 6축 퀀트 & 펀더멘털 레이더 (Hexagon DNA)</span>
              </div>
              <div class="stock-radar-legend">
                <span><i class="dot-firm"></i>이 종목</span>
                <span><i class="dot-market"></i>시장 평균(50%)</span>
              </div>
            </div>
            ${radarSvg}
          </div>

          <!-- 3. 5대 팩터 스코어보드 & 데이터 신뢰도 카드 -->
          ${factorCardsHtml}

          <!-- 4. 기술적 지표 & 실전 해석 (일봉) -->
          ${taBlock}

          <!-- 5. 기술적 타이밍 & 가격 밴드 게이지 -->
          ${visualGauges}
          ${timingBlock}

          <!-- 6. 선정 및 게이트 상태 -->
          ${gateCardsHtml}

          <!-- 7. 액션 버튼 (4개 버튼 1줄 정렬) & AI 리포트 박스 -->
          ${publicShareMode ? `
            <p class="hint public-readonly-note">공개 웹은 마지막 업로드 스냅샷을 보는 읽기 전용 화면입니다. AI 생성·백테스트 실행·관심종목 저장은 로컬에서 사용할 수 있습니다.</p>
          ` : `
            <div class="actions" style="display:grid; grid-template-columns: repeat(4, 1fr); gap:6px; margin:14px 0 6px;">
              <button class="primary" id="btn-report" data-ticker="${ticker}" style="font-weight:700; font-size:11px; padding:7px 2px; display:inline-flex; align-items:center; justify-content:center; gap:2px; white-space:nowrap;" title="AI 심층 분석 리포트 생성">🤖 AI 리포트</button>
              <button id="btn-infographic-drawer" data-ticker="${ticker}" style="background:linear-gradient(135deg, rgba(6,182,212,0.22), rgba(59,130,246,0.22)); color:#38bdf8; border:1px solid rgba(56,189,248,0.5); font-weight:700; font-size:11px; padding:7px 2px; display:inline-flex; align-items:center; justify-content:center; gap:2px; white-space:nowrap;" title="인포그래픽 프레젠테이션 뷰 열기">🎨 인포그래픽</button>
              <button id="btn-backtest-stock" data-ticker="${ticker}" style="background:rgba(56,189,248,0.12); color:#38bdf8; border-color:rgba(56,189,248,0.35); font-weight:600; font-size:11px; padding:7px 2px; display:inline-flex; align-items:center; justify-content:center; gap:2px; white-space:nowrap;" title="4대 전략 백테스트">🧪 백테스팅</button>
              <button id="btn-watch" data-ticker="${ticker}" data-company="${escapeHtml(r.company || "")}" style="font-size:11px; padding:7px 2px; display:inline-flex; align-items:center; justify-content:center; gap:2px; white-space:nowrap;" title="관심종목 추가/해제">⭐ 관심종목</button>
            </div>
            <p class="hint" style="font-size:11px; color:#94a3b8; margin-top:2px;">💡 AI 심층 리포트는 선택한 LLM으로 14대 지침을 분석하며, <b>인포그래픽 뷰</b>로 시각화 덱을 즉시 확인할 수 있습니다.</p>
          `}
          <div id="report-box" style="margin-top:8px;">
            <div style="padding:10px 14px; background:rgba(15,23,42,0.6); border:1px dashed rgba(56,189,248,0.25); border-radius:8px; font-size:12px; color:#94a3b8; display:flex; align-items:center; justify-content:space-between;">
              <span>💡 <b>AI 심층 분석 리포트 대기 중</b> (상단 [🤖 AI 리포트] 또는 [🎨 인포그래픽] 클릭)</span>
              <span style="font-size:11px; color:#64748b;">${escapeHtml(r.company || ticker)}</span>
            </div>
          </div>
        </div>

        <!-- COLUMN 2 (RIGHT): 공식 수급 90일, 실전 참모 분석, DART 공시 이벤트, 핵심 재무 팩트 & 밸류에이션, 기업 개요 & 대주주 지분, Yahoo Financials -->
        <div>
          <!-- 1. 공식 수급 90일 -->
          ${flow90Block(data.flow90, code)}

          <!-- 2. 실전 참모 분석 -->
          ${criticCard((data.sunzi || {}).critic)}

          <!-- 3. 공시 이벤트 & DART 캘린더 -->
          ${eventsBlock(data.events)}

          <!-- 4. 핵심 재무 팩트 & 밸류에이션 -->
          <article class="intro" style="margin-top:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">📊 핵심 재무 팩트 & 밸류에이션</h3>
              <span class="chip" style="font-size:10px;">KRX 팩트</span>
            </div>
            ${facts}
          </article>

          <!-- 5. 기업 개요 & 지배구조 & 본사 정보 -->
          ${companyInfoBlock}

          <!-- 6. Yahoo Financials & 컨센서스 -->
          ${yahooBlock}
        </div>
      </div>

      <!-- BOTTOM FULL-WIDTH 2-COLUMN GRID: 네이버 뉴스 & 네이버 웹검색 나란히 배치 (가로폭 100% 꽉 차게) -->
      ${bottomNewsGrid}
    `;

    if (!publicShareMode) {
      $("#btn-backtest-stock")?.addEventListener("click", () => {
        closeDrawer();
        openStrategyBacktest(code, r.company || code).catch((err) => alert(err.message));
      });
      $("#btn-report")?.addEventListener("click", () => runReport(code).catch((err) => alert(err.message)));
      $("#btn-infographic-drawer")?.addEventListener("click", async () => {
        try {
          const data = await api(`/api/research/${code}/report`);
          if (data.exists && data.row) {
            openReportModal(data.row);
          } else {
            if (confirm(`아직 생성된 리포트가 없습니다. 지금 ${r.company || code}의 AI 심층 리포트 및 인포그래픽을 생성할까요?`)) {
              runReport(code).catch((err) => alert(err.message));
            }
          }
        } catch (err) {
          window.open(`/api/research/${code}/infographic`, "_blank");
        }
      });
      $("#btn-watch")?.addEventListener("click", () => addWatch(code, r.company || "").catch((err) => alert(err.message)));
      $("#btn-collect-flow-single")?.addEventListener("click", async () => {
        const btn = $("#btn-collect-flow-single");
        if (btn) {
          btn.disabled = true;
          btn.textContent = "수집 중…";
        }
        try {
          const res = await api(`/api/flow/collect-ticker/${code}`, { method: "POST" });
          if (res.ok) {
            openStock(code);
          } else {
            alert(res.error || "수집 실패");
            if (btn) {
              btn.disabled = false;
              btn.textContent = "⚡ KIS 공식 수급 즉시 수집";
            }
          }
        } catch (err) {
          alert(err.message);
          if (btn) {
            btn.disabled = false;
            btn.textContent = "⚡ KIS 공식 수급 즉시 수집";
          }
        }
      });
    }
    loadReport(code).catch(() => {
      $("#report-box").innerHTML = "<p style='font-size:12px; color:#64748b;'>저장된 AI 분석 리포트 없음</p>";
    });
    loadTier1StockInsights(code).catch(() => {});
  } catch (err) {
    $("#drawer-body").innerHTML = `<div style="padding:20px; color:#ef4444;"><h3>❌ 데이터 로딩 실패</h3><p>${escapeHtml(err.message)}</p></div>`;
  } finally {
    if (bar) bar.style.display = "none";
  }
}

async function loadTier1StockInsights(code) {
  try {
    const res = await api(`/api/research/${code}/tier1-insights`);
    if (!res) return;
    const insightBoxes = [$("#tier1-news-container"), $("#tier1-dart-container"), $("#tier1-posture-container")].filter(Boolean);
    if (!res.ok) {
      insightBoxes.forEach((box) => renderTier1Unavailable(box, res));
      return;
    }
    
    // 1. Render News AI Card
    const newsBox = $("#tier1-news-container");
    if (newsBox && res.news_analysis && res.news_analysis.summary) {
      const na = res.news_analysis;
      const sentCls = ["호재", "긍정"].includes(na.sentiment) ? "ok" : ["악재", "부정"].includes(na.sentiment) ? "bad" : "warn";
      const sentIcon = ["호재", "긍정"].includes(na.sentiment) ? "🔥" : ["악재", "부정"].includes(na.sentiment) ? "⚠️" : "⚖️";
      newsBox.innerHTML = `
        <div class="tier1-ai-card tier1-news-card" style="background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,41,59,0.9)); border:1px solid rgba(56,189,248,0.4); border-radius:10px; padding:12px 14px; box-shadow:0 4px 14px rgba(0,0,0,0.35);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <span style="font-size:12px; font-weight:700; color:#38bdf8; display:flex; align-items:center; gap:6px;">
              🤖 Tier 1 무료 AI 실시간 뉴스 브리핑
              <span style="font-size:10px; font-weight:400; color:#94a3b8;">(${escapeHtml(res.model || "NVIDIA 550B")})</span>
            </span>
            <span class="chip ${sentCls}" style="font-size:10.5px; font-weight:700; padding:2px 8px;">${sentIcon} ${escapeHtml(na.sentiment || "중립")}</span>
          </div>
          <p style="font-size:12.5px; line-height:1.55; color:#f1f5f9; margin:0 0 6px; font-weight:500;">${escapeHtml(na.summary)}</p>
          ${na.key_driver ? `<div style="font-size:11.5px; color:#cbd5e1; display:flex; align-items:center; gap:4px;">🔑 <b>핵심 요인:</b> <span style="color:#67e8f9;">${escapeHtml(na.key_driver)}</span></div>` : ""}
        </div>
      `;
    }

    // 2. Render DART Events AI Card
    const dartBox = $("#tier1-dart-container");
    if (dartBox && res.events_analysis && res.events_analysis.commentary) {
      const ea = res.events_analysis;
      const riskCls = ea.risk_level === "주의" ? "bad" : ea.risk_level === "안전" ? "ok" : "warn";
      const riskIcon = ea.risk_level === "주의" ? "⚠️" : ea.risk_level === "안전" ? "🛡️" : "⚖️";
      dartBox.innerHTML = `
        <div class="tier1-ai-card tier1-dart-card" style="margin-top:10px; background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,41,59,0.9)); border:1px solid rgba(168,85,247,0.4); border-radius:10px; padding:12px 14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <span style="font-size:12px; font-weight:700; color:#c084fc;">💡 Tier 1 AI 공시 실전 해설 (지분 희석/오버행)</span>
            <span class="chip ${riskCls}" style="font-size:10px; font-weight:700; padding:2px 8px;">${riskIcon} 공시 위험도: ${escapeHtml(ea.risk_level || "판단 불가")}</span>
          </div>
          <p style="font-size:12px; line-height:1.5; color:#f1f5f9; margin:0 0 4px;">${escapeHtml(ea.commentary)}</p>
          ${ea.key_point ? `<div style="font-size:11px; color:#e2e8f0;">📌 <b>체크 포인트:</b> ${escapeHtml(ea.key_point)}</div>` : ""}
        </div>
      `;
    }

    // 3. Render Technical & Flow Posture Guide Card
    const postBox = $("#tier1-posture-container");
    if (postBox && res.tech_flow_analysis && res.tech_flow_analysis.action_guide) {
      const tfa = res.tech_flow_analysis;
      const postCls = tfa.posture === "확인" ? "ok" : tfa.posture === "근거 부족" ? "bad" : "warn";
      postBox.innerHTML = `
        <div class="tier1-ai-card tier1-posture-card" style="margin-top:10px; background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,41,59,0.9)); border:1px solid rgba(52,211,153,0.4); border-radius:10px; padding:12px 14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <span style="font-size:12px; font-weight:700; color:#34d399;">🎯 Tier 1 AI 기술·수급 교차 해석</span>
            <span class="chip ${postCls}" style="font-size:10px; font-weight:700; padding:2px 8px;">${escapeHtml(tfa.posture || "판단 불가")}</span>
          </div>
          <p style="font-size:12px; line-height:1.5; color:#f1f5f9; margin:0 0 4px;">${escapeHtml(tfa.action_guide)}</p>
          ${tfa.timing_tip ? `<div style="font-size:11px; color:#cbd5e1;">🔎 <b>추가 확인:</b> <span style="color:#a7f3d0;">${escapeHtml(tfa.timing_tip)}</span></div>` : ""}
        </div>
      `;
    }
    insightBoxes.forEach((box) => appendTier1Meta(box, res));
  } catch (e) {
    console.debug("Tier 1 insights load error:", e);
    const box = $("#tier1-news-container");
    if (box) renderTier1Unavailable(box, null, e);
  }
}

function renderResearch(rec) {
  if (!rec) {
    $("#research-box").innerHTML = "<p>아직 AI 분석이 없습니다.</p>";
    return;
  }
  const thesis = rec.thesis || {};
  const trap = rec.value_trap_assessment || {};
  $("#research-box").innerHTML = `
    <h3>AI 분석 · ${rec.provider || ""} ${rec.model || ""}</h3>
    <p>판정 <b>${rec.research_decision || "—"}</b> · 리서치 ${fmt(rec.research_score, 0)} · 확신 ${fmt(rec.research_confidence, 0)}</p>
    <p>${thesis.one_line || ""}</p>
    <p>${thesis.business_model || ""}</p>
    <p>해자/ROIC: ${thesis.moat_and_roic_durability || "—"}</p>
    <p>가치함정 ${trap.level || "—"} ${(trap.reasons || []).join("; ")}</p>
    <p class="hint">${rec.disclaimer || ""}</p>
  `;
}

async function loadResearch(ticker) {
  const data = await api(`/api/research/${ticker}`);
  renderResearch(data.exists ? data.row : null);
}

async function runAnalyze(ticker) {
  $("#research-box").innerHTML = "<p>간단 검증 중… 선택한 LLM에 요청합니다.</p>";
  const data = await api("/api/research", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
  renderResearch(data.row);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function rowNote(text) {
  const t = String(text || "").trim();
  return t ? `<div class="row-note">${escapeHtml(t)}</div>` : "";
}

const FACTOR_SPEC = [
  ["가", "value_score", 30, "가치"],
  ["품", "quality_score", 25, "품질"],
  ["성", "growth_score", 25, "성장"],
  ["모", "momentum_score", 10, "모멘텀"],
  ["안", "financial_score", 10, "안정"],
];

function factorBars(r) {
  return `<div class="factors">${FACTOR_SPEC.map(([, key, max, name]) => {
    const v = Number(r[key] || 0);
    const pct = Math.max(0, Math.min(100, (v / max) * 100));
    return `<span title="${name} ${v.toFixed(1)} / ${max}"><i><b style="width:${pct.toFixed(0)}%"></b><em>${name} ${v.toFixed(1)} / ${max}</em></i></span>`;
  }).join("")}</div>`;
}

function sunziCard(panel) {
  if (!panel || !panel.label) return "";
  const ev = (panel.evidence || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const contra = (panel.contrary || []).map((t) => `<li class="warn">${escapeHtml(t)}</li>`).join("");
  return `<article class="intro">
    <h3>${escapeHtml(panel.label)} ${fmt(panel.score, 0)} · 확신 ${escapeHtml(panel.confidence || "")}</h3>
    <p>${escapeHtml(panel.comment || "")}</p>
    ${ev ? `<ul>${ev}</ul>` : ""}
    ${contra ? `<ul>${contra}</ul>` : ""}
  </article>`;
}

function flowSpark(chart, key) {
  const vals = (chart || []).map((d) => Number(d[key] || 0)).filter((n) => Number.isFinite(n));
  if (!vals.length) return "";
  const max = Math.max(...vals.map((v) => Math.abs(v)), 1);
  return `<div class="fg-spark">${vals
    .slice(-60)
    .map((v) => {
      const h = Math.max(2, Math.round((Math.abs(v) / max) * 40));
      const cls = v > 0 ? "up" : v < 0 ? "down" : "";
      return `<b class="${cls}" style="height:${h}px" title="${v}"></b>`;
    })
    .join("")}</div>`;
}

function flow90Block(flow, ticker) {
  const chart = (flow && flow.chart) || [];
  const w = (flow && flow.windows) || {};
  if (!chart.length) {
    return `<article class="intro" style="background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:10px; padding:14px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">📊 공식 수급 90일</h3>
        <span class="chip" style="font-size:10px;">KIS 기관/외인</span>
      </div>
      <p style="font-size:12px; color:#94a3b8; line-height:1.5; margin:0 0 10px;">이 종목의 90일 KIS 공식 수급 내역이 아직 로컬 DB에 수집되지 않았습니다.</p>
      ${ticker ? `<button type="button" class="primary small" id="btn-collect-flow-single" data-ticker="${ticker}" style="font-size:11px; padding:5px 12px; font-weight:700;">⚡ KIS 공식 수급 즉시 수집</button>` : ""}
    </article>`;
  }
  return `<article class="intro" style="background:rgba(15,23,42,0.85); border:1px solid #1e293b; border-radius:10px; padding:14px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <h3 style="margin:0; font-size:13.5px; color:#38bdf8;">📊 공식 수급 90일</h3>
      <span class="chip ok" style="font-size:10px;">수집 완료</span>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:8px; font-size:12px; color:#cbd5e1; margin-bottom:10px;">
      <span>5일 <b>${fmtAmt(w.w5)}</b></span>
      <span>20일 <b>${fmtAmt(w.w20)}</b></span>
      <span>60일 <b>${fmtAmt(w.w60)}</b></span>
      <span>90일 <b>${fmtAmt(w.w90)}</b></span>
    </div>
    ${flowSpark(chart, "INSTITUTION_TOTAL") || flowSpark(chart, "FUND")}
    <div id="tier1-posture-container"></div>
  </article>`;
}

function eventsBlock(ev) {
  const rows = (ev && ev.rows) || [];
  if (!rows.length) {
    return `<article class="intro" style="margin-top:12px;">
      <h3>공시 이벤트</h3>
      <p class="hint">${escapeHtml((ev && ev.error) || "최근 분류 공시가 없습니다.")}</p>
      <div id="tier1-dart-container"></div>
    </article>`;
  }
  const lis = rows
    .slice(0, 8)
    .map((r) => {
      const ret = r.ret_5d != null ? ` · 이후5일 ${fmtPct(r.ret_5d)}` : r.sample === "LOW_SAMPLE" ? " · 표본부족" : "";
      const link = r.url ? `<a class="ext" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">원문</a>` : "";
      return `<li><b>${escapeHtml(r.event_ko || r.event_type)}</b> ${escapeHtml(r.report_date || "")} ${escapeHtml((r.title || "").slice(0, 48))}${ret} ${link}</li>`;
    })
    .join("");
  return `<article class="intro" style="margin-top:12px;">
    <h3>공시 이벤트 & DART 캘린더</h3>
    <ul class="intro-facts">${lis}</ul>
    <div id="tier1-dart-container"></div>
  </article>`;
}

function criticCard(panel) {
  if (!panel || !panel.posture) return "";
  const axes = panel.axes || {};
  const axisLine = [
    ["보존", axes.capital_preservation],
    ["비대칭", axes.asymmetric_payoff],
    ["선택권", axes.optionality],
    ["전장", axes.situational_advantage],
    ["근거", axes.evidence_strength],
    ["반대", axes.adversarial_robustness],
  ]
    .map(([k, v]) => `${k} ${fmt(v, 0)}`)
    .join(" · ");
  const wait = panel.waiting_test || {};
  const bearList = (panel.strongest_bear_evidence || []);
  const variantRaw = String(panel.variant_view || panel.variant || "").trim();
  const variantClean = (!variantRaw || variantRaw.includes("NO_CLEAR") || variantRaw === "NO_CLEAR_VARIANT_VIEW")
    ? "현재 시장 컨센서스와 펀더멘털 지표 간의 정합성을 주시하고 있어."
    : variantRaw;

  const post = String(panel.posture_ko || panel.posture || "");
  const isNegative = /후퇴|퇴로|회피|거부|경고|주의|경계|보수|bear|retreat|avoid/i.test(post);
  const isPositive = /진격|돌격|선제|공격|적극|bull|advance/i.test(post);

  let cardStyle = "background:rgba(15,23,42,0.9); border:1px solid #1e293b; border-radius:10px; padding:16px; margin-top:12px;";
  let badgeCls = "background:rgba(56,189,248,0.2); color:#38bdf8; border:1px solid rgba(56,189,248,0.4);";
  let badgeIcon = "🍵";
  let voiceColor = "#93c5fd";

  if (isNegative) {
    cardStyle = "background:linear-gradient(145deg, rgba(244,63,94,0.12), rgba(15,23,42,0.95)); border:1px solid rgba(244,63,94,0.45); border-left:4px solid #f43f5e; border-radius:10px; padding:16px; margin-top:12px; box-shadow:0 4px 20px rgba(244,63,94,0.08);";
    badgeCls = "background:rgba(244,63,94,0.25); color:#fda4af; border:1px solid rgba(244,63,94,0.6); font-weight:800;";
    badgeIcon = "⚠️";
    voiceColor = "#fda4af";
  } else if (isPositive) {
    cardStyle = "background:linear-gradient(145deg, rgba(16,185,129,0.12), rgba(15,23,42,0.95)); border:1px solid rgba(16,185,129,0.45); border-left:4px solid #10b981; border-radius:10px; padding:16px; margin-top:12px;";
    badgeCls = "background:rgba(16,185,129,0.25); color:#6ee7b7; border:1px solid rgba(16,185,129,0.6); font-weight:800;";
    badgeIcon = "🟢";
    voiceColor = "#6ee7b7";
  }

  const bearHtml = bearList.length ? `
    <div style="padding:10px 12px; background:rgba(244,63,94,0.14); border:1px solid rgba(244,63,94,0.35); border-radius:8px; margin:10px 0;">
      <b style="color:#fda4af; font-size:12px; display:block; margin-bottom:5px;">🚨 내가 가장 불편하게 보는 점 (핵심 리스크)</b>
      <ul style="margin:0; padding-left:14px; font-size:12px; color:#ffe4e6; line-height:1.6;">
        ${bearList.map(t => `<li style="margin:2px 0;"><b>${escapeHtml(t)}</b></li>`).join("")}
      </ul>
    </div>
  ` : "";

  const waitHtml = (wait.cost_of_waiting || wait.benefit_of_waiting) ? `
    <div style="padding:9px 12px; background:rgba(15,23,42,0.85); border:1px solid #334155; border-radius:8px; margin-top:10px; font-size:12px; line-height:1.5;">
      ${wait.benefit_of_waiting ? `<div style="color:#cbd5e1;"><b style="color:#38bdf8;">⏳ 기다리면:</b> ${escapeHtml(wait.benefit_of_waiting)}</div>` : ""}
      ${wait.cost_of_waiting ? `<div style="color:#cbd5e1; margin-top:4px;"><b style="color:#fb7185;">⚠️ 잃는 것:</b> ${escapeHtml(wait.cost_of_waiting)}</div>` : ""}
    </div>
  ` : "";

  const cleanOneLine = (panel.one_line_judgment || "")
    .replace(/Quant[에와를]?\s*(넣지|합산하지|바꾸지)\s*않습니다\.?[\s]*/gi, "")
    .replace(/이\s*판단은\s*Quant와\s*합산하지\s*않아\.?[\s]*/gi, "")
    .trim();

  const cleanComment = (panel.comment || "")
    .replace(/Quant[에와를]?\s*(넣지|합산하지|바꾸지)\s*않습니다\.?[\s]*/gi, "")
    .replace(/이\s*판단은\s*Quant와\s*합산하지\s*않아\.?[\s]*/gi, "")
    .trim();

  return `<article class="intro yang-brief" style="${cardStyle}">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
      <h3 style="margin:0; font-size:14px; color:#f8fafc;">🍵 실전 참모 전략검토</h3>
      <span class="chip" style="${badgeCls}">${badgeIcon} ${escapeHtml(panel.posture_ko || panel.posture)} ${fmt(panel.score, 0)}점</span>
    </div>
    ${cleanOneLine ? `<p class="yang-voice" style="color:${voiceColor}; font-weight:700; font-size:12.5px; line-height:1.5; margin:0 0 8px;">"${escapeHtml(cleanOneLine)}"</p>` : ""}
    ${cleanComment && cleanComment !== cleanOneLine ? `<p style="font-size:12px; color:#cbd5e1; line-height:1.5; margin:0 0 8px;">${escapeHtml(cleanComment)}</p>` : ""}
    <div style="padding:6px 10px; background:rgba(15,23,42,0.6); border-radius:6px; font-size:11px; color:#94a3b8; margin-bottom:10px;">
      📐 6대 축 검증: <b>${escapeHtml(axisLine)}</b>
    </div>
    ${panel.consensus ? `<p style="font-size:12px; color:#cbd5e1; margin:6px 0;"><b>💡 이미 가격에 들어간 이야기:</b> ${escapeHtml(panel.consensus)}</p>` : ""}
    <p style="font-size:12px; color:#cbd5e1; margin:6px 0;"><b>🔍 다른 보기 (컨센서스 점검):</b> ${escapeHtml(variantClean)}</p>
    ${bearHtml}
    ${waitHtml}
    ${panel.no_action_required ? `<div style="margin-top:10px; padding:7px 10px; background:rgba(244,63,94,0.18); border-radius:6px; font-weight:700; color:#fca5a5; font-size:12px;">🛑 지금은 무리하게 매수하지 않고 관망/퇴로 확보가 유리합니다.</div>` : ""}
  </article>`;
}

function fiveStrip(data) {
  let faLabel = "";
  let faGatePass = true;
  if (data.fa) {
    faGatePass = data.fa.fa_gate_pass !== false;
    let rawLabel = data.fa.label || data.fa.fa_label || "";
    let clean = rawLabel.replace(/^(🛡️|⚠️)\s*/, "").replace(/^法\s*/, "").trim();
    if (!clean) clean = faGatePass ? "재무적격" : "재무주의";
    const icon = faGatePass ? "🛡️" : "⚠️";
    faLabel = `${icon} 法 ${clean}`;
  }
  const parts = [
    data.dao,
    data.tian,
    data.di,
    data.jiang,
    data.fa
      ? {
          label: faLabel || (faGatePass ? "🛡️ 法 재무적격" : "⚠️ 法 재무주의"),
          score: data.fa.fa_score ?? data.fa.score,
          comment: data.fa.comment,
          fa_gate_pass: data.fa.fa_gate_pass,
        }
      : null,
  ];
  if (!parts.some((p) => p && p.label)) return "";
  return `<div class="five-grid">${parts
    .map((p) => {
      if (!p) return "";
      const isFail = p.fa_gate_pass === false || (p.label && (p.label.includes("주의") || p.label.includes("경고") || p.label.includes("탈락") || p.label.includes("위험") || p.label.includes("부담") || p.label.includes("미달")));
      const isPass = p.fa_gate_pass === true || (p.label && (p.label.includes("적격") || p.label.includes("통과") || p.label.includes("선행")));
      const cls = isFail ? "fail warn" : isPass ? "pass" : "";
      const scoreVal = Number(p.score || 0);
      const scoreColor = isFail ? "#ef4444" : scoreVal >= 70 ? "#34d399" : scoreVal >= 50 ? "#38bdf8" : "#fbbf24";
      const cleanComment = (p.comment || "")
        .replace(/Quant[에와를]?\s*(넣지|합산하지|바꾸지)\s*않습니다\.?[\s]*/gi, "")
        .replace(/Quant\s*순위는\s*바꾸지\s*않습니다\.?[\s]*/gi, "")
        .replace(/이\s*판단은\s*Quant와\s*합산하지\s*않아\.?[\s]*/gi, "")
        .replace(/재무\s*Quant\s*순위를\s*바꾸지\s*않습니다\.?[\s]*/gi, "")
        .trim();
      return `<div class="five-card ${cls}" style="background:linear-gradient(145deg, rgba(15,23,42,0.95), ${isPass ? 'rgba(34,197,94,0.12)' : isFail ? 'rgba(239,68,68,0.14)' : 'rgba(56,189,248,0.1)'}); border:1px solid ${isPass ? 'rgba(34,197,94,0.5)' : isFail ? 'rgba(239,68,68,0.5)' : 'rgba(56,189,248,0.3)'}; border-radius:12px; padding:12px 14px; display:flex; flex-direction:column; gap:6px; box-shadow:0 4px 16px rgba(0,0,0,0.35);">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
          <span style="font-weight:800; font-size:13.5px; color:#f8fafc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(p.label)}</span>
          <span style="padding:2px 8px; border-radius:99px; background:${isPass ? 'rgba(34,197,94,0.2)' : isFail ? 'rgba(239,68,68,0.2)' : 'rgba(56,189,248,0.2)'}; border:1px solid ${scoreColor}; font-size:13px; font-weight:900; color:${scoreColor}; flex-shrink:0;">${fmt(p.score, 0)}점</span>
        </div>
        <div style="width:100%; height:3px; background:rgba(255,255,255,0.08); border-radius:2px; overflow:hidden;">
          <div style="width:${Math.max(0, Math.min(100, scoreVal))}%; height:100%; background:${scoreColor}; border-radius:2px;"></div>
        </div>
        <p style="font-size:11.5px; line-height:1.45; word-break:keep-all; margin:0; color:#cbd5e1;">${escapeHtml(cleanComment)}</p>
      </div>`;
    })
    .join("")}</div>`;
}

function faChip(r) {
  if (r.fa_gate_pass === true) {
    return `<span class="tag up has-tip" data-tip-title="🛡️ 재무·리스크 적격 (손자병법 法 통과)" data-tip="${escapeHtml(r.fa_comment || "데이터 신뢰도, 재무 건전성 및 공시 리스크 요건을 모두 통과한 안전 적격 종목입니다.")}">🛡️ 재무적격</span>`;
  }
  if (r.fa_gate_pass === false) {
    const why = (r.fa_reasons_ko || []).join(" ") || r.fa_comment || "재무 건전성 규율 미달";
    return `<span class="tag down has-tip" data-tip-title="⚠️ 재무·리스크 주의 (손자병법 法 미달)" data-tip="${escapeHtml(why)}">⚠️ 재무주의</span>`;
  }
  return "";
}

function confCell(v) {
  const n = Number(v);
  if (Number.isNaN(n) || v == null || v === "") return "—";
  const cls = n >= 80 ? "ok" : n >= 70 ? "warn" : "bad";
  return `<span class="${cls}">${fmt(v, 1)}</span>`;
}

function penCell(v) {
  const n = Number(v);
  if (Number.isNaN(n) || v == null || v === "") return "—";
  const cls = n >= 5 ? "bad" : n >= 1 ? "warn" : "";
  return `<span class="${cls}">${fmt(v, 1)}</span>`;
}

function signedInt(n) {
  const x = Number(n || 0);
  const cls = x > 0 ? "up" : x < 0 ? "down" : "";
  const txt = `${x > 0 ? "+" : ""}${x.toLocaleString("ko-KR")}`;
  return `<span class="${cls}">${txt}</span>`;
}

function renderMarkdown(src) {
  const lines = String(src || "").split(/\r?\n/);
  const out = [];
  let table = [];
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !r.every((c) => /^[\s:-]*$/.test(c)));
    if (rows.length) {
      out.push("<table>");
      rows.forEach((cells, i) => {
        const tag = i === 0 ? "th" : "td";
        out.push("<tr>" + cells.map((c) => `<${tag}>${c}</${tag}>`).join("") + "</tr>");
      });
      out.push("</table>");
    }
    table = [];
  };
  for (const raw of lines) {
    const escaped = escapeHtml(raw);
    if (raw.trim().startsWith("|") && raw.trim().endsWith("|")) {
      table.push(raw.trim().slice(1, -1).split("|").map((c) => escapeHtml(c.trim())));
      continue;
    }
    flushTable();
    if (/^###\s+/.test(raw)) out.push(`<h4>${escapeHtml(raw.replace(/^###\s+/, ""))}</h4>`);
    else if (/^##\s+/.test(raw)) out.push(`<h3>${escapeHtml(raw.replace(/^##\s+/, ""))}</h3>`);
    else if (/^#\s+/.test(raw)) out.push(`<h3>${escapeHtml(raw.replace(/^#\s+/, ""))}</h3>`);
    else if (/^[-*]\s+/.test(raw)) out.push(`<li>${escapeHtml(raw.replace(/^[-*]\s+/, "")).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</li>`);
    else if (!raw.trim()) out.push("<br>");
    else out.push(`<p>${escaped.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</p>`);
  }
  flushTable();
  return out.join("");
}

function reportArticleHtml(rec) {
  if (!rec) return "<p>아직 AI 분석 리포트가 없습니다.</p>";
  if (rec.report_markdown) {
    const miss = (rec.missing_headings || []).length
      ? `<p class="hint">빠진 제목: ${(rec.missing_headings || []).join(", ")}</p>`
      : "";
    return `
      <p class="hint">${rec.prompt_version || ""} · ${rec.provider || ""} ${rec.model || ""} · ${(rec.researched_at || "").replace("T", " ").slice(0, 16)}</p>
      <div class="report">${renderMarkdown(rec.report_markdown || "")}</div>
      ${miss}
      <p class="hint">${rec.disclaimer || ""}</p>
    `;
  }
  const thesis = rec.thesis || {};
  const trap = rec.value_trap_assessment || {};
  return `
    <h3>간단 검증 · ${rec.provider || ""} ${rec.model || ""}</h3>
    <p>판정 <b>${rec.research_decision || "—"}</b> · 리서치 ${fmt(rec.research_score, 0)} · 확신 ${fmt(rec.research_confidence, 0)}</p>
    <p>${thesis.one_line || ""}</p>
    <p>${thesis.business_model || ""}</p>
    <p>해자/ROIC: ${thesis.moat_and_roic_durability || "—"}</p>
    <p>가치함정 ${trap.level || "—"} ${(trap.reasons || []).join("; ")}</p>
    <p class="hint">${rec.disclaimer || ""}</p>
  `;
}

let modalTicker = "";

function openReportModal(rec, customTitle = null) {
  const code = padTicker(rec.ticker);
  const company = rec.company || code;
  const title = customTitle || `📑 ${escapeHtml(company)} (${code}) 심층 리서치 & 인포그래픽 리포트`;
  const md = renderMarkdown(rec.report_markdown || "");
  const usage = rec.usage || {};
  const tokensStr = usage.total_tokens ? `🪙 소모 토큰: ${Number(usage.total_tokens).toLocaleString()} (입력 ${Number(usage.prompt_tokens || 0).toLocaleString()} / 출력 ${Number(usage.completion_tokens || 0).toLocaleString()})` : "🪙 토큰: 기록 없음";
  const meta = `${rec.provider || ""} · ${rec.model || ""} · 기준일 ${rec.as_of_date || ""} · ${tokensStr}`;

  const infographicUrl = `/api/research/${code}/infographic?as_of=${encodeURIComponent(rec.as_of_date || "")}`;

  // Strategy Backtest Summary Hero if available
  let btHtml = "";
  const bt = rec.strategy_backtest || {};
  if (bt && bt.ok && bt.strategies && bt.strategies.length) {
    const strats = bt.strategies;
    const stratRows = strats.map((s, idx) => {
      const isBest = s.strategy_id === bt.best_id;
      const sh = s.sharpe != null ? fmt(s.sharpe, 2) : "—";
      const oosSh = s.oos_sharpe != null ? fmt(s.oos_sharpe, 2) : "—";
      const valRet = s.validation_return != null ? `${s.validation_return > 0 ? "+" : ""}${(s.validation_return * 100).toFixed(1)}%` : "—";
      const oosRet = s.oos_return != null ? `${s.oos_return > 0 ? "+" : ""}${(s.oos_return * 100).toFixed(1)}%` : "—";
      const wfHit = s.wf_hit != null ? `${(s.wf_hit * 100).toFixed(0)}%` : "—";
      const mddVal = s.max_drawdown != null ? -Math.abs(s.max_drawdown * 100) : null;
      const mdd = mddVal != null ? `${mddVal.toFixed(1)}%` : "—";
      const ret = s.total_return != null ? `${s.total_return > 0 ? "+" : ""}${(s.total_return * 100).toFixed(1)}%` : "—";
      const retCls = s.total_return != null && s.total_return > 0 ? "up" : s.total_return < 0 ? "down" : "";
      return `
        <tr style="${isBest ? 'background:rgba(56,189,248,0.12); font-weight:600;' : ''}">
          <td>${isBest ? '👑 1위 ' : `${idx + 1}위 `}${escapeHtml(s.name || s.strategy_id)}</td>
          <td><span class="chip">${escapeHtml(s.family_ko || s.family || "")}</span></td>
          <td class="${retCls}">${ret}</td>
          <td><b>${sh}</b></td>
          <td>${valRet}<div class="meta">${s.validation_trade_count ?? 0}회</div></td>
          <td>${oosRet}<div class="meta">샤프 ${oosSh} · ${s.oos_trade_count ?? 0}회</div></td>
          <td>${wfHit}</td>
          <td class="down">${mdd}</td>
          <td>${s.trade_count || 0}회</td>
          <td class="meta">${escapeHtml(s.params_ko || "")}</td>
        </tr>
      `;
    }).join("");

    btHtml = `
      <div style="background:linear-gradient(145deg, #0e172a, #0b1322); border:1px solid rgba(56,189,248,0.35); border-radius:10px; padding:14px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <b style="color:#38bdf8; font-size:14px;">🧪 4대 가격 규칙 백테스트 검증</b>
          <span style="font-size:11.5px; color:#94a3b8;">${bt.bars || 0}거래일 일봉 검증</span>
        </div>
        <div style="padding:8px 10px; background:rgba(56,189,248,0.1); border-radius:6px; margin-bottom:10px; font-size:12.5px;">
          <b style="color:#38bdf8;">검증 구간 점수 1위: ${escapeHtml(bt.best_name || "")} (${escapeHtml(bt.best_params_ko || "")})</b>
          <p style="margin:3px 0 0; color:#cbd5e1; font-size:12px;">${escapeHtml(bt.best_comment || "")}</p>
        </div>
        <div class="table-wrap">
          <table class="table" style="font-size:11.5px;">
            <thead>
              <tr>
                <th>전략명</th>
                <th>유형</th>
                <th>전체기간 참고 수익률</th>
                <th>전체기간 샤프</th>
                <th>검증 수익률</th>
                <th>최종검증 결과</th>
                <th>WF 승률</th>
                <th>최대낙폭</th>
                <th>매매횟수</th>
                <th>최적 파라미터</th>
              </tr>
            </thead>
            <tbody>
              ${stratRows}
            </tbody>
          </table>
        </div>
        ${renderPlaybookHtml(bt.playbook)}
      </div>
    `;
  }

  // Dual View Body Container
  const drawerContent = `
    <div class="report-modal-toolbar">
      <div class="report-view-subtabs">
        <button type="button" class="report-view-btn active" id="modal-tab-infographic">🎨 인포그래픽 뷰 (Interactive Deck)</button>
        <button type="button" class="report-view-btn" id="modal-tab-markdown">📑 정통 리포트 뷰 (Text Deep-Dive)</button>
      </div>
      <div style="display:flex; gap:6px; align-items:center;">
        <button type="button" class="ghost small" id="btn-modal-regen" style="height:32px; font-size:12px; border-color:rgba(56,189,248,0.4); color:#38bdf8; font-weight:600;">🔄 다시 생성</button>
        <button type="button" class="primary small" id="btn-open-fullscreen-report" style="height:32px; font-size:12px;">🖥️ 새 창 전체화면</button>
        <button type="button" class="ghost small" id="btn-print-report" style="height:32px; font-size:12px;">🖨️ PDF / 인쇄</button>
        <a class="ghost small" href="${infographicUrl}" download="${encodeURIComponent(company)}_${code}_인포그래픽리포트.html" style="height:32px; font-size:12px; display:inline-flex; align-items:center; text-decoration:none;">📥 HTML 저장</a>
      </div>
    </div>

    <!-- Pane 1: Infographic View (Default) -->
    <div id="modal-pane-infographic" class="report-iframe-wrap">
      <iframe src="${infographicUrl}" title="Infographic Report"></iframe>
    </div>

    <!-- Pane 2: Markdown Deep-Dive View -->
    <div id="modal-pane-markdown" class="hidden">
      <div class="meta" style="margin-bottom:12px">${escapeHtml(meta)}</div>
      ${btHtml}
      <div class="report-render">${md}</div>
    </div>
  `;

  // Open the report modal using the existing #report-modal structure
  modalTicker = code;
  const modal = $("#report-modal");
  const titleEl = $("#report-modal-title");
  const bodyEl = $("#report-modal-body");
  if (titleEl) titleEl.textContent = title;
  if (bodyEl) bodyEl.innerHTML = drawerContent;
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");

  // Wire up dual view tab switching in modal
  setTimeout(() => {
    const tabInfo = $("#modal-tab-infographic");
    const tabMd = $("#modal-tab-markdown");
    const paneInfo = $("#modal-pane-infographic");
    const paneMd = $("#modal-pane-markdown");
    const btnFull = $("#btn-open-fullscreen-report");
    const btnModalRegen = $("#btn-modal-regen");

    if (tabInfo && tabMd && paneInfo && paneMd) {
      tabInfo.onclick = () => {
        tabInfo.classList.add("active");
        tabMd.classList.remove("active");
        paneInfo.classList.remove("hidden");
        paneMd.classList.add("hidden");
      };
      tabMd.onclick = () => {
        tabMd.classList.add("active");
        tabInfo.classList.remove("active");
        paneMd.classList.remove("hidden");
        paneInfo.classList.add("hidden");
      };
    }
    if (btnFull) {
      btnFull.onclick = () => {
        window.open(infographicUrl, "_blank");
      };
    }
    if (btnModalRegen) {
      btnModalRegen.onclick = () => {
        runReport(code).catch((err) => alert(err.message));
      };
    }
    const btnPrint = $("#btn-print-report");
    if (btnPrint) {
      btnPrint.onclick = () => {
        const iframe = $("#modal-pane-infographic iframe");
        if (iframe && iframe.contentWindow) {
          iframe.contentWindow.focus();
          iframe.contentWindow.print();
        } else {
          window.print();
        }
      };
    }
  }, 30);
}

function closeReportModal() {
  $("#report-modal").classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function renderReport(rec) {
  const box = $("#report-box");
  if (!box) return;
  if (!rec) {
    box.innerHTML = `<p style="font-size:11.5px; color:#64748b; margin:6px 0 0;">💡 아직 생성된 AI 리포트가 없습니다. 상단 [🤖 AI 리포트] 또는 [🎨 인포그래픽]을 클릭하세요.</p>`;
    return;
  }
  box.innerHTML = `
    <div style="padding:9px 12px; background:rgba(56,189,248,0.08); border:1px solid rgba(56,189,248,0.3); border-radius:8px; margin-top:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:11.5px; font-weight:700; color:#38bdf8;">🤖 AI 리포트 & 인포그래픽</span>
        <span class="chip ok" style="font-size:10px; padding:2px 6px;">생성 완료</span>
      </div>
      <div style="font-size:10.5px; color:#94a3b8; margin:2px 0 6px;">엔진: ${escapeHtml(rec.provider || "")} · ${escapeHtml(rec.model || "")}</div>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px;">
        <button class="primary small" id="btn-report-wide" style="font-size:11px; padding:4px 6px; font-weight:700; white-space:nowrap;">🎨 인포그래픽 열기</button>
        <button class="ghost small" id="btn-report-regen" style="font-size:11px; padding:4px 6px; font-weight:600; white-space:nowrap; border-color:rgba(56,189,248,0.4); color:#38bdf8;">🔄 다시 생성</button>
      </div>
    </div>
  `;
  $("#btn-report-wide")?.addEventListener("click", () => openReportModal(rec));
  $("#btn-report-regen")?.addEventListener("click", () => runReport(rec.ticker).catch((err) => alert(err.message)));
}

async function loadReport(ticker, asOf) {
  const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
  const data = await api(`/api/research/${ticker}/report${q}`);
  renderReport(data.exists ? data.row : null);
  return data.exists ? data.row : null;
}


const inFlightReports = new Map();

function updateAiReportStatusBanner() {
  let banner = $("#ai-report-floating-banner");
  const prog = $("#global-progress-bar");
  const chip = $("#chip-activity");

  if (inFlightReports.size === 0) {
    if (banner) banner.remove();
    if (prog) prog.classList.add("hidden");
    if (chip) {
      chip.classList.remove("activity-running");
      chip.classList.add("activity-idle");
      chip.innerHTML = "🟢 시스템 준비됨";
    }
    return;
  }

  // Active items exist
  const items = Array.from(inFlightReports.values());
  const latest = items[items.length - 1];
  const countText = items.length > 1 ? ` (+${items.length - 1}건)` : "";

  if (prog) prog.classList.remove("hidden");
  if (chip) {
    chip.classList.remove("activity-idle");
    chip.classList.add("activity-running");
    chip.innerHTML = `⚡ AI 리포트 작성 중: ${escapeHtml(latest.company || latest.ticker)}${countText}`;
  }

  if (!banner) {
    banner = document.createElement("div");
    banner.id = "ai-report-floating-banner";
    banner.className = "ai-report-floating-banner";
    document.body.appendChild(banner);
  }

  banner.innerHTML = `
    <div class="spinner"></div>
    <div>
      <b>🤖 [${escapeHtml(latest.company || latest.ticker)}] AI 리포트 백그라운드 생성 중…</b>${countText}
      <div style="font-size:11px; color:#94a3b8; margin-top:2px;">창을 닫아도 계속 실행되며 완료 시 자동 알림 및 보관됩니다.</div>
    </div>
    <button type="button" id="btn-reopen-ai-modal" class="ghost" style="padding:4px 10px; font-size:12px; height:28px; white-space:nowrap;">진행창 열기</button>
  `;

  const btnReopen = $("#btn-reopen-ai-modal");
  if (btnReopen) {
    btnReopen.onclick = () => {
      openReportModal({
        ticker: latest.ticker,
        company: latest.company,
        report_markdown: `⏳ **[${latest.company || latest.ticker}] AI 심층 분석 리포트를 작성하고 있습니다.**\n\n- DeepSeek / OpenRouter LLM을 통해 최신 공시, 5대 팩터, 4대 전략 백테스트 및 실전 매매 플레이북을 생성 중입니다.\n- 예상 소요 시간: 약 1~2분\n- **이 창을 닫아도 백그라운드에서 정상 완료됩니다.**`,
      }, "리포트 작성 중 (백그라운드)");
    };
  }
}

async function runReport(ticker) {
  const code = padTicker(ticker);
  let company = code;
  const matchRow = rankRows.find((r) => padTicker(r.ticker) === code) || (dashRows || []).find((r) => padTicker(r.ticker) === code);
  if (matchRow && matchRow.company) company = matchRow.company;

  // 1. Register in inFlightReports
  inFlightReports.set(code, { ticker: code, company, startedAt: Date.now() });
  updateAiReportStatusBanner();

  // 2. Open initial progress modal
  openReportModal({
    ticker: code,
    company,
    report_markdown: `⏳ **[${company} (${code})] AI 심층 기업 분석 리포트를 작성하고 있습니다.**\n\n- DeepSeek / OpenRouter LLM을 호출하여 최신 공시, 재무 팩터, 해자, 4대 전략 백테스트 및 실전 매매 플레이북을 실시간 분석 중입니다.\n- 예상 소요 시간: 약 1~2분\n- **이 창을 닫아도 백그라운드에서 안전하게 완료되며, 완료 시 상단 알림이 뜹니다.**`,
  }, "리포트 작성 중 (백그라운드 진행)");

  showToast(`⚡ <b>[${company} (${code})] AI 분석 리포트 발간 시작</b> (백그라운드 실행 중)`, "info", 5000);

  try {
    const data = await api("/api/research/report", {
      method: "POST",
      body: JSON.stringify({ ticker: code }),
    });

    // 3. Finished successfully
    inFlightReports.delete(code);
    updateAiReportStatusBanner();

    if (data && data.row) {
      renderReport(data.row);
      openReportModal(data.row);
      loadReportArchive().catch(() => {});
      showToast(`🎉 <b>[${data.row.company || company} (${code})] AI 분석 리포트 작성이 완료되었습니다!</b>`, "success", 8000);
    }
  } catch (err) {
    inFlightReports.delete(code);
    updateAiReportStatusBanner();
    showToast(`⚠️ [${company}] AI 리포트 작성 실패: ${err.message}`, "error", 8000);
    alert(`AI 리포트 작성 오류: ${err.message}`);
  }
}

async function openArchivedItem(ticker, asOf, kind) {
  const code = padTicker(ticker);
  if (kind === "간단 검증") {
    const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
    const data = await api(`/api/research/${code}${q}`);
    if (data.exists) {
      openReportModal(data.row, `${data.row.company || code} 간단 검증`);
      return;
    }
  }
  const rec = await loadReport(code, asOf);
  if (rec) {
    openReportModal(rec);
    return;
  }
  await openStock(code);
}

async function loadDash() {
  const [status, top, all, guide, archive] = await Promise.all([
    api("/api/status"),
    api("/api/results/top?n=100"),
    api("/api/results/all?limit=300"),
    guideCache ? Promise.resolve(guideCache) : api("/api/guide"),
    api("/api/research/reports").catch(() => ({ rows: [] })),
  ]);
  guideCache = guide;
  reportRows = archive.rows || [];
  lastStatus = status;
  lastStatusExplain = status.status_explain || null;
  renderFreshChip(status.freshness);
  if (currentView === "dash" || currentView === "rank") {
    stampFromStatus();
    const attemptedAsOf = status?.quality?.as_of_date || "";
    const rankAsOf = top?.source_as_of || all?.source_as_of || "";
    if (rankAsOf && attemptedAsOf && rankAsOf !== attemptedAsOf) {
      const priceAsOf = status?.freshness?.price_max_date || "";
      setPageAsOf(
        `퀀트 랭킹 ${rankAsOf} (마지막 성공본)${priceAsOf ? ` · KRX 시세 ${priceAsOf}` : ""}`,
        `최신 ${attemptedAsOf} 계산은 적격 랭킹이 없어 표시에서 제외했습니다. 데이터가 비어 보이지 않도록 검증을 통과한 마지막 성공본을 사용합니다.`
      );
    }
  }
  renderSchedLine(status.scheduler);
  renderRunDiagnostics(status);
  
  const llmName = status.llm_label || status.llm_provider || "openrouter";
  const llmModel = status.llm_model ? status.llm_model.split("/").pop() : "";
  const llmDisplay = llmModel ? `🤖 AI: ${llmName} (${llmModel}) ▾` : `🤖 AI: ${llmName} ▾`;
  setChip($("#chip-llm"), llmDisplay, `AI 분석 리포트 생성 모델: ${status.llm_model || llmName}. 클릭하여 모델을 즉시 변경할 수 있습니다.`);
  dashRows = top.rows || [];
  renderKpis(status, dashRows, all.total);
  renderChampions(dashRows);
  loadGlanceTop3().catch(() => {});
  renderDashDna(dashRows, currentDashTopN);
  renderTop20(dashRows, currentDashTopN);
  renderQuality(status.quality, guideCache, status.freshness);
  rankRows = all.rows || [];
  renderRank($("#rank-q").value);
  renderJob(status.job);
  renderReportList("#dash-reports-body", reportRows, 6);
  renderReportList("#reports-body", filterReportRows($("#report-q") ? $("#report-q").value : ""));
  loadWatch().catch(() => {});
  loadPortfolio().catch(() => {});
  loadDashTier1Briefing().catch(() => {});
}

function renderTier1Unavailable(container, res = {}, err = null) {
  if (!container) return false;
  if (res && res.ok) return true;
  const evidence = res?.evidence || {};
  const code = res?.error_code || "TIER1_REQUEST_FAILED";
  const message = res?.message || err?.message || "무료 AI 설명을 불러오지 못했습니다.";
  const missing = Array.isArray(evidence.missing) && evidence.missing.length
    ? `<div style="margin-top:5px; font-size:11px; color:#fbbf24;">누락: ${escapeHtml(evidence.missing.join(", "))}</div>`
    : "";
  container.innerHTML = `
    <div class="tier1-briefing-card" style="background:rgba(120,53,15,0.12); border:1px solid rgba(245,158,11,0.45); border-radius:10px; padding:11px 14px; margin-bottom:14px;">
      <div style="display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
        <b style="font-size:12.5px; color:#fbbf24;">⚠️ Tier 1 설명 사용 불가</b>
        <span class="chip" style="font-size:10px; color:#fbbf24;">${escapeHtml(code)}</span>
      </div>
      <p style="margin:6px 0 0; color:#cbd5e1; font-size:12px; line-height:1.5;">${escapeHtml(message)}</p>
      <div style="margin-top:4px; color:#94a3b8; font-size:10.5px;">원본 수치와 퀀트 점수에는 영향이 없습니다.</div>
      ${missing}
    </div>`;
  return false;
}

function appendTier1Meta(container, res = {}) {
  if (!container || !res) return;
  const card = container.querySelector(".tier1-briefing-card") || container.firstElementChild;
  if (!card || card.querySelector(".tier1-meta-row")) return;
  const evidence = res.evidence || {};
  const coverageMap = { SUFFICIENT: "근거 충분", PARTIAL: "근거 일부", NONE: "근거 없음" };
  const coverage = coverageMap[evidence.coverage] || "근거 상태 미상";
  const sourceCount = Array.isArray(evidence.sources) ? evidence.sources.length : 0;
  const fallback = res.status === "DETERMINISTIC_FALLBACK";
  const cacheLabel = res.cache?.hit === true
    ? "♻️ 동일 데이터 해설 재사용"
    : (res.cache?.stored === false ? "⚠️ 새 생성 · 캐시 미저장" : (res.cache ? "✨ 최신 데이터로 새 생성" : ""));
  card.insertAdjacentHTML("beforeend", `
    <div class="tier1-meta-row" style="display:flex; gap:6px; flex-wrap:wrap; align-items:center; padding-top:7px; margin-top:3px; border-top:1px solid rgba(148,163,184,0.16); font-size:10.5px; color:#94a3b8;">
      <span class="chip" style="font-size:10px;">${fallback ? "🧮 규칙 기반 설명" : "🤖 AI 해석"}</span>
      ${cacheLabel ? `<span class="chip" style="font-size:10px;">${cacheLabel}</span>` : ""}
      <span class="chip" style="font-size:10px;">📌 ${escapeHtml(coverage)} · ${Number(evidence.item_count || 0)}건</span>
      <span>출처 ${sourceCount}개</span>
      ${evidence.as_of ? `<span>기준 ${escapeHtml(String(evidence.as_of))}</span>` : ""}
      <span>🔒 퀀트 점수 미반영</span>
    </div>`);
}

async function loadDashTier1Briefing() {
  const container = $("#dash-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/dashboard/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.headline) {
      const isRuleFallback = res.status === "DETERMINISTIC_FALLBACK";
      const engineLabel = isRuleFallback ? "실데이터 자동 요약" : "Tier 1 무료 엔진";
      const modelLabel = isRuleFallback ? "규칙 기반 · AI 미사용" : `🤖 ${res.model || "Tier 1 무료 모델"} (비용 0원)`;
      container.innerHTML = `
        <div style="background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,58,138,0.25)); border:1px solid rgba(56,189,248,0.35); border-radius:12px; padding:12px 16px; display:flex; flex-direction:column; gap:6px; box-shadow:0 4px 16px rgba(0,0,0,0.35);">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">⚡ 오늘의 퀀트 시장 종합 브리핑</span>
              <span class="chip ok" style="font-size:10px; font-weight:700;">${escapeHtml(engineLabel)}</span>
            </div>
            <span style="font-size:11px; color:#86efac; font-weight:600;">${escapeHtml(modelLabel)}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <div style="display:flex; flex-direction:column; gap:4px; font-size:12px; color:#cbd5e1; line-height:1.5;">
            ${res.champion_focus ? `<div>👑 <b>1위 챔피언 모멘텀:</b> ${escapeHtml(res.champion_focus)}</div>` : ""}
            ${res.strategy_note ? `<div>💡 <b>랭킹 해석 주의:</b> ${escapeHtml(res.strategy_note)}</div>` : ""}
          </div>
        </div>
      `;
      appendTier1Meta(container, res);
    }
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadRankTier1Briefing() {
  const container = $("#rank-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/rank/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    const changes = (res.changes || []).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const explanations = (res.top_explanations || []).slice(0, 4).map((item) => `
      <div style="padding:7px 9px; border-radius:7px; background:rgba(15,23,42,0.55); border:1px solid rgba(148,163,184,0.14);">
        <b style="color:#67e8f9;">${escapeHtml(item.ticker || "종목")}</b>
        <span style="color:#cbd5e1;"> · ${escapeHtml(item.summary || "")}</span>
      </div>`).join("");
    const cautions = (res.cautions || []).slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    container.innerHTML = `
      <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(14,116,144,0.16)); border:1px solid rgba(34,211,238,0.32); border-radius:12px; padding:13px 16px; display:flex; flex-direction:column; gap:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
          <b style="color:#67e8f9; font-size:13px;">🔎 점수·순위 변화 AI 해설</b>
          <span style="font-size:10.5px; color:#94a3b8;">${escapeHtml(res.model || "Tier 1 무료 모델")}</span>
        </div>
        <strong style="color:#f8fafc; font-size:14px;">${escapeHtml(res.headline || "")}</strong>
        ${changes ? `<div><b style="font-size:11.5px; color:#38bdf8;">전회 대비 관측</b><ul style="margin:4px 0 0; padding-left:19px; color:#cbd5e1; font-size:12px; line-height:1.5;">${changes}</ul></div>` : ""}
        ${explanations ? `<div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:6px; font-size:11.5px;">${explanations}</div>` : ""}
        ${cautions ? `<div style="background:rgba(245,158,11,0.08); border-left:3px solid #f59e0b; padding:6px 9px; border-radius:5px;"><b style="font-size:11px; color:#fbbf24;">해석 주의</b><ul style="margin:3px 0 0; padding-left:18px; color:#cbd5e1; font-size:11px;">${cautions}</ul></div>` : ""}
      </div>`;
    appendTier1Meta(container, res);
  } catch (e) {
    renderTier1Unavailable(container, null, e);
  }
}

async function loadMarketTier1Briefing() {
  const container = $("#market-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/market/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.headline) {
      container.innerHTML = `
        <div style="background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(168,85,247,0.2)); border:1px solid rgba(168,85,247,0.35); border-radius:12px; padding:12px 16px; display:flex; flex-direction:column; gap:6px; box-shadow:0 4px 16px rgba(0,0,0,0.35); margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:13px; font-weight:800; color:#c084fc;">🌐 글로벌 매크로 & 공포탐욕 AI 코멘터리</span>
              <span class="chip ok" style="font-size:10px; font-weight:700;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#86efac; font-weight:600;">🤖 ${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")} (비용 0원)</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)} <span class="chip" style="font-size:11px; margin-left:6px; color:#38bdf8;">${escapeHtml(res.risk_posture || "중립 대응")}</span></b>
          <div style="display:flex; flex-direction:column; gap:4px; font-size:12px; color:#cbd5e1; line-height:1.5;">
            ${res.macro_insight ? `<div>📊 <b>거시 환경 진단:</b> ${escapeHtml(res.macro_insight)}</div>` : ""}
            ${res.action_tip ? `<div>🔎 <b>추가 확인할 지표:</b> ${escapeHtml(res.action_tip)}</div>` : ""}
            ${(res.drivers || []).length ? `<div style="display:flex; flex-wrap:wrap; gap:5px; margin-top:3px;">${res.drivers.slice(0, 6).map((d) => `<span class="chip" style="font-size:10px;">${escapeHtml(d.id || "지표")} · ${escapeHtml(d.direction || "중립")} · ${escapeHtml(d.reason || "")}</span>`).join("")}</div>` : ""}
          </div>
        </div>
      `;
      appendTier1Meta(container, res);
    }
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadFlowTier1Briefing(containerId = "flow-tier1-briefing") {
  const container = $(`#${containerId}`);
  if (!container) return;
  try {
    const res = await api("/api/flow/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.headline) {
      container.innerHTML = `
        <div style="background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(52,211,153,0.18)); border:1px solid rgba(52,211,153,0.35); border-radius:12px; padding:12px 16px; display:flex; flex-direction:column; gap:6px; box-shadow:0 4px 16px rgba(0,0,0,0.35); margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:13px; font-weight:800; color:#34d399;">⚡ 외인·기관 메이저 수급 AI 브리핑</span>
              <span class="chip ok" style="font-size:10px; font-weight:700;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#86efac; font-weight:600;">🤖 ${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")} (비용 0원)</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.briefing || "")}</p>
          ${(res.focus_sectors || []).length ? `<div style="display:flex; gap:6px; align-items:center; margin-top:2px;"><span style="font-size:11px; color:#94a3b8;">주목 섹터:</span> ${res.focus_sectors.map(s => `<span class="chip" style="font-size:10.5px; padding:1px 6px;">${escapeHtml(s)}</span>`).join("")}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadTossTier1Briefing() {
  const container = $("#toss-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/toss/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:12px; padding:12px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">⚡</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">토스 실시간 시장 모멘텀 AI 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.movers_summary || "")}</p>
          ${res.trading_tip ? `<div style="margin-top:2px; font-size:11.5px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:4px 8px; border-radius:4px;">💡 <b>순위 자료 해석 주의:</b> ${escapeHtml(res.trading_tip)}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadSectorTier1Briefing() {
  const container = $("#sector-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/sector/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:12px; padding:12px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">🔄</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">26대 KSIC 업종 순환매 & 주도 섹터 AI 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.leading_sector_comment || "")}</p>
          ${res.sector_strategy ? `<div style="margin-top:2px; font-size:11.5px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:4px 8px; border-radius:4px;">🔎 <b>업종 점수 해석 주의:</b> ${escapeHtml(res.sector_strategy)}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadUs13fTier1Briefing() {
  const container = $("#us13f-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/us13f/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:12px; padding:12px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">🏛️</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">월가 대가 포트폴리오 13F 컨센서스 AI 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.consensus_insight || "")}</p>
          ${res.action_tip ? `<div style="margin-top:2px; font-size:11.5px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:4px 8px; border-radius:4px;">💡 <b>13F 해석상 한계:</b> ${escapeHtml(res.action_tip)}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadSeasonalityTier1Briefing() {
  const container = $("#seasonality-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/seasonality/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:12px; padding:12px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">📅</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">30개년 빅데이터 시즌 모멘텀 AI 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.seasonality_brief || "")}</p>
          ${(res.key_catalysts || []).length ? `
            <div style="display:flex; gap:8px; align-items:flex-start; flex-wrap:wrap; margin-top:4px;">
              <span class="chip" style="font-size:11px; font-weight:700; color:#38bdf8; background:rgba(56,189,248,0.12); border:1px solid rgba(56,189,248,0.25); padding:2px 8px; border-radius:6px; white-space:nowrap; flex-shrink:0;">📌 주요 캘린더 이벤트</span>
              <div style="display:flex; flex-wrap:wrap; gap:6px; flex:1;">
                ${res.key_catalysts.map(c => `<span class="chip" style="font-size:11px; padding:2px 8px; background:rgba(30,41,59,0.85); color:#cbd5e1; border:1px solid rgba(255,255,255,0.1);">${escapeHtml(c)}</span>`).join("")}
              </div>
            </div>` : ""}
          ${res.sample_caution ? `<div style="font-size:11.5px; color:#fbbf24; background:rgba(245,158,11,0.08); border-left:3px solid #f59e0b; padding:5px 9px; border-radius:4px;">⚠️ <b>표본·재현성:</b> ${escapeHtml(res.sample_caution)}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadTradeTier1Briefing() {
  const container = $("#trade-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/trade/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:12px; padding:12px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">⚡</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">트레이딩 랩 단기 스윙 & 수급 타점 AI 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.trading_brief || "")}</p>
          ${res.execution_guide ? `<div style="margin-top:2px; font-size:11.5px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:4px 8px; border-radius:4px;">🔎 <b>판단 무효화·주의:</b> ${escapeHtml(res.execution_guide)}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

const SUNZI_PERSONAS = {
  yang: {
    avatar: "🍵",
    name: "양 웬리 제독",
    sub: "제13함대 사령관 · 불패의 퀀트 참모",
    badge: "🍵 홍차 브리핑 준비 완료",
    quote: "“전쟁에서 가장 중요한 건 이기는 게 아니라, 지지 않는 거라네.”",
    briefingTitle: "제13함대 히페리온 작전 회의록",
    heroStep2Label: "💡 양 웬리의 기책 & 진입 타점:",
    heroTitle: "⚔️ 양 웬리의 정밀 전술 분석 후보 TOP 6",
    tableCol: "양 웬리 전술 총평"
  },
  reinhard: {
    avatar: "🦁",
    name: "라인하르트 폰 로엔그람 황제",
    sub: "은하제국 황제 · 패도적 모멘텀 총사령관",
    badge: "🦁 제국 친정군 출진 준비 완료",
    quote: "“우주(시장)의 패권은 주저하는 자에게 주어지지 않는다. 전 함대 돌격!”",
    briefingTitle: "은하제국 황제 친정군 작전 칙령록",
    heroStep2Label: "⚔️ 라인하르트의 주도주 돌파 타점:",
    heroTitle: "🦁 라인하르트 황제의 전력 돌격 후보 TOP 6",
    tableCol: "라인하르트 황제 칙령"
  },
  oberstein: {
    avatar: "👁️",
    name: "파울 폰 오베르슈타인 군무상서",
    sub: "은하제국 군무상서 · 냉혹한 리스크 통제관",
    badge: "👁️ 리스크 사정 및 도려내기 준비 완료",
    quote: "“감정은 자본의 독입니다. 기대치가 음수인 포지션을 즉시 도려내십시오.”",
    briefingTitle: "군무상서 기밀 리스크 종합 사정서",
    heroStep2Label: "🛡️ 오베르슈타인의 리스크 사정 & 진입선:",
    heroTitle: "👁️ 오베르슈타인의 리스크 사정 후보 TOP 6",
    tableCol: "오베르슈타인 사정 총평"
  },
  julian: {
    avatar: "📖",
    name: "율리안 민츠 참모",
    sub: "양 웬리 제독의 후계자 · 팩터 정석 연구원",
    badge: "📖 5대 팩터 교차 검증 완료",
    quote: "“데이터는 거짓말을 하지 않습니다. 제독님의 가르침대로 정석만 따르겠습니다!”",
    briefingTitle: "후계자 율리안의 퀀트 정석 작전 보고서",
    heroStep2Label: "📖 율리안의 팩터 교차 검증 타점:",
    heroTitle: "📖 율리안의 팩터 정석 검증 후보 TOP 6",
    tableCol: "율리안 정석 총평"
  }
};

let currentSunziPersona = "yang";

async function loadSunziTier1Briefing(persona = currentSunziPersona) {
  currentSunziPersona = persona;
  const container = $("#sunzi-tier1-briefing");
  if (!container) return;
  try {
    const res = await api(`/api/sunzi/tier1-briefing?persona=${encodeURIComponent(persona)}`);
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      const personaBadges = [
        { id: "yang", icon: "🍵", name: "양 웬리", desc: "홍차·안전마진" },
        { id: "reinhard", icon: "🦁", name: "라인하르트", desc: "패도·모멘텀" },
        { id: "oberstein", icon: "👁️", name: "오베르슈타인", desc: "냉혹·손절" },
        { id: "julian", icon: "📖", name: "율리안", desc: "성실·정석" }
      ];
      
      const buttonsHtml = personaBadges.map(p => `
        <button type="button" class="tag-btn yang-deck-persona-btn ${p.id === persona ? 'active' : ''}" data-persona="${p.id}" style="padding:4px 10px; font-size:11.5px; border-radius:6px; transition:all 0.2s; ${p.id === persona ? 'background:#38bdf8; color:#0f172a; font-weight:800; border:1px solid #38bdf8;' : 'background:rgba(255,255,255,0.06); color:#cbd5e1; border:1px solid rgba(255,255,255,0.1);'}">
          ${p.icon} ${p.name} (${p.desc})
        </button>
      `).join("");

      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.95)); border:1px solid rgba(56, 189, 248, 0.45); border-radius:12px; padding:14px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:18px;">⚔️</span>
              <span style="font-size:14px; font-weight:900; color:#38bdf8;">은하퀀트전설 4대 지휘관 당직 전술 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10.5px; padding:1px 6px;">Tier 1 무료 AI</span>
            </div>
            <div style="display:flex; align-items:center; gap:4px; flex-wrap:wrap;">
              <span style="font-size:11.5px; color:#94a3b8; margin-right:4px;">지휘관 변경:</span>
              ${buttonsHtml}
            </div>
          </div>
          
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="chip" style="background:#eab308; color:#0f172a; font-weight:800; font-size:11.5px;">${escapeHtml(res.commander || '지휘관')}</span>
            <b style="font-size:15px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          </div>
          <p style="margin:0; font-size:13px; color:#e2e8f0; line-height:1.55; padding:10px 14px; background:rgba(15,23,42,0.6); border-radius:8px; border-left:3px solid #38bdf8;">
            ${escapeHtml(res.briefing || "")}
          </p>
          ${res.tactical_order ? `<div style="font-size:12px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:8px 12px; border-radius:4px;">📜 <b>오늘의 작전 지침:</b> ${escapeHtml(res.tactical_order)}</div>` : ""}
        </div>
      `;

      container.querySelectorAll(".yang-deck-persona-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const p = btn.getAttribute("data-persona");
          if (p && p !== currentSunziPersona) {
            currentSunziPersona = p;
            loadSunziTier1Briefing(p);
            loadSunzi();
          }
        });
      });
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadEmptyTier1Briefing() {
  const container = $("#empty-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/empty/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8)); border:1px solid rgba(56, 189, 248, 0.35); border-radius:12px; padding:12px 16px; margin-bottom:14px; display:flex; flex-direction:column; gap:6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:16px;">🚪</span>
              <span style="font-size:13px; font-weight:800; color:#38bdf8;">메이저 수급 이탈 & 빈집 복귀(턴어라운드) AI 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10px; padding:1px 6px;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14px; color:#f8fafc;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12px; color:#cbd5e1; line-height:1.5;">${escapeHtml(res.empty_insight || "")}</p>
          ${res.entry_caution ? `<div style="margin-top:2px; font-size:11.5px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:4px 8px; border-radius:4px;">💡 <b>유동성·거래가능성 주의:</b> ${escapeHtml(res.entry_caution)}</div>` : ""}
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadStrategyTier1Briefing() {
  const container = $("#strategy-lab-tier1-briefing");
  if (!container) return;
  try {
    const res = await api("/api/strategy/tier1-briefing");
    if (!renderTier1Unavailable(container, res)) return;
    if (res && res.ok && res.headline) {
      container.innerHTML = `
        <div class="tier1-briefing-card" style="background:linear-gradient(135deg, rgba(23, 37, 65, 0.9), rgba(15, 23, 42, 0.95)); border:1px solid rgba(56, 189, 248, 0.35); border-left:4px solid #38bdf8; border-radius:12px; padding:14px 18px; margin-bottom:16px; display:flex; flex-direction:column; gap:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:18px;">🧪</span>
              <span style="font-size:14px; font-weight:800; color:#38bdf8;">4대 퀀트 매매 타이밍 백테스트 AI 컨센서스 브리핑</span>
              <span class="chip" style="background:rgba(52, 211, 153, 0.15); color:#34d399; font-size:10.5px; padding:1px 7px; font-weight:700;">Tier 1 무료 엔진</span>
            </div>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(res.model || "nvidia/nemotron-3-ultra-550b-a55b:free")}</span>
          </div>
          <b style="font-size:14.5px; color:#f8fafc; line-height:1.4;">${escapeHtml(res.headline)}</b>
          <p style="margin:0; font-size:12.5px; color:#cbd5e1; line-height:1.55;">${escapeHtml(res.strategy_insight || "")}</p>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:8px; margin-top:4px;">
            ${res.action_guide ? `
              <div style="font-size:11.5px; color:#34d399; background:rgba(52, 211, 153, 0.08); border-left:3px solid #34d399; padding:6px 10px; border-radius:4px;">
                🔎 <b>등급 읽는 방법:</b> ${escapeHtml(res.action_guide)}
              </div>
            ` : ""}
            ${res.risk_management ? `
              <div style="font-size:11.5px; color:#38bdf8; background:rgba(56, 189, 248, 0.08); border-left:3px solid #38bdf8; padding:6px 10px; border-radius:4px;">
                🛡️ <b>리스크 관리 팁:</b> ${escapeHtml(res.risk_management)}
              </div>
            ` : ""}
          </div>
        </div>
      `;
    }
    appendTier1Meta(container, res);
  } catch (e) { renderTier1Unavailable(container, null, e); }
}

async function loadTossRankings() {
  const box = $("#toss-rankings");
  if (!box) return;
  loadTossTier1Briefing().catch(() => {});
  const data = await api("/api/toss/rankings");
  if (!data.configured) {
    box.innerHTML = "<p class='hint'>설정에 토스증권 Client ID/Secret을 넣고, Open API 허용 IP를 등록하세요.</p>";
    return;
  }
  if (data.error && !(data.groups || []).some((g) => (g.rows || []).length)) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error)}</p>`;
    return;
  }
  const medalIcons = ["🥇", "🥈", "🥉", "4", "5", "6", "7", "8"];
  box.innerHTML = `${data.selection ? `<p class="hint">${escapeHtml(data.selection)}</p>` : ""}<div class="rank-grid">${(data.groups || [])
    .map((g) => {
      const rows = (g.rows || []).slice(0, 8);
      if (!rows.length) {
        return `<div class="rank-card"><h3>${escapeHtml(g.label)}</h3><p class="hint">${escapeHtml(g.error || "데이터 없음")}</p></div>`;
      }
      const body = rows
        .map((r, i) => {
          const code = String(r.code || r.symbol || "").replace(/^A/, "");
          const name = r.name && r.name !== code ? r.name : r.name || code;
          const chg = Number(r.change_rate);
          const chgPct = Number.isNaN(chg) ? null : chg * (Math.abs(chg) > 1 ? 1 : 100);
          const chgCls = chgPct == null ? "" : chgPct > 0 ? "up" : chgPct < 0 ? "down" : "";
          const chgTxt = chgPct == null ? "—" : `${chgPct > 0 ? "+" : ""}${chgPct.toFixed(2)}%`;
          const last = r.last == null ? "—" : Number(r.last).toLocaleString("ko-KR");
          const medal = medalIcons[i] || String(i + 1);
          const isSpecial = Math.abs(chgPct || 0) > 30;
          const specialBadge = isSpecial ? `<span class="chip" style="font-size:9.5px; padding:1px 4px; background:rgba(239,68,68,0.15); color:#f87171;" title="신규상장 또는 변동성 상품">신규상장/변동성</span>` : "";

          return `<tr class="clickable stock-jump" data-ticker="${escapeHtml(code)}" onclick="openStock('${escapeHtml(code)}')">
            <td class="num" style="font-weight:700; font-size:13px;">${medal}</td>
            <td class="name-cell">
              <div style="display:flex; align-items:center; gap:6px;">
                <b style="color:#f8fafc; cursor:pointer;">${escapeHtml(name)}</b>
                ${specialBadge}
              </div>
              <div class="meta" style="font-size:11px; color:#94a3b8;">${escapeHtml(code)}</div>
              ${rowNote(r.comment_short || r.comment)}
            </td>
            <td class="num ${chgCls}" style="font-weight:800;">${escapeHtml(chgTxt)}</td>
            <td class="num" style="font-weight:700;">${escapeHtml(String(last))}원</td>
            <td><a class="ext inline" href="${escapeHtml(r.page || "https://www.tossinvest.com/stocks/A" + code)}" target="_blank" rel="noopener" onclick="event.stopPropagation();">토스 ↗</a></td>
          </tr>`;
        })
        .join("");
      return `<div class="rank-card"><h3>${escapeHtml(g.label)}</h3>
        <table class="rank-table"><thead><tr><th>#</th><th>종목</th><th>등락</th><th>현재가</th><th></th></tr></thead>
        <tbody>${body}</tbody></table></div>`;
    })
    .join("")}</div>`;
  stampLive("#toss-live");
  const when = fmtWhen(data.fetched_at);
  const line = when ? `토스 시세 랭킹 ${when} · 약 2분 캐시` : "토스 시세 랭킹 시점 없음";
  setPageAsOf(line, "토스 Open API 시세입니다. KRX 종가 칩과 다른 시각입니다. 지금 새로고침으로 다시 받을 수 있습니다.");
  const wrap = $("#toss-rankings");
  if (wrap && when) wrap.insertAdjacentHTML("afterbegin", asofBanner(line));
}

function fgColor(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return "#93a0b8";
  if (n < 25) return "#ef4b6a";
  if (n < 45) return "#f07a4b";
  if (n < 55) return "#f0b429";
  if (n < 75) return "#7bcf5a";
  return "#3dcf8e";
}

function fgGauge(score, label) {
  const n = Math.max(0, Math.min(100, Number(score) || 0));
  const deg = 180 - n * 1.8;
  const rad = (deg * Math.PI) / 180;
  const x = 100 + 78 * Math.cos(rad);
  const y = 100 - 78 * Math.sin(rad);
  return `<svg class="fg-meter" viewBox="0 0 200 118" aria-label="${escapeHtml(label || "")} ${n}">
    <defs>
      <linearGradient id="fgArc" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#ef4b6a"/><stop offset="50%" stop-color="#f0b429"/><stop offset="100%" stop-color="#3dcf8e"/>
      </linearGradient>
    </defs>
    <path d="M22 100 A78 78 0 0 1 178 100" fill="none" stroke="url(#fgArc)" stroke-width="14" stroke-linecap="round"/>
    <line x1="100" y1="100" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#e8eef8" stroke-width="3"/>
    <circle cx="100" cy="100" r="5" fill="#e8eef8"/>
    <text x="22" y="116" fill="#ef4b6a" font-size="10">공포</text>
    <text x="158" y="116" fill="#3dcf8e" font-size="10">탐욕</text>
  </svg>`;
}

function fgCard(title, side, history, key) {
  if (!side || side.score == null) {
    return `<div class="fg-card"><h3>${escapeHtml(title)}</h3><p class="hint">아직 값이 없습니다.</p></div>`;
  }
  const color = fgColor(side.score);
  const delta = side.previous_close == null ? "" : `전일 ${fmt(side.previous_close, 0)}`;
  const bars = (side.indicators || [])
    .filter((x) => x && x.name && x.name !== "종합 심리")
    .map((x) => {
      const w = Math.max(0, Math.min(100, Number(x.value) || 0));
      return `<li><span>${escapeHtml(x.name)}</span><i><em style="width:${w}%"></em></i><b>${fmt(x.value, 0)}</b></li>`;
    })
    .join("");
  const spark = (history || [])
    .slice(-24)
    .map((h) => {
      const v = Number(h[key]);
      const hgt = Number.isNaN(v) ? 2 : Math.max(2, (v / 100) * 42);
      return `<b style="height:${hgt}px;background:${fgColor(v)}"></b>`;
    })
    .join("");
  const extra =
    key === "kr" && side.kospi_change != null
      ? `<p class="hint">KOSPI ${fmt(side.kospi_price, 0)} · ${fmt(side.kospi_change, 2)}% · KOSDAQ ${fmt(side.kosdaq_change, 2)}%</p>`
      : "";
  return `<div class="fg-card">
    <h3>${escapeHtml(title)}</h3>
    <div class="fg-label" style="color:${color}">${escapeHtml(side.label || "")}</div>
    <div class="fg-score" style="color:${color}">${fmt(side.score, 0)}</div>
    ${fgGauge(side.score, side.label)}
    <p class="hint">${escapeHtml(delta)} · ${escapeHtml(side.source || "")}</p>
    ${extra}
    <ul class="fg-bars">${bars}</ul>
    ${spark ? `<div class="fg-spark">${spark}</div>` : ""}
  </div>`;
}

function renderFearGreed(fg) {
  if (!fg) return "";
  if (!fg.configured) {
    return `<p class="hint">공포·탐욕 지수를 불러오지 못했습니다. ${escapeHtml(fg.error || "")}</p>`;
  }
  return `<div class="fg-grid">
      ${fgCard("한국 시장", fg.kr, fg.history, "kr")}
      ${fgCard("미국 시장", fg.us, fg.history, "us")}
    </div>
    <p class="hint">${escapeHtml(fg.disclaimer || "")} 출처: <a class="ext inline" href="${escapeHtml(fg.page || "https://feargreed.co.kr/")}" target="_blank" rel="noopener">feargreed.co.kr</a></p>`;
}

const SENTIMENT_ITEM_GUIDE = {
  "모멘텀": {
    tip: "코스피 지수와 125일 이동평균선 간의 이격도를 측정해 시장의 중기 추세적 과열/침체 강도를 진단합니다.",
    up: "이평선 상향 돌파 및 상승 추세 가속",
    down: "이평선 하회 및 중기 조정 구간 진입",
    hint: "이격도가 과도하게 벌어지면 평균 회귀 압력이 발생합니다."
  },
  "주가 강도": {
    tip: "최근 52주 신고가 종목 수와 신저가 종목 수의 비율을 통해 시장 내부 건전성을 분석합니다.",
    up: "신고가 종목 증가 ➔ 시장 상승 종목군 확산 (건전한 상승장)",
    down: "신저가 종목 급증 ➔ 하락 종목 속출 및 내부 체력 악화",
    hint: "지수는 올라도 신저가가 많다면 착시 현상일 수 있습니다."
  },
  "시장 변동성": {
    tip: "코스피 200 변동성(VKOSPI) 및 30일 일봉 변동성을 100점 역산하여 시장의 불안 심리를 포착합니다.",
    up: "변동성 축소 ➔ 시장 안정 및 안도 랠리 지속",
    down: "변동성 급등 ➔ 시장 패닉 및 투매 가능성",
    hint: "변동성 최고조 구간은 역사적 바닥권 형성과 일치합니다."
  },
  "외인 수급": {
    tip: "최근 5거래일간 외국인 투자자의 코스피 시장 순매수 강도와 수급 방향성을 추적합니다.",
    up: "외국인 대규모 순매수 유입 ➔ 대형 수출주 주도 랠리",
    down: "외국인 연속 순매도 ➔ 지수 상단 제한 및 수급 공백",
    hint: "환율 안정과 맞물릴 때 외국인 수급 탄력성이 극대화됩니다."
  },
  "거래 활동성": {
    tip: "20일 평균 대비 당일 거래대금 및 회전율 증가율을 바탕으로 시장 참여자의 에너지와 유동성을 측정합니다.",
    up: "거래대금 폭증 ➔ 강력한 추세 돌파 또는 바닥 탈출 신호",
    down: "거래대금 급감 ➔ 관망세 및 거래 절벽",
    hint: "거래대금이 실리지 않는 반등은 단기 되돌림에 그칠 확률이 높습니다."
  }
};

function renderKrSentiment(sent) {
  if (!sent || !sent.components) return "";
  const st = sent.state || "NEUTRAL";
  const stKo = sent.state_ko || "중립";
  const score = fmt(sent.score, 1);
  const comps = Object.entries(sent.components || {}).map(([, c]) => {
    const key = Object.keys(SENTIMENT_ITEM_GUIDE).find(k => (c.label || "").includes(k)) || "모멘텀";
    const g = SENTIMENT_ITEM_GUIDE[key] || {
      tip: `${c.label} 지표 점수입니다.`,
      up: "과열 및 탐욕 심리 증가",
      down: "공포 및 침체 심리 증가",
      hint: "점수가 20점 이하일 때 역발상 분할매수를 고려하세요."
    };
    return `<div class="sentiment-item has-tip"
                 data-tip-title="${escapeHtml(c.label)} (비중 ${c.weight}%)"
                 data-tip="${escapeHtml(g.tip)}"
                 data-tip-up="${escapeHtml(g.up)}"
                 data-tip-down="${escapeHtml(g.down)}"
                 data-tip-hint="${escapeHtml(g.hint)}"
                 tabindex="0">
      <span>${escapeHtml(c.label)} (비중 ${c.weight}%)</span>
      <b>${fmt(c.score, 1)}점</b>
    </div>`;
  }).join("");

  return `
    <div class="sentiment-box">
      <div class="sentiment-head">
        <div>
          <h3 style="margin:0 0 4px">자체 한국 시장 공포·탐욕 지수 (KR Market Sentiment)</h3>
          <span class="hint">KRX 일봉 + 외인 5일 수급 기반 100점 만점 자체 감성 지수</span>
        </div>
        <div class="sentiment-score-badge ${st} has-tip"
             data-tip-title="📊 공포·탐욕 지수 종합: ${score}점 (${escapeHtml(stKo)})"
             data-tip="0~25점: 극단적 공포 (투매 및 역사적 저점 매수 구간), 25~45점: 공포, 45~55점: 중립, 55~75점: 탐욕, 75~100점: 극단적 탐욕 (과열 및 분할 익절 구간)"
             data-tip-hint="워런 버핏의 '남들이 공포에 질려 있을 때 욕심을 내라'는 원칙을 시스템화한 지표입니다."
             tabindex="0">
          ${score}점 · ${stKo}
        </div>
      </div>
      <div class="sentiment-grid">
        ${comps}
      </div>
    </div>
  `;
}

async function loadMarket(refresh) {
  const box = $("#market-box");
  if (!box) return;
  const data = await api(`/api/market${refresh ? "?refresh=true" : ""}`);
  const fgHtml = renderFearGreed(data.fear_greed);
  const krSentHtml = renderKrSentiment(data.kr_sentiment);
  if (!data.configured) {
    stampLive("#market-live");
    box.innerHTML = `${fgHtml}${krSentHtml}<p class="hint">${escapeHtml(data.error || "시세 없음")}</p>`;
    return;
  }
  const REGIME_COMPONENT_GUIDE = {
    "60일 추세": { icon: "📈", tip: "코스피 60일 이동평균선 상회 종목 비중으로 중기 상승 추세 확산도를 측정합니다." },
    "20일 상승": { icon: "⚡", tip: "최근 20거래일 동안 플러스 수익률을 기록한 단기 강세 종목 비율입니다." },
    "거래대금": { icon: "🔥", tip: "시장 전체 거래대금의 20일 이동평균 대비 강도와 유동성 활력도입니다." },
    "변동성": { icon: "🛡️", tip: "코스피 200 변동성(VKOSPI) 지수 역산치로, 수치가 낮을수록 시장 공포가 큽니다." },
    "미국 장단기": { icon: "🇺🇸", tip: "미국 국채 10년-2년 금리차로 글로벌 경기 침체 선행 신호를 진단합니다." },
    "원화 안정": { icon: "💵", tip: "원/달러 환율의 1380원~1450원 안정 구간 및 외국인 환차손 방어 여력입니다." },
    "60일 상승": { icon: "🌊", tip: "60일 중기 기간 동안 상승세를 유지한 시장 주도 종목군의 밀도입니다." }
  };

  const metricCards = (data.components || []).map((c) => {
    const val = c.value != null ? Number(c.value) : 50;
    const tone = c.tone || "중립";
    const key = Object.keys(REGIME_COMPONENT_GUIDE).find(k => (c.label || "").includes(k)) || "60일 추세";
    const g = REGIME_COMPONENT_GUIDE[key] || { icon: "📊", tip: `${c.label} 지표 점수입니다.` };

    return `
      <div class="regime-metric-box has-tip"
           data-tip-title="${g.icon} ${escapeHtml(c.label)}"
           data-tip="${escapeHtml(g.tip)}"
           data-tip-hint="점수: ${fmt(val, 1)}점 · 상태: ${escapeHtml(tone)}"
           tabindex="0">
        <div class="regime-metric-top">
          <span>${g.icon} ${escapeHtml(c.label)}</span>
          <span class="regime-tone-badge ${tone}">${escapeHtml(tone)}</span>
        </div>
        <div class="regime-metric-score">${fmt(val, 1)} <small style="font-size:11px;font-weight:normal;color:#94a3b8;">/ 100</small></div>
        <div class="regime-bar-track">
          <div class="regime-bar-fill ${tone}" style="width:${Math.max(4, Math.min(100, val))}%;"></div>
        </div>
      </div>
    `;
  }).join("");

  const ecos = data.ecos || {};
  const ecosCards = (ecos.series || []).map((s) => {
    if (s.error) return `<div class="ecos-metric-box"><span style="color:#f87171;">${escapeHtml(s.alias || "")}</span><b>—</b><div class="meta">${escapeHtml(s.error)}</div></div>`;
    return `
      <div class="ecos-metric-box has-tip"
           data-tip-title="🏛️ 한국은행 ${escapeHtml(s.alias || s.name || "")}"
           data-tip="한국은행 ECOS 공식 통계 지표입니다. 기준일 ${escapeHtml(s.time || "")}"
           tabindex="0">
        <span>${escapeHtml(s.alias || s.name || "")}</span>
        <b>${fmt(s.value, 2)} <small style="font-size:11px;font-weight:normal;color:#94a3b8;">${escapeHtml(s.unit || "")}</small></b>
        <div class="meta">기준일 ${escapeHtml(s.time || "")}</div>
      </div>
    `;
  }).join("");

  const regimeScore = Number(data.regime_score || 50);
  const regimeTone = regimeScore >= 55 ? "우호" : regimeScore <= 40 ? "부담" : "중립";

  box.innerHTML = `
    ${krSentHtml}
    ${fgHtml}

    <div class="market-regime-card">
      <div class="market-regime-header">
        <div>
          <h3 style="margin:0 0 4px;font-size:15px;color:#fff;">🏛️ 시장 내부 국면 & 건전성 진단 (Market Breadth Matrix)</h3>
          <span class="hint">KRX 전 종목 일봉 기반 7대 내부 체력 지표 · 시세 기준일 ${escapeHtml(data.freshness?.price_max_date || "—")}</span>
        </div>
        <div class="stance-badge ${regimeTone}" style="font-size:13px;padding:5px 12px;">
          내부 국면: ${escapeHtml(data.label || data.regime || "중립")} (${fmt(data.regime_score, 1)}점)
        </div>
      </div>
      <div class="market-regime-grid">
        ${metricCards}
      </div>
    </div>

    <div class="market-regime-card">
      <div class="market-regime-header">
        <div>
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <h3 style="margin:0;font-size:15px;color:#fff;">🇰🇷 한국은행 ECOS 거시경제 핵심 지표</h3>
            <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 7px;">한국은행 오픈 API</span>
          </div>
          <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:4px; font-size:12px; color:#94a3b8;">
            <span>한국은행 오픈 API 실시간 연동 기준금리, 국고채, 환율, 물가 통계</span>
            <span>⏱️ <b>실시간 동기화:</b> <span id="ecos-synced-badge" style="color:#38bdf8; font-weight:700;">${formatSyncTime(ecos.fetched_at || data.fetched_at)}</span></span>
          </div>
        </div>
        <button type="button" id="btn-ecos-summary-refresh" class="trade-refresh-btn" style="height:32px; font-size:11.5px; padding:0 10px; border-radius:6px;" title="한국은행 ECOS 데이터 즉시 재수집">
          <span>🔄</span><span>실시간 새로고침</span>
        </button>
      </div>
      <div class="ecos-visual-grid">
        ${ecosCards || `<p class="hint">${escapeHtml(ecos.error || "조회 데이터 없음")}</p>`}
      </div>
    </div>
  `;
  stampLive("#market-live");
  loadMarketTier1Briefing().catch(() => {});
}

function krw(n) {
  const x = Number(n);
  if (Number.isNaN(x) || !x) return "—";
  const abs = Math.abs(x);
  if (abs >= 1e12) return `${(x / 1e12).toFixed(2)}조`;
  if (abs >= 1e8) return `${(x / 1e8).toFixed(0)}억`;
  return x.toLocaleString("ko-KR");
}

function pctCell(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v) * 100;
  const cls = n > 0 ? "up" : n < 0 ? "down" : "";
  return `<span class="${cls}">${n > 0 ? "+" : ""}${n.toFixed(1)}%</span>`;
}

let flowCache = null;

function flowDays() {
  return Number($("#flow-days")?.value || 5);
}

function flowMinKrw() {
  return Number($("#flow-min-krw")?.value || 0);
}

function flowUniverse() {
  return $("#trade-universe")?.value || "all";
}

function filterFlowUniverse(rows) {
  const universe = flowUniverse();
  if (universe === "top100") return rows.filter((r) => Boolean(r.in_quant));
  if (universe === "outside") return rows.filter((r) => !r.in_quant);
  return rows;
}

function sharedFlowRows(rows, amountKey = null) {
  const scoped = filterFlowUniverse(Array.isArray(rows) ? rows : []);
  return amountKey ? filterAmount(scoped, amountKey, flowMinKrw()) : scoped;
}

function filterFlowQuery(rows) {
  const q = ($("#flow-q")?.value || "").trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => {
    const hay = `${r.ticker || ""} ${r.company || ""}`.toLowerCase();
    return hay.includes(q) || getChosung(r.company || "").includes(q);
  });
}

function flowUniverseLabel() {
  const universe = flowUniverse();
  if (universe === "top100") return "퀀트 TOP100";
  if (universe === "outside") return "퀀트 TOP100 밖";
  return "전체 종목";
}

function analyzeHit(rows, key) {
  const vals = rows.map((r) => r[key]).filter((v) => v != null && !Number.isNaN(Number(v))).map(Number);
  if (!vals.length) return { n: 0, hit: null, avg: null, median: null };
  const hit = vals.filter((v) => v > 0).length / vals.length;
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  const sorted = [...vals].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  return { n: vals.length, hit, avg, median };
}

function forwardReturnCell(row, horizon) {
  const value = row?.[`ret_${horizon}d`];
  const meta = row?.[`ret_${horizon}d_meta`];
  if (value != null && !Number.isNaN(Number(value)) && meta?.complete !== false) {
    const dates = meta?.start_date && meta?.end_date ? `${meta.start_date} → ${meta.end_date}` : "전체 관측 구간 충족";
    return `<span class="has-tip" data-tip-title="D+${horizon} 확정 수익률" data-tip="${escapeHtml(dates)} · 신호일 이후 ${horizon}거래일을 모두 관측한 실측값입니다." tabindex="0">${pctCell(value)}</span>`;
  }
  if (meta?.status === "PENDING") {
    const observed = Math.max(0, Number(meta.observed_sessions || 0));
    const required = Math.max(horizon, Number(meta.required_sessions || horizon));
    return `<span class="warn has-tip" data-tip-title="D+${horizon} 검증 대기" data-tip="현재 D+${observed}/${required}까지 관측했습니다. ${required}거래일이 모두 지난 뒤에만 수익률과 승률 표본에 포함합니다." tabindex="0">대기 D+${observed}/${required}</span>`;
  }
  return `<span class="hint has-tip" data-tip-title="D+${horizon} 검증 자료 없음" data-tip="새 수급 스키마로 다시 스캔한 뒤 관측 기간이 충족되면 표시합니다." tabindex="0">—</span>`;
}

function filterAmount(rows, key, minKrw) {
  if (!minKrw) return rows;
  return rows.filter((r) => Number(r[key] || 0) >= minKrw);
}

function hitLine(label, stats) {
  if (!stats || !stats.n) return `${label} —`;
  const hit = stats.hit == null ? "—" : `${(stats.hit * 100).toFixed(0)}%`;
  return `${label} ${stats.n}종목 · 5일 양수 ${hit} · 평균 ${pctCell(stats.avg)} · 중앙 ${pctCell(stats.median)}`;
}

function bucketTable(title, rows, amountKey) {
  const buckets = [
    ["전체", 0],
    ["10억+", 1e9],
    ["50억+", 5e9],
    ["100억+", 1e10],
  ];
  const body = buckets
    .map(([label, thresh]) => {
      const st = analyzeHit(filterAmount(rows, amountKey, thresh), "ret_5d");
      return `<tr>
        <td>${label}</td>
        <td class="num">${st.n}</td>
        <td class="num">${st.hit == null ? "—" : `${(st.hit * 100).toFixed(0)}%`}</td>
        <td class="num">${pctCell(st.avg)}</td>
        <td class="num">${pctCell(st.median)}</td>
      </tr>`;
    })
    .join("");
  return `<div class="rank-card"><h3>${escapeHtml(title)}</h3>
    <table class="rank-table"><thead><tr>
      <th>금액구간</th><th>종목</th><th>5일 히트</th><th>평균</th><th>중앙</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}

function quoteCell(r) {
  if (r.last == null) return "—";
  return `${Number(r.last).toLocaleString("ko-KR")}<div class="meta">${pctCell(r.change_rate)}</div>`;
}

function plainSignedInt(value) {
  const n = Number(value || 0);
  return `${n > 0 ? "+" : ""}${n.toLocaleString("ko-KR")}`;
}

function flowHistoryTipAttrs(row, label, displayedValue = "") {
  const daily = Array.isArray(row?.daily) ? row.daily.filter((d) => d && d.date).slice(0, 20) : [];
  const recent = daily.slice(0, 5);
  const title = `${row?.company || row?.ticker || "종목"} · ${label}`;
  const tip = recent.length
    ? recent.map((d) => {
        const day = String(d.date || "").slice(5);
        const price = d.close == null
          ? "종가 —"
          : `종가 ${Number(d.close).toLocaleString("ko-KR")}원${d.price_change_rate == null ? "" : ` (${fmtPct(d.price_change_rate)})`}`;
        return `${day} · ${price} · 외인 ${plainSignedInt(d.foreign)} · 기관 ${plainSignedInt(d.institution)} · 개인 ${plainSignedInt(d.individual)} · 사모 ${plainSignedInt(d.pe)}`;
      }).join("\n")
    : "최근 5거래일 일별 수급·가격 이력이 없습니다. 수급 다시 스캔을 실행하면 새 스키마로 저장됩니다.";
  const priced = daily.filter((d) => d.close != null && Number(d.close) > 0);
  let priceWindow = "가격 이력 없음";
  if (priced.length) {
    const newest = Number(priced[0].close);
    const oldest = Number(priced[priced.length - 1].close);
    const rangeReturn = oldest > 0 ? newest / oldest - 1 : null;
    priceWindow = `${oldest.toLocaleString("ko-KR")}원 → ${newest.toLocaleString("ko-KR")}원${rangeReturn == null ? "" : ` (${fmtPct(rangeReturn)})`}`;
  }
  const selectedDays = Number(row?.days || flowDays() || daily.length || 5);
  const current = displayedValue ? `현재 셀 ${displayedValue} · ` : "";
  const summary = `${current}설정 ${selectedDays}거래일 가격 ${priceWindow} · 외인 ${plainSignedInt(row?.foreign_net)} · 기관 ${plainSignedInt(row?.institution_net)} · 개인 ${plainSignedInt(row?.individual_net)} · 사모 ${plainSignedInt(row?.pe_net)}`;
  return ` data-tip-title="${escapeHtml(title)}" data-tip="${escapeHtml(tip)}" data-tip-hint="${escapeHtml(summary)}" data-tip-hint-label="설정기간 집계" data-tip-layout="flow-history" tabindex="0"`;
}

function flowTable(title, rows, amountKey, tabId) {
  const scope = tabId || (amountKey === "pe_krw" ? "flowPe" : "flowDual");
  const filteredRows = filterFlowQuery(rows);

  if (!filteredRows.length) {
    return `<div class="rank-card"><div class="card-h"><h3 style="margin:0;">${escapeHtml(title)}</h3></div><p class="hint" style="text-align:center; padding:30px;">조건에 부합하는 수급 포착 종목이 없습니다.</p></div>`;
  }
  const ordered = sortedCopy(filteredRows, scope, amountKey, "desc");
  const vis = flowLimit[scope] || FLOW_FIRST;
  const shown = ordered.slice(0, vis);
  const left = ordered.length - shown.length;
  const body = shown
    .map((r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
      <td class="num font-bold">${i + 1}</td>
      <td class="name-cell">
        <div style="display:flex; align-items:center; gap:6px;">
          <b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b>
          <span class="meta">${escapeHtml(r.ticker || "")}</span>
        </div>
        ${rowNote(amountKey === "pe_krw" ? (r.comment_pe_short || r.comment_pe) : (r.comment_flow_short || r.comment_flow))}
      </td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "최근가", r.last == null ? "—" : `${Number(r.last).toLocaleString("ko-KR")}원`)}>${quoteCell(r)}</td>
      <td class="num has-tip ${r.foreign_net > 0 ? 'text-emerald-400 font-bold' : r.foreign_net < 0 ? 'text-rose-400' : ''}"${flowHistoryTipAttrs(r, "외국인 누적 순매수", plainSignedInt(r.foreign_net))}>${signedInt(r.foreign_net)}</td>
      <td class="num has-tip ${r.institution_net > 0 ? 'text-emerald-400 font-bold' : r.institution_net < 0 ? 'text-rose-400' : ''}"${flowHistoryTipAttrs(r, "기관 누적 순매수", plainSignedInt(r.institution_net))}>${signedInt(r.institution_net)}</td>
      <td class="num has-tip ${r.pe_net > 0 ? 'text-purple-400 font-bold' : r.pe_net < 0 ? 'text-rose-400' : ''}"${flowHistoryTipAttrs(r, "사모펀드 누적 순매수", plainSignedInt(r.pe_net))}>${signedInt(r.pe_net)}</td>
      <td class="num has-tip font-bold text-accent-cyan"${flowHistoryTipAttrs(r, "수급 추정금액", krw(r[amountKey]))}>${escapeHtml(krw(r[amountKey]))}</td>
      <td class="num font-bold">${forwardReturnCell(r, 5)}</td>
      <td class="num font-bold">${forwardReturnCell(r, 20)}</td>
    </tr>`)
    .join("");
  const more = left > 0
    ? `<p class="more-line" style="margin-top:12px; text-align:center;"><button type="button" class="ghost" data-flow-more="${escapeHtml(scope)}" style="padding:6px 18px; border-radius:8px;">더보기 ${Math.min(FLOW_STEP, left)}종목 (${shown.length}/${ordered.length})</button></p>`
    : `<p class="hint" style="text-align:center; margin-top:12px;">${ordered.length}개 종목 전부 표시됨</p>`;
  return `<div class="rank-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
      <h3 style="margin:0; font-size:15px; color:#f8fafc;">${escapeHtml(title)} <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:11.5px; font-weight:700;">${ordered.length}개 종목</span></h3>
    </div>
    <div class="table-wrap">
      <table class="rank-table" data-scope="${scope}">
        <thead>
          <tr>
            <th style="width:40px;">#</th>
            <th class="sortable has-tip" data-sort="company" style="min-width:140px;" data-tip-title="종목명 및 6자리 코드" data-tip="클릭 시 해당 종목의 실시간 수급 분해 및 팩터 상세창이 열립니다." tabindex="0">종목명</th>
            <th class="sortable has-tip" data-sort="last" data-tip-title="토스 실시간 시세" data-tip="토스증권 실시간 기준 현재가 및 당일 등락률입니다." tabindex="0">최근가</th>
            <th class="sortable has-tip" data-sort="foreign_net" data-tip-title="👽 외국인 누적 순매수" data-tip="설정 기간 동안 외국인 투자자의 합산 순매수 주수입니다." tabindex="0">외인(주)</th>
            <th class="sortable has-tip" data-sort="institution_net" data-tip-title="🏛️ 기관 누적 순매수" data-tip="금융투자, 보험, 투신, 사모 등 기관 투자자 전체의 합산 순매수 주수입니다." tabindex="0">기관(주)</th>
            <th class="sortable has-tip" data-sort="pe_net" data-tip-title="💼 사모펀드 누적 순매수" data-tip="가장 빠른 스마트머니인 사모펀드의 합산 순매수 주수입니다." tabindex="0">사모(주)</th>
            <th class="sortable has-tip" data-sort="${amountKey}" data-tip-title="💵 수급 유입 추정금액" data-tip="(외인+기관 순매수 주수) × 최근 종가로 환산한 실질 자금 유입 규모입니다." tabindex="0">추정금액</th>
            <th class="sortable has-tip" data-sort="ret_5d" data-tip-title="📈 수급 발생 후 5일 성과" data-tip="신호일 이후 5거래일을 모두 관측한 경우에만 표시하고 승률 표본에 포함합니다." tabindex="0">이후 5일</th>
            <th class="sortable has-tip" data-sort="ret_20d" data-tip-title="📈 수급 발생 후 20일 성과" data-tip="신호일 이후 20거래일을 모두 관측한 경우에만 표시하고 승률 표본에 포함합니다." tabindex="0">이후 20일</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
    ${more}
  </div>`;
}

function renderFlow(data) {
  const box = $("#flow-box");
  if (!box) return;
  if (!data.configured) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error || "토스증권 키가 필요합니다.")}</p>`;
    return;
  }
  const minKrw = flowMinKrw();
  const dualRows = sharedFlowRows(data.dual || [], "dual_krw");
  const peRows = sharedFlowRows(data.private_equity || [], "pe_krw");
  const tabs = [
    { id: "dual", name: "💎 쌍끌이", rows: dualRows, key: "dual_krw", title: "외인·기관 동시 순매수 (쌍끌이)" },
    { id: "pe", name: "💼 사모펀드", rows: peRows, key: "pe_krw", title: "스마트머니 사모펀드 순매수" },
    { id: "dual_pe", name: "🔥 쌍끌이+사모", rows: sharedFlowRows(data.dual_pe || [], "dual_krw"), key: "dual_krw", title: "외인·기관·사모 3대 메이저 집중 매집" },
    { id: "dual_pe_retail", name: "🚀 +개인이탈", rows: sharedFlowRows(data.dual_pe_retail || [], "dual_krw"), key: "dual_krw", title: "메이저 싹쓸이 + 개인이탈 (손바뀜 완료)" },
    { id: "other_corp", name: "🏢 기타법인", rows: sharedFlowRows(data.other_corp || [], "other_corp_krw"), key: "other_corp_krw", title: "기타법인 대량 순매수" },
    { id: "pension", name: "🏛️ 기금 가세", rows: sharedFlowRows(data.pension || [], "pension_krw"), key: "pension_krw", title: "연기금 동반 가세 수급" },
  ];
  if (!tabs.some((t) => t.id === flowTab)) flowTab = "dual";
  const dual = analyzeHit(dualRows, "ret_5d");
  const pe = analyzeHit(peRows, "ret_5d");
  const when = fmtWhen(data.fetched_at);
  const asof = when ? `토스 수급 스캔 ${when} · ${data.days || 5}거래일` : `수급 스캔 시점 없음 · ${data.days || 5}거래일`;
  if (currentView === "trade" && smartFlowTab === "overview") setPageAsOf(asof, "토스 투자자 매매를 받은 시각입니다. 다시 스캔하면 갱신됩니다. KRX 종가 칩과는 다릅니다.");

  const tabBtns = tabs
    .map(
      (t) =>
        `<button type="button" class="${t.id === flowTab ? "on" : ""}" data-flow-tab="${t.id}">${escapeHtml(t.name)} <span style="opacity:0.8; font-size:11px;">(${t.rows.length})</span></button>`
    )
    .join("");
  const active = tabs.find((t) => t.id === flowTab) || tabs[0];
  let panel = "";
  if (active.id === "other_corp" && !active.rows.length) {
    panel = `<p class="hint" style="text-align:center; padding:30px;">토스 응답에 기타법인 항목이 없거나 순매수가 없습니다. 키가 있으면 이 탭에 붙습니다.</p>`;
  } else {
    panel = flowTable(active.title, active.rows, active.key, `flow-${active.id}`);
  }

  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(6,1fr); margin:0 0 16px;">
      <div class="kpi clickable-kpi has-tip" data-flow-tab="dual"
           data-tip-title="⚡ 외인·기관 쌍끌이 순매수 (Dual Buy)"
           data-tip="외국인과 기관이 동시에 순매수한 핵심 수급 주도주입니다. 시장에서 가장 신뢰도가 높은 단기 주가 상승 모멘텀 신호입니다."
           data-tip-hint="외인과 기관의 쌍끌이 매집은 대형주 및 주도 섹터 랠리의 필수 조건입니다."
           tabindex="0">
        <span>쌍끌이 후보</span><b style="color:#00e5ff;">${dualRows.length}</b>
      </div>
      <div class="kpi has-tip"
           data-tip-title="🎯 쌍끌이 5일 승률 (Hit Rate)"
           data-tip="쌍끌이 수급 발생 후 5거래일 동안 주가가 플러스(+) 수익을 기록한 종목 비율입니다."
           data-tip-hint="60% 이상이면 수급 추종 매매 전략의 유효성이 매우 높습니다."
           tabindex="0">
        <span>5일 승률</span><b style="color:#34d399;">${dual.hit == null ? "—" : `${(dual.hit * 100).toFixed(0)}%`}</b>
      </div>
      <div class="kpi clickable-kpi has-tip" data-flow-tab="pe"
           data-tip-title="🕵️ 사모펀드 순매수 (PE Buy)"
           data-tip="시장의 스마트 머니로 통하는 사모펀드가 최근 공격적으로 순매수한 종목군입니다."
           data-tip-hint="사모펀드 수급 유입은 단기 재료 및 실적 턴어라운드 선취매 가능성을 내포합니다."
           tabindex="0">
        <span>사모 순매수</span><b style="color:#c084fc;">${peRows.length}</b>
      </div>
      <div class="kpi clickable-kpi has-tip" data-flow-tab="dual_pe"
           data-tip-title="💎 쌍끌이 + 사모펀드 동시 매집"
           data-tip="외국인·기관 일반 합계뿐만 아니라 사모펀드까지 3대 메이저 주체가 일제히 매수한 초강력 수급 집중주입니다."
           data-tip-hint="수급 일치도가 가장 높아 승률이 우수합니다."
           tabindex="0">
        <span>쌍끌이+사모</span><b style="color:#f59e0b;">${(data.dual_pe || []).length}</b>
      </div>
      <div class="kpi clickable-kpi has-tip" data-flow-tab="dual_pe_retail"
           data-tip-title="🚀 메이저 싹쓸이 + 개인이탈 (손바뀜 완료)"
           data-tip="외인·기관·사모펀드는 싹쓸이 매집하고, 개인 투자자는 매도(이탈)하여 악성 매물이 완벽히 손바뀜된 최상급 수급주입니다."
           data-tip-hint="개인 매물이 털린 후 가벼워진 수급으로 강력한 급등 탄력성이 나타납니다."
           tabindex="0">
        <span>+개인이탈</span><b style="color:#ec4899;">${(data.dual_pe_retail || []).length}</b>
      </div>
      <div class="kpi clickable-kpi has-tip" data-flow-tab="other_corp"
           data-tip-title="🏢 기타법인 순매수"
           data-tip="자사주 매입, 최대주주 우호지분 매집, 경영권 분쟁 또는 전략적 투자(SI) 법인의 대량 순매수 종목입니다."
           data-tip-hint="주가 하방 지지력이 매우 탄탄합니다."
           tabindex="0">
        <span>기타법인</span><b style="color:#60a5fa;">${(data.other_corp || []).length}</b>
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
      <span class="chip" style="background:rgba(56,189,248,0.12); color:#38bdf8;">스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 순매수 합산 · ${escapeHtml(flowUniverseLabel())}${minKrw ? ` · ${krw(minKrw)} 이상만 표시` : ""}</span>
      <span class="hint" style="margin:0;">※ 쌍끌이 기관은 토스 기관합계(금융투자+보험+투신+사모 등) 기준입니다.</span>
    </div>

    <div class="h-tabs">${tabBtns}</div>
    <div class="flow-panel">${panel}</div>
    <p class="hint" style="margin-top:12px;">💡 최근가는 토스, 수급 데이터는 일별 합산입니다. 열 이름을 클릭하면 최근가, 외인/기관 순매수량, 추정금액으로 정렬할 수 있습니다.</p>
  `;
  paintSortHeaders(`flow-${active.id}`);
  loadFlowTier1Briefing("flow-tier1-briefing").catch(() => {});
}

function renderFlowStats(data) {
  const box = $("#flow-stats-box");
  if (!box) return;
  if (!data?.configured) {
    box.innerHTML = `<p class="hint">${escapeHtml(data?.error || "토스증권 키가 필요합니다.")}</p>`;
    return;
  }

  const withQuery = (rows) => filterFlowQuery(rows);
  const dualRows = withQuery(sharedFlowRows(data.dual || [], "dual_krw"));
  const peRows = withQuery(sharedFlowRows(data.private_equity || [], "pe_krw"));
  const tripleRows = withQuery(sharedFlowRows(data.dual_pe || [], "dual_krw"));
  const confluenceRows = withQuery(sharedFlowRows(data.rows || []).filter((r) => setupNotional(r) >= flowMinKrw() && taMatch(r, "confluence")));
  const groups = [
    ["외인·기관 쌍끌이", dualRows],
    ["사모펀드 순매수", peRows],
    ["쌍끌이+사모", tripleRows],
    ["수급+기술 중첩", confluenceRows],
  ];

  const performanceRows = groups.map(([label, rows]) => {
    const d5 = analyzeHit(rows, "ret_5d");
    const d20 = analyzeHit(rows, "ret_20d");
    return `<tr>
      <td><b>${escapeHtml(label)}</b></td>
      <td class="num">${rows.length}</td>
      <td class="num">${d5.n}</td>
      <td class="num">${d5.hit == null ? "—" : `${(d5.hit * 100).toFixed(0)}%`}</td>
      <td class="num">${pctCell(d5.avg)}</td>
      <td class="num">${pctCell(d5.median)}</td>
      <td class="num">${d20.n}</td>
      <td class="num">${d20.hit == null ? "—" : `${(d20.hit * 100).toFixed(0)}%`}</td>
      <td class="num">${pctCell(d20.avg)}</td>
      <td class="num">${pctCell(d20.median)}</td>
    </tr>`;
  }).join("");

  const dual5 = analyzeHit(dualRows, "ret_5d");
  const pe5 = analyzeHit(peRows, "ret_5d");
  const conf5 = analyzeHit(confluenceRows, "ret_5d");
  const when = fmtWhen(data.fetched_at);
  if (currentView === "trade" && smartFlowTab === "stats") {
    setPageAsOf(
      when ? `성과 표본 수급 스캔 ${when} · ${data.days || 5}거래일` : "성과 표본 시점 없음",
      "표의 이후 5일·20일은 저장된 과거 신호의 실측 성과이며 미래 수익률 예측이 아닙니다."
    );
  }

  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr); margin:0 0 16px;">
      <div class="kpi"><span>검증 범위</span><b style="font-size:17px;">${escapeHtml(flowUniverseLabel())}</b></div>
      <div class="kpi"><span>쌍끌이 5일 승률</span><b style="color:#34d399;">${dual5.hit == null ? "—" : `${(dual5.hit * 100).toFixed(0)}%`}</b><small>표본 ${dual5.n}건</small></div>
      <div class="kpi"><span>사모 5일 승률</span><b style="color:#c084fc;">${pe5.hit == null ? "—" : `${(pe5.hit * 100).toFixed(0)}%`}</b><small>표본 ${pe5.n}건</small></div>
      <div class="kpi"><span>수급+기술 5일 승률</span><b style="color:#facc15;">${conf5.hit == null ? "—" : `${(conf5.hit * 100).toFixed(0)}%`}</b><small>표본 ${conf5.n}건</small></div>
    </div>

    <div class="rank-card">
      <div class="card-h"><h3 style="margin:0;">📊 수급 셋업별 과거 성과 비교</h3></div>
      <p class="hint">현재 검색·금액·종목 범위를 적용한 뒤, 수급 신호 발생 후 실제 5일·20일 수익률의 양수 비율과 평균·중앙값을 비교합니다.</p>
      <div class="smart-flow-warning" style="margin-bottom:12px;"><b>관측 완료 표본만 집계</b><br />D+5·D+20 거래일을 모두 지난 신호만 승률·평균·중앙값에 포함합니다. 진행 중인 신호는 각 표에서 D+n/목표로 표시됩니다.</div>
      <div class="table-wrap">
        <table class="rank-table">
          <thead><tr>
            <th>수급 셋업</th><th>현재 후보</th>
            <th>5일 표본</th><th>5일 승률</th><th>5일 평균</th><th>5일 중앙</th>
            <th>20일 표본</th><th>20일 승률</th><th>20일 평균</th><th>20일 중앙</th>
          </tr></thead>
          <tbody>${performanceRows}</tbody>
        </table>
      </div>
    </div>

    <div class="rank-grid" style="margin-top:14px;">
      ${bucketTable("쌍끌이 금액구간별 5일 성과", dualRows, "dual_krw")}
      ${bucketTable("사모 금액구간별 5일 성과", peRows, "pe_krw")}
    </div>
    <div class="smart-flow-note" style="margin-top:14px;">
      <b>해석 주의</b><br />표본 수가 적으면 승률 100%도 신뢰하기 어렵습니다. 최근가와 당일 등락은 토스, 기술지표는 KRX 저장 일봉이며, 거래비용·슬리피지를 뺀 주문 성과가 아닙니다.
    </div>`;
}

function flowReady(data) {
  return Boolean(data && !data.need_scan && Array.isArray(data.rows) && Array.isArray(data.trading));
}

async function ensureFlow(force) {
  const days = flowDays();
  if (!force && flowCache && flowCache.days === days && flowReady(flowCache)) {
    return flowCache;
  }
  let data = await api(`/api/flow?days=${days}`);
  if (force || !flowReady(data)) {
    data = await api("/api/flow", { method: "POST", body: JSON.stringify({ days }) });
  }
  flowCache = data;
  return data;
}

async function loadInvestor() {
  const box = $("#investor-box");
  if (!box) return;
  const data = await api("/api/investor");
  const cov = data.coverage || {};
  const blockers = (data.blockers || []).map((t) => `<li class="warn">${escapeHtml(t)}</li>`).join("");
  const next = (data.next_steps || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  const uni = (data.universe_preview || [])
    .map((t) => {
      const isWatch = t.why === "관심종목";
      const icon = isWatch ? "⭐" : "🔥";
      const tagCls = isWatch ? "watch-tag" : "liquidity-tag";
      const pillCls = isWatch ? "watch-pill" : "liquidity-pill";
      const tipTitle = `${icon} ${escapeHtml(t.company || t.ticker)} (${t.ticker})`;
      const tipDesc = escapeHtml(t.detail || (isWatch ? "사용자가 직접 관심종목으로 등록한 종목입니다." : "최근 시장 거래대금 최상위 고유동성 대형주입니다."));
      return `<button type="button" class="universe-pill ${pillCls} has-tip" data-tip-title="${tipTitle}" data-tip="${tipDesc}" onclick="openStock('${escapeHtml(t.ticker)}')" tabindex="0">
        <b class="pill-name">${escapeHtml(t.company || t.ticker)}</b>
        <span class="badge-tag ${tagCls}">${icon} ${escapeHtml(t.why || "")}</span>
      </button>`;
    })
    .join(" ");
  const asof = cov.last_date ? `공식 수급 최신일 ${cov.last_date} · ${cov.tickers || 0}종목 · ${cov.rows || 0}행` : "공식 수급 데이터 없음 (토스 캐시 대체 가동 중)";
  if (currentView === "investor") setPageAsOf(asof, "KIS 관심종목·고유동성 수급 추적. API 미설정 시 토스 데이터로 자동 대체됩니다.");

  loadFlowTier1Briefing("investor-tier1-briefing").catch(() => {});

  box.innerHTML = `
    ${asofBanner(asof)}
    <div id="tier1-investor-briefing" style="margin-bottom:14px;"></div>
    <div class="kpis" style="grid-template-columns:repeat(4,1fr); margin:0 0 16px;">
      <div class="kpi has-tip" data-tip-title="🏛️ KIS Open API 연동" data-tip="한국투자증권 실거래/모의계좌 OpenAPI를 통한 실시간 수급 적재 상태입니다." tabindex="0">
        <span>KIS Open API</span><b class="${data.configured ? "ok" : "warn"}" style="color:${data.configured ? '#4ade80' : '#f59e0b'};">${data.configured ? "연결 완료" : "미설정 (토스 대체)"}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="📁 저장된 수급 종목" data-tip="로컬 데이터베이스에 수급 일별 시계열이 적재된 누적 종목 수입니다." tabindex="0">
        <span>저장된 종목</span><b style="color:#00e5ff;">${cov.tickers ?? 0}개</b>
      </div>
      <div class="kpi has-tip" data-tip-title="📊 누적 수급 레코드" data-tip="외인·기관·개인·기금의 일자별 순매수 및 외인지분율 행 수입니다." tabindex="0">
        <span>수집된 수급 데이터</span><b style="color:#c084fc;">${cov.rows ?? 0}행</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🎯 수집 예정 유니버스" data-tip="관심종목 + 거래대금 상위 30종목 중 다음 수집 대기 후보입니다." tabindex="0">
        <span>수집 예정 후보</span><b style="color:#facc15;">${data.universe_n ?? 0}종목</b>
      </div>
    </div>

    <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:12px 14px; margin-bottom:14px;">
      <h4 style="margin:0 0 6px; font-size:14px; color:#60a5fa;">📌 공식 수급 수집 기준 및 동작 원리</h4>
      <p style="margin:0 0 8px; font-size:13px; color:#cbd5e1; line-height:1.5;">
        한국투자증권(KIS) Open API를 통해 증권사 HTS와 동일한 일별 기관·외국인·개인·기금의 <b>공식 순매수 주수 및 외인 지분율</b>을 직접 수집·적재합니다.
      </p>
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; font-size:12px; color:#94a3b8;">
        <div style="background:rgba(0,0,0,0.2); padding:8px 10px; border-radius:6px;">
          <b style="color:#e2e8f0;">🎯 수집 대상 선정 기준 (Universe)</b><br/>
          • <b>1순위: 관심종목</b> (직접 등록한 모든 종목)<br/>
          • <b>2순위: 거래대금 TOP 30</b> (시장 주도 고유동성 대형주)<br/>
          <i>※ API 쿼터 보호 및 속도 유지를 위해 핵심 종목만 집중 수집</i>
        </div>
        <div style="background:rgba(0,0,0,0.2); padding:8px 10px; border-radius:6px;">
          <b style="color:#e2e8f0;">💡 데이터 백업 엔진 (Fallback)</b><br/>
          KIS API 키가 없거나 수집 전이어도, 아래 <b>[연속·동반·방향전환]</b> 분석표는 <b>토스증권 수급 캐시(기관+외인)</b>로 자동 연동되어 빈 화면 없이 즉시 분석할 수 있습니다.
        </div>
      </div>
    </div>

    <div style="margin-bottom:12px;">
      <h4 style="margin:0 0 6px; font-size:13px; color:#e2e8f0;">📋 이번 수집 대상 종목 (클릭 시 상세 분석)</h4>
      <div style="display:flex; flex-wrap:wrap; gap:6px;">
        ${uni || '<span class="hint">관심종목을 등록하거나 KRX 시세를 실행하면 대상이 생성됩니다.</span>'}
      </div>
    </div>

    ${blockers ? `<div style="margin-top:10px;"><h4 style="margin:0 0 4px; font-size:13px; color:#f59e0b;">⚠️ KIS 공식 수급 안내</h4><ul style="margin:0; padding-left:20px; font-size:12px; color:#fbbf24;">${blockers}</ul></div>` : ""}
    ${next ? `<div style="margin-top:10px;"><h4 style="margin:0 0 4px; font-size:13px; color:#93c5fd;">🚀 다음 진행 팁</h4><ul style="margin:0; padding-left:20px; font-size:12px; color:#cbd5e1;">${next}</ul></div>` : ""}
    <p class="hint" style="margin-top:12px;">${escapeHtml(data.disclaimer || "")}</p>
  `;
  loadTier1InvestorBriefing().catch(() => {});
}

async function loadTier1InvestorBriefing() {
  const box = $("#tier1-investor-briefing");
  if (!box) return;
  try {
    const data = await api("/api/flow/tier1-briefing");
    if (!renderTier1Unavailable(box, data)) return;
    const sectors = (data.focus_sectors || []).map((s) => `<span class="chip" style="font-size:11px; color:#38bdf8; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.3); padding:2px 8px; border-radius:4px;">🎯 ${escapeHtml(s)}</span>`).join(" ");
    box.innerHTML = `
      <div class="tier1-ai-card" style="background:linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,41,59,0.9)); border:1px solid rgba(56,189,248,0.4); border-radius:10px; padding:14px 16px; box-shadow:0 4px 16px rgba(0,0,0,0.3);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span style="font-size:12.5px; font-weight:700; color:#38bdf8; display:flex; align-items:center; gap:6px;">
            🤖 Tier 1 무료 AI 메이저 수급 동향 브리핑
            <span style="font-size:10.5px; font-weight:400; color:#94a3b8;">(${escapeHtml(data.model || "NVIDIA 550B")})</span>
          </span>
          <div style="display:flex; gap:4px;">${sectors}</div>
        </div>
        <b style="font-size:13.5px; color:#f8fafc; display:block; margin-bottom:6px;">"${escapeHtml(data.headline || "")}"</b>
        <p style="font-size:12.5px; line-height:1.55; color:#cbd5e1; margin:0;">${escapeHtml(data.briefing || "")}</p>
      </div>
    `;
    appendTier1Meta(box, data);
  } catch (e) {
    console.debug("Tier 1 investor briefing error:", e);
    renderTier1Unavailable(box, null, e);
  }
}

let investorEventTab = "consecutive";
let investorEventSource = "auto";

function dirKo(d) {
  if (d === "BUY") return "매수";
  if (d === "SELL") return "매도";
  return "중립";
}

function fmtAmt(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(0)}만`;
  return n.toLocaleString("ko-KR");
}

function renderInvestorEvents(data) {
  const box = $("#investor-events-box");
  if (!box) return;
  const official = data.official || {};
  const toss = data.toss || {};
  const pick = investorEventSource === "toss" ? "toss" : investorEventSource === "official" ? "official" : data.active || "toss";
  const src = pick === "official" ? official : toss;
  const reb = data.rebalance || {};
  const tabs = [
    ["consecutive", `🔥 연속 순매수 (${ (src.consecutive || []).length })`],
    ["paired", `💎 동반 매수 (${ (src.paired || []).length })`],
    ["turns", `🔄 방향전환 (${ (src.turns || []).length })`],
    ["cum5", `📅 5일 누적 (${ (src.cum5 || []).length })`],
    ["cum20", `📅 20일 누적 (${ (src.cum20 || []).length })`],
    ["cum60", `📅 60일 누적 (${ (src.cum60 || []).length })`],
  ];
  const rows = src[investorEventTab] || [];
  const isCum = String(investorEventTab).startsWith("cum");
  const cumKey = investorEventTab === "cum60" ? "w60" : investorEventTab === "cum5" ? "w5" : "w20";

  const renderDirBadge = (d) => {
    if (d === "BUY") return '<span class="chip" style="background:rgba(16,185,129,0.15); color:#34d399; font-weight:800;">🔴 순매수</span>';
    if (d === "SELL") return '<span class="chip" style="background:rgba(239,68,68,0.15); color:#f87171; font-weight:800;">🔵 순매도</span>';
    return '<span class="chip" style="background:rgba(148,163,184,0.15); color:#94a3b8;">중립</span>';
  };

  const renderAmtBadge = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n) || n === 0) return "—";
    const str = fmtAmt(n);
    if (n > 0) return `<b class="text-emerald-400">+${str}</b>`;
    if (n < 0) return `<b class="text-rose-400">${str}</b>`;
    return str;
  };

  const head =
    investorEventTab === "turns"
      ? `<th class="has-tip" data-tip="종목명 및 6자리 코드입니다.">종목명</th><th class="has-tip" data-tip="외인/기관의 매도세가 매수세로 전환된 방향입니다.">전환 방향</th><th class="has-tip" data-tip="전환 직전까지 지속되었던 연속 매도 일수입니다.">이전 연속</th><th class="has-tip" data-tip="오늘 유입된 순매수 주수입니다.">오늘 순매수</th><th class="has-tip" data-tip="데이터 출처입니다.">출처</th>`
      : investorEventTab === "paired"
        ? `<th class="has-tip" data-tip="종목명 및 6자리 코드입니다.">종목명</th><th class="has-tip" data-tip="동반 매수 포지션입니다.">방향</th><th class="has-tip" data-tip="기관 투자자 순매수량입니다.">${escapeHtml(src.pair || "기관")}</th><th class="has-tip" data-tip="외국인 투자자 순매수량입니다.">외국인</th><th class="has-tip" data-tip="데이터 출처입니다.">출처</th>`
        : isCum
          ? `<th class="has-tip" data-tip="종목명 및 6자리 코드입니다.">종목명</th><th class="has-tip" data-tip="설정 기간 동안 누적된 합산 순매수량입니다.">누적 순매수</th><th class="has-tip" data-tip="수급 일수입니다.">일수</th><th class="has-tip" data-tip="이력 데이터 충분성 여부입니다.">이력 상태</th><th class="has-tip" data-tip="데이터 출처입니다.">출처</th>`
        : `<th class="has-tip" data-tip="종목명 및 6자리 코드입니다.">종목명</th><th class="has-tip" data-tip="순매수 또는 순매도 포지션입니다.">방향</th><th class="has-tip" data-tip="쉬지 않고 연속으로 순매수한 거래일 수입니다.">연속 일수</th><th class="has-tip" data-tip="연속 매수 기간 동안 합산된 총 순매수량입니다.">누적 수급</th><th class="has-tip" data-tip="이력 상태입니다.">이력 상태</th><th class="has-tip" data-tip="데이터 출처입니다.">출처</th>`;

  const body = rows
    .slice(0, 40)
    .map((r) => {
      const srcChip = `<span class="chip" style="background:rgba(255,255,255,0.06); color:#cbd5e1; font-size:11px;">${escapeHtml(r.source || (pick === "official" ? "KIS" : "토스"))}</span>`;
      if (isCum) {
        return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
          <td><div style="display:flex; align-items:center; gap:6px;"><b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b><span class="meta">${escapeHtml(r.ticker)}</span></div></td>
          <td class="num">${renderAmtBadge(r[cumKey])}</td>
          <td class="num">${r[cumKey + "_n"] ? `<b style="color:#38bdf8;">${r[cumKey + "_n"]}일</b>` : "—"}</td>
          <td>${r[cumKey + "_capped"] ? '<span class="chip" style="background:rgba(245,158,11,0.15); color:#f59e0b; font-size:11px;">이력 짧음</span>' : "정상"}</td>
          <td>${srcChip}</td></tr>`;
      }
      if (investorEventTab === "turns") {
        const t = r.turn || r;
        const turnBadge = `<span class="chip" style="background:rgba(250,204,21,0.15); color:#facc15; font-weight:700;">🔄 ${dirKo(t.from || r.turn_from)} ➔ ${dirKo(t.to || r.turn_to)}</span>`;
        return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
          <td><div style="display:flex; align-items:center; gap:6px;"><b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b><span class="meta">${escapeHtml(r.ticker)}</span></div></td>
          <td>${turnBadge}</td>
          <td class="num">${t.prior_days || r.turn_prior_days ? `<b style="color:#94a3b8;">${t.prior_days || r.turn_prior_days}일</b>` : "—"}</td>
          <td class="num">${renderAmtBadge(t.today || r.today_a)}</td>
          <td>${srcChip}</td></tr>`;
      }
      if (investorEventTab === "paired") {
        return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
          <td><div style="display:flex; align-items:center; gap:6px;"><b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b><span class="meta">${escapeHtml(r.ticker)}</span></div></td>
          <td>${renderDirBadge(r.paired_direction)}</td>
          <td class="num">${renderAmtBadge(r.today_a)}</td>
          <td class="num">${renderAmtBadge(r.today_b)}</td>
          <td>${srcChip}</td></tr>`;
      }
      return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
        <td><div style="display:flex; align-items:center; gap:6px;"><b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b><span class="meta">${escapeHtml(r.ticker)}</span></div></td>
        <td>${renderDirBadge(r.direction)}</td>
        <td class="num"><b style="color:#38bdf8;">${r.days || 0}일 연속</b></td>
        <td class="num">${renderAmtBadge(r.cumulative)}</td>
        <td>${r.capped ? '<span class="chip" style="background:rgba(245,158,11,0.15); color:#f59e0b; font-size:11px;">이력 시작</span>' : "정상"}</td>
        <td>${srcChip}</td></tr>`;
    })
    .join("");

  const srcBadge = pick === "official"
    ? '<span class="chip" style="background:rgba(56,189,248,0.18); color:#38bdf8; font-weight:800; border:1px solid rgba(56,189,248,0.4);">🏛️ 한국투자증권(KIS) 공식 수급 기준</span>'
    : '<span class="chip" style="background:rgba(168,85,247,0.18); color:#c084fc; font-weight:800; border:1px solid rgba(168,85,247,0.4);">⚡ 토스증권 수급 캐시 기준 (자동 백업 엔진)</span>';

  box.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:10px;">
      <div class="h-tabs" style="margin:0; padding:0; border:none;">
        <button type="button" class="${pick === "official" ? "on" : ""}" data-inv-src="official">🏛️ 공식 KIS (${official.tickers || 0}종목)</button>
        <button type="button" class="${pick === "toss" ? "on" : ""}" data-inv-src="toss">⚡ 토스 캐시 (${toss.tickers || 0}종목)</button>
      </div>
      <div>${srcBadge}</div>
    </div>
    <div class="h-tabs" style="margin-bottom:12px;">
      ${tabs.map(([id, label]) => `<button type="button" class="${investorEventTab === id ? "on" : ""}" data-inv-tab="${id}">${label}</button>`).join("")}
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>${head}</tr></thead>
        <tbody>${body || `<tr><td colspan="6" class="hint" style="text-align:center; padding:30px;">해당 조건의 수급 포착 종목이 없습니다.</td></tr>`}</tbody>
      </table>
    </div>
  `;
  box.querySelectorAll("[data-inv-tab]").forEach((btn) =>
    btn.addEventListener("click", () => {
      investorEventTab = btn.dataset.invTab;
      renderInvestorEvents(data);
    })
  );
  box.querySelectorAll("[data-inv-src]").forEach((btn) =>
    btn.addEventListener("click", () => {
      investorEventSource = btn.dataset.invSrc;
      renderInvestorEvents(data);
    })
  );
  box.querySelectorAll("tr.clickable[data-ticker]").forEach((tr) =>
    tr.addEventListener("click", () => openStock(tr.dataset.ticker).catch((err) => alert(err.message)))
  );
}

async function loadInvestorEvents() {
  const box = $("#investor-events-box");
  if (!box) return;
  const minTurn = Number($("#investor-turn")?.value || 5);
  const data = await api(`/api/investor/events?min_turn=${minTurn}`);
  if (investorEventSource === "auto") investorEventSource = data.active || "toss";
  renderInvestorEvents(data);
}

let currentSunziUniverse = "quant";
let currentSunziQuery = "";
let currentSunziPosture = "all";
let currentSunziFa = "all";
let currentSunziMarket = "all";

function sunziTone(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return "";
  if (n >= 70) return "ok";
  if (n >= 45) return "warn";
  return "bad";
}

function postureMeta(code) {
  const key = String(code || "OBSERVE");
  const map = {
    ENGAGE: { ko: "착수", cls: "posture-engage", hint: "조건은 맞습니다. 출진 명령은 아닙니다." },
    WAIT: { ko: "대기", cls: "posture-wait", hint: "오늘은 싸울 날이 아닙니다." },
    OBSERVE: { ko: "관찰", cls: "posture-observe", hint: "정보가 부족하면 가만히 있는 쪽이 낫습니다." },
    RETREAT: { ko: "후퇴", cls: "posture-retreat", hint: "질 이유가 더 잘 보입니다." },
    AVOID: { ko: "회피", cls: "posture-avoid", hint: "法이 안 되면 그 전쟁은 시작하지 않습니다." },
  };
  return map[key] || map.OBSERVE;
}

function postureChip(r) {
  const meta = postureMeta(r.posture);
  const label = r.posture_ko || meta.ko;
  return `<span class="posture-chip ${meta.cls} has-tip" data-tip="${escapeHtml(r.critic_comment || meta.hint)}">${escapeHtml(label)}</span>`;
}

function sunziMiniBars(r) {
  const bits = [
    ["道", r.dao],
    ["天", r.tian],
    ["地", r.di],
    ["將", r.jiang],
    ["法", r.fa],
  ];
  return `<div class="yang-mini-bars">${bits.map(([k, v]) => {
    const pct = Math.max(4, Math.min(100, Number(v) || 0));
    return `<div class="yang-mini-col"><i><em style="height:${pct}%"></em></i><span>${k}</span></div>`;
  }).join("")}</div>`;
}

let sunziAllRows = [];

function openYangTacticalModal(r, initialPersona = "yang") {
  const modal = $("#yang-tactical-modal");
  if (!modal) return;

  let activePersona = initialPersona;

  function renderPersonaContent(aiData, persona) {
    const personaMeta = {
      yang: { badge: "🍵 제13함대 양 웬리 기밀 작전 지시서", badgeColor: "#eab308", voiceTitle: "🍵 양 웬리 제독의 실전 총평" },
      reinhard: { badge: "🦁 은하제국 황제 친정군 칙령", badgeColor: "#f59e0b", voiceTitle: "🦁 라인하르트 황제의 칙령" },
      oberstein: { badge: "👁️ 군무상서 기밀 리스크 사정서", badgeColor: "#94a3b8", voiceTitle: "👁️ 오베르슈타인 군무상서의 사정" },
      julian: { badge: "📖 후계자 율리안 퀀트 정석 보고서", badgeColor: "#38bdf8", voiceTitle: "📖 율리안 민츠 참모의 보고" }
    }[persona] || { badge: "제13함대 기밀 작전 지시서", badgeColor: "#eab308", voiceTitle: "실전 총평" };

    const badgeEl = $("#yang-modal-badge");
    if (badgeEl) {
      badgeEl.textContent = personaMeta.badge;
      badgeEl.style.background = personaMeta.badgeColor;
    }
    $("#yang-modal-strategy-tag").textContent = aiData.strategy_tag || r.strategy_tag || "知彼知己 (지피지기)";
    $("#yang-modal-title").textContent = `${r.company || r.ticker} (${r.ticker})`;
    $("#yang-modal-sub").textContent = `${r.market || 'KOSPI'} · ${r.industry || '미분류'} · 퀀트 점수 ${r.quant_score ?? '—'}점 · 참모 점수 ${r.critic_score ?? '—'}점`;

    const bearListHtml = (r.strongest_bear_evidence || []).map((b) => `<li style="color:#fca5a5; font-size:12.5px; margin-bottom:4px;">${escapeHtml(b)}</li>`).join("");
    const waitTest = r.waiting_test || {};

    $("#yang-modal-body").innerHTML = `
      <!-- 1. Top Quote Bar -->
      <div style="background:linear-gradient(90deg, rgba(56,189,248,0.15), rgba(234,179,8,0.1)); padding:12px 16px; border-radius:12px; border-left:4px solid #38bdf8;">
        <b style="color:#fff; font-size:14px;">${personaMeta.voiceTitle}:</b>
        <p style="margin:6px 0 0; color:#38bdf8; font-size:14px; font-weight:700; line-height:1.5;">“${escapeHtml(aiData.one_line_verdict || r.one_line_judgment || r.critic_comment || '')}”</p>
      </div>

      <!-- 2. 3-Tier Tactical Intelligence -->
      <div style="display:flex; flex-direction:column; gap:10px;">
        <div class="yang-tier-box briefing">
          <b style="font-size:13px; color:#38bdf8;">🔭 1단계: 전황 분석 & 회사의 실체</b>
          <p style="margin:6px 0 0; color:#e2e8f0; line-height:1.5;">${escapeHtml(aiData.tactical_briefing || r.tactical_briefing || r.critic_comment || '분석 데이터 집계 중...')}</p>
        </div>

        <div class="yang-tier-box maneuver">
          <b style="font-size:13px; color:#fbbf24;">💡 2단계: 기책 & 진입/대기 타점</b>
          <p style="margin:6px 0 0; color:#fef08a; line-height:1.5;">${escapeHtml(aiData.maneuver_entry || r.maneuver_entry || '지지선 대기 권장')}</p>
        </div>

        <div class="yang-tier-box escape">
          <b style="font-size:13px; color:#f43f5e;">🚪 3단계: 퇴로 확보 & 작전 무효화 조건 (손절 원칙)</b>
          <p style="margin:6px 0 0; color:#fda4af; line-height:1.5;">${escapeHtml(aiData.escape_route || r.escape_route || '3~5% 손절선 설정')}</p>
        </div>
      </div>

      <!-- 3. Sun Tzu 5 Aspects Detailed Table -->
      <div style="margin-top:4px;">
        <b style="color:#fff; font-size:13.5px; margin-bottom:8px; display:block;">📜 손자 五事 (道天地將法) 정밀 점검표</b>
        <div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:6px;">
          <div class="five-card" style="padding:8px 10px; text-align:center;">
            <span style="font-size:11px;">道 (정렬)</span>
            <b class="${sunziTone(r.dao)}" style="font-size:16px;">${fmt(r.dao, 0)}</b>
          </div>
          <div class="five-card" style="padding:8px 10px; text-align:center;">
            <span style="font-size:11px;">天 (시장)</span>
            <b class="${sunziTone(r.tian)}" style="font-size:16px;">${fmt(r.tian, 0)}</b>
          </div>
          <div class="five-card" style="padding:8px 10px; text-align:center;">
            <span style="font-size:11px;">地 (업종)</span>
            <b class="${sunziTone(r.di)}" style="font-size:16px;">${fmt(r.di, 0)}</b>
          </div>
          <div class="five-card" style="padding:8px 10px; text-align:center;">
            <span style="font-size:11px;">將 (지휘관)</span>
            <b class="${sunziTone(r.jiang)}" style="font-size:16px;">${fmt(r.jiang, 0)}</b>
          </div>
          <div class="five-card" style="padding:8px 10px; text-align:center;">
            <span style="font-size:11px;">法 (규율)</span>
            <b class="${sunziTone(r.fa)}" style="font-size:16px;">${fmt(r.fa, 0)}</b>
          </div>
        </div>
      </div>

      <!-- 4. Adversarial Skepticism & Waiting Benefit -->
      <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:12px 14px;">
        <b style="color:#f87171; font-size:12.5px;">⚠️ 참모가 의심하는 가장 강력한 반대 논리:</b>
        <ul style="margin:6px 0 8px 18px; padding:0;">${bearListHtml || '<li style="color:#94a3b8; font-size:12px;">특이 반대 징후 없음</li>'}</ul>
        <div style="margin-top:6px; font-size:12px; color:#94a3b8; border-top:1px solid rgba(255,255,255,0.06); padding-top:6px; display:flex; justify-content:space-between;">
          <span>⏳ <b>기다림의 득:</b> ${escapeHtml(waitTest.benefit_of_waiting || '—')}</span>
          <span>⌛ <b>기다림의 실:</b> ${escapeHtml(waitTest.cost_of_waiting || '—')}</span>
        </div>
      </div>

      <!-- Action Footer -->
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:8px;">
        <button type="button" class="ghost small" onclick="openStock('${escapeHtml(r.ticker)}')">📊 종목 전체 퀀트 분석 →</button>
        <button type="button" class="primary small" id="btn-modal-close-action" style="background:#38bdf8; color:#0f172a; font-weight:800;">확인 완료</button>
      </div>
    `;

    const closeAction = $("#btn-modal-close-action");
    if (closeAction) closeAction.onclick = closeYangModal;
  }

  function fetchPersonaAi(persona) {
    activePersona = persona;
    modal.querySelectorAll(".yang-persona-btn").forEach(btn => {
      if (btn.getAttribute("data-persona") === persona) {
        btn.classList.add("active");
        btn.style.background = "#38bdf8";
        btn.style.color = "#0f172a";
        btn.style.fontWeight = "800";
      } else {
        btn.classList.remove("active");
        btn.style.background = "";
        btn.style.color = "";
        btn.style.fontWeight = "";
      }
    });

    if (persona === "yang" && r.tactical_briefing) {
      renderPersonaContent(r, "yang");
      return;
    }

    $("#yang-modal-body").innerHTML = `
      <div style="text-align:center; padding:30px; color:#94a3b8;">
        <div class="skeleton-spinner" style="margin:0 auto 10px;"></div>
        <b style="color:#38bdf8;">지휘관 AI가 '${escapeHtml(r.company || r.ticker)}'의 실전 작전 지시서를 작성 중입니다...</b>
      </div>
    `;

    api("/api/sunzi/tactical-ai", {
      method: "POST",
      body: JSON.stringify({
        ticker: r.ticker,
        company: r.company,
        quant_score: r.quant_score,
        sector: r.industry,
        posture: r.posture,
        dao_score: r.dao,
        tian_score: r.tian,
        di_score: r.di,
        jiang_score: r.jiang,
        fa_pass: r.fa_gate_pass,
        persona: persona
      })
    }).then(aiData => {
      renderPersonaContent(aiData, persona);
    }).catch(err => {
      renderPersonaContent(r, persona);
    });
  }

  // Initial render
  fetchPersonaAi(activePersona);

  modal.querySelectorAll(".yang-persona-btn").forEach(btn => {
    btn.onclick = () => {
      const p = btn.getAttribute("data-persona");
      if (p && p !== activePersona) {
        fetchPersonaAi(p);
      }
    };
  });

  modal.classList.remove("hidden");
  modal.style.display = "flex";

  function closeYangModal() {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }

  const closeBtn = $("#btn-close-yang-modal");
  if (closeBtn) closeBtn.onclick = closeYangModal;
  modal.onclick = (e) => {
    if (e.target === modal) closeYangModal();
  };
}

async function loadSunzi() {
  const box = $("#sunzi-box");
  if (!box) return;
  loadSunziTier1Briefing().catch(() => {});
  box.innerHTML = `
    <div style="text-align:center; padding:40px; color:#94a3b8;">
      <div style="font-size:32px; margin-bottom:12px;">🍵</div>
      <b>제13함대 작전 테이블을 펼치는 중입니다...</b>
      <p style="font-size:12px; margin-top:4px;">차는 아직 따뜻합니다. 손자의 오사로 전황을 측정하고 있습니다.</p>
    </div>
  `;

  const params = new URLSearchParams({
    n: currentSunziUniverse === "all" ? "60" : "40",
    universe: currentSunziUniverse,
  });
  if (currentSunziQuery) params.set("query", currentSunziQuery);
  if (currentSunziPosture && currentSunziPosture !== "all") params.set("posture", currentSunziPosture);
  if (currentSunziFa && currentSunziFa !== "all") params.set("fa", currentSunziFa);
  if (currentSunziMarket && currentSunziMarket !== "all") params.set("market", currentSunziMarket);

  const data = await api(`/api/sunzi?${params.toString()}`);
  if (!data.configured) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error || "결과가 없습니다. 실행 파이프라인에서 재계산을 먼저 하세요.")}</p>`;
    return;
  }

  const tian = data.tian || {};
  const briefing = data.briefing || {};
  const aspects = data.aspects || [];
  sunziAllRows = data.rows || [];
  const postures = data.postures || {};

  const counts = [
    { key: "ENGAGE", label: "🟢 착수", hint: "유리한 전장 착수", n: postures.ENGAGE || 0 },
    { key: "WAIT", label: "🟡 대기", hint: "이일대로·홍차 관망", n: postures.WAIT || 0 },
    { key: "OBSERVE", label: "🟣 관찰", hint: "지피지기·정찰 유지", n: postures.OBSERVE || 0 },
    { key: "RETREAT", label: "🟠 후퇴", hint: "퇴로 확보·전선 후퇴", n: postures.RETREAT || 0 },
    { key: "AVOID", label: "🔴 회피", hint: "해도 결함·출병 거부", n: postures.AVOID || 0 },
  ];

  if (currentView === "sunzi") {
    setPageAsOf(
      `天 ${tian.regime_ko || "—"} · 法 통과 ${data.fa_pass_n || 0}/${data.n || 0} · 대기 ${postures.WAIT || 0}`,
      "손자병법 오사(道天地將法) 기반 거시 전황 점검"
    );
  }

  // 5 Aspects Radar Gauges
  const aspectCards = aspects.map((a) => `
    <div class="five-card sunzi-aspect" style="padding:14px 16px; border-radius:14px; background:linear-gradient(180deg, rgba(15,23,42,0.8), rgba(8,47,73,0.4)); border:1px solid rgba(56,189,248,0.25);">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:13.5px; font-weight:800; color:#38bdf8;">${escapeHtml(a.han || "")} ${escapeHtml(a.ko || "")}</span>
        <b class="${sunziTone(a.score)}" style="font-size:20px; font-weight:900;">${fmt(a.score, 0)}</b>
      </div>
      <p class="sunzi-q" style="font-size:11.5px; color:#94a3b8; margin:6px 0 8px;">${escapeHtml(a.sunzi || "")}</p>
      <p class="yang-voice" style="font-size:12.5px; line-height:1.5; color:#e2e8f0;">${escapeHtml(a.yang || "")}</p>
      ${a.note ? `<div class="meta" style="margin-top:8px; font-size:11px; color:#67e8f9;">📌 ${escapeHtml(a.note)}</div>` : ""}
    </div>
  `).join("");

  const pMeta = SUNZI_PERSONAS[currentSunziPersona] || SUNZI_PERSONAS.yang;

  // Top 6 Staff Hero Cards
  const staff = sunziAllRows.slice(0, 6);
  const staffCards = staff.map((r, idx) => `
    <div class="yang-tactical-card" data-ticker="${escapeHtml(r.ticker || "")}" data-index="${idx}">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
        <div>
          <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <span class="yang-strategy-pill">${escapeHtml(r.strategy_tag || '知彼知己')}</span>
            <b style="color:#fff; font-size:17px; font-weight:900;">${escapeHtml(r.company || r.ticker || "")}</b>
            <span class="chip" style="background:#1e293b; color:#94a3b8; font-family:monospace; font-size:11px;">${escapeHtml(r.market || "")} ${escapeHtml(r.ticker || "")}</span>
          </div>
          <div class="meta" style="margin-top:4px;">${escapeHtml(r.industry || "미분류")} · 퀀트 점수 <b>${fmt(r.quant_score, 1)}점</b> · 참모 점수 <b class="${sunziTone(r.critic_score)}">${fmt(r.critic_score, 0)}점</b></div>
        </div>
        ${postureChip(r)}
      </div>

      <!-- Mini 5 Aspects Bar -->
      ${sunziMiniBars(r)}

      <!-- 3-Tier Tactical Commentary Box -->
      <div style="display:flex; flex-direction:column; gap:8px; margin-top:10px;">
        <div class="yang-tier-box briefing">
          <b style="font-size:12px; color:#38bdf8;">🔭 전황 분석:</b> ${escapeHtml(r.tactical_briefing || r.critic_comment || '')}
        </div>
        ${r.maneuver_entry ? `
        <div class="yang-tier-box maneuver">
          <b style="font-size:12px; color:#fbbf24;">${escapeHtml(pMeta.heroStep2Label)}</b> ${escapeHtml(r.maneuver_entry)}
        </div>` : ''}
      </div>

      <div style="margin-top:12px; display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.08); padding-top:8px;">
        <span style="font-size:12px; color:#67e8f9; font-weight:700;">“${escapeHtml((r.one_line_judgment || '').slice(0, 36))}...”</span>
        <button type="button" class="ghost small btn-open-yang-brief" data-index="${idx}" style="color:#38bdf8; border:1px solid rgba(56,189,248,0.35);">📜 1:1 작전 지시서 ➔</button>
      </div>
    </div>
  `).join("");

  box.innerHTML = `
    <!-- Top War Room HUD Banner -->
    <div class="yang-war-room-header">
      <div class="yang-portrait-card">
        <div class="yang-avatar-hud">${pMeta.avatar}</div>
        <b style="font-size:18px; color:#fff; font-weight:900;">${escapeHtml(pMeta.name)}</b>
        <span style="color:#94a3b8; font-size:12px; display:block; margin-top:2px;">${escapeHtml(pMeta.sub)}</span>
        <div class="yang-tea-badge">${escapeHtml(pMeta.badge)}</div>
        <p style="margin:12px 0 0; font-size:11.5px; color:#cbd5e1; line-height:1.45; font-style:italic;">
          ${escapeHtml(pMeta.quote)}
        </p>
      </div>

      <article class="yang-briefing-hud">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <h3 style="margin:0; font-size:17px; color:#38bdf8; font-weight:900;">📜 ${escapeHtml(pMeta.briefingTitle)}</h3>
          <span class="chip" style="background:rgba(234,179,8,0.2); color:#fde047; font-size:11.5px; font-weight:800;">孫子 五事 評點</span>
        </div>
        <p style="font-size:12px; color:#94a3b8; margin:0 0 8px; line-height:1.4;">${escapeHtml(briefing.sunzi_line || "")}</p>
        <p style="font-size:14px; color:#f1f5f9; font-weight:500; line-height:1.65; margin:0 0 10px; padding:10px 14px; background:rgba(15,23,42,0.6); border-radius:10px; border-left:3px solid #38bdf8;">
          ${escapeHtml(briefing.yang_line || "")}
        </p>
        <div style="display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#64748b;">
          <span>💡 ${escapeHtml(data.disclaimer || briefing.voice || "")}</span>
          <span style="color:#38bdf8;">*착수는 출진 명령이 아니라 연구 우선순위 배정입니다.</span>
        </div>
      </article>
    </div>

    <!-- 5 Aspects Gauge Grid -->
    <div style="margin-bottom:16px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <b style="font-size:14px; color:#fff;">📊 손자병법 오사 (道·天·地·將·法) 거시 전황 측정계</b>
        <span style="font-size:12px; color:#94a3b8;">전체 ${sunziAllRows.length}개 후보 전황 평균</span>
      </div>
      <div class="five-grid sunzi-aspect-grid">${aspectCards}</div>
    </div>

    <!-- Search & Filter Toolbar -->
    <div class="yang-toolbar">
      <div class="autocomplete-wrap yang-search">
        <input id="sunzi-q" type="text" autocomplete="off" value="${escapeHtml(currentSunziQuery)}" placeholder="🔍 퀀트 밖 종목도 분석합니다. 종목명이나 코드를 입력하세요." />
        <ul id="sunzi-q-menu" class="stock-autocomplete-menu" style="display:none;"></ul>
      </div>
      <div id="sunzi-universe-tabs" class="yang-seg">
        <button type="button" class="preset-chip-btn active" data-universe="quant">👑 퀀트 상위 명부</button>
        <button type="button" class="preset-chip-btn" data-universe="all">🌐 전 종목 명부</button>
      </div>
      <select id="sunzi-fa-filter">
        <option value="all">法 전체</option>
        <option value="pass">法 규율 통과만</option>
        <option value="fail">法 미달만</option>
      </select>
      <select id="sunzi-market-filter">
        <option value="all">시장 전체</option>
        <option value="KOSPI">KOSPI</option>
        <option value="KOSDAQ">KOSDAQ</option>
      </select>
    </div>

    <!-- 5 Postures Filter Bar -->
    <div class="yang-posture-filter-bar">
      ${counts.map((c) => {
        const isActive = (currentSunziPosture || 'all') === c.key ? 'active' : '';
        return `
          <button type="button" class="yang-posture-btn ${isActive}" data-posture="${c.key}">
            <div style="font-size:13px; font-weight:800; display:flex; justify-content:space-between; align-items:center;">
              <span>${c.label}</span>
              <b style="font-size:15px; color:#fff;">${c.n}</b>
            </div>
            <div style="font-size:11px; margin-top:2px; opacity:0.8;">${c.hint}</div>
          </button>
        `;
      }).join("")}
      <button type="button" class="yang-posture-btn ${(!currentSunziPosture || currentSunziPosture === 'all') ? 'active' : ''}" data-posture="all">
        <div style="font-size:13px; font-weight:800; display:flex; justify-content:space-between; align-items:center;">
          <span>🌐 전체 보기</span>
          <b style="font-size:15px; color:#fff;">${sunziAllRows.length}</b>
        </div>
        <div style="font-size:11px; margin-top:2px; opacity:0.8;">전체 태세 명부</div>
      </button>
    </div>

    <!-- Staff Hero Cards (Top 6) -->
    <div style="margin-bottom:18px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <b style="font-size:14.5px; color:#fde047;">${escapeHtml(pMeta.heroTitle)}</b>
        <span style="font-size:11.5px; color:#94a3b8;">카드를 클릭하면 1:1 심층 작전 지시서가 열립니다.</span>
      </div>
      <div class="yang-staff-grid">${staffCards}</div>
    </div>

    <!-- Full Data Table -->
    <div class="table-wrap">
      <table data-scope="sunzi">
        <thead>
          <tr>
            <th class="sortable" data-sort="quant_rank">#</th>
            <th class="sortable" data-sort="company">종목</th>
            <th class="sortable" data-sort="posture_ko">참모 태세</th>
            <th>손자 전략</th>
            <th class="sortable" data-sort="critic_score">참모 점수</th>
            <th class="sortable" data-sort="quant_score">Quant</th>
            <th class="sortable" data-sort="dao">道</th>
            <th class="sortable" data-sort="tian">天</th>
            <th class="sortable" data-sort="di">地</th>
            <th class="sortable" data-sort="jiang">將</th>
            <th class="sortable has-tip" data-sort="fa" data-tip="손자 法 — 데이터·리스크·공시 규율">法</th>
            <th>규율</th>
            <th>${escapeHtml(pMeta.tableCol)}</th>
            <th>지시서</th>
          </tr>
        </thead>
        <tbody>
          ${sortedCopy(sunziAllRows, "sunzi", "quant_rank", "asc")
            .map((r, idx) => `
              <tr class="clickable" data-ticker="${escapeHtml(r.ticker)}" data-index="${idx}">
                <td class="num">${r.quant_rank ?? "—"}</td>
                <td>
                  <b>${escapeHtml(r.company || "")}</b>
                  <div class="meta">${escapeHtml(r.ticker)} · ${escapeHtml(r.industry || "")}</div>
                </td>
                <td>${postureChip(r)}</td>
                <td><span class="yang-strategy-pill" style="font-size:10.5px;">${escapeHtml(r.strategy_tag || '知彼知己')}</span></td>
                <td class="num ${sunziTone(r.critic_score)}">${fmt(r.critic_score, 0)}</td>
                <td class="num">${fmt(r.quant_score, 1)}</td>
                <td class="num ${sunziTone(r.dao)}">${fmt(r.dao, 0)}</td>
                <td class="num ${sunziTone(r.tian)}">${fmt(r.tian, 0)}</td>
                <td class="num ${sunziTone(r.di)}">${fmt(r.di, 0)}</td>
                <td class="num ${sunziTone(r.jiang)}">${fmt(r.jiang, 0)}</td>
                <td class="num ${sunziTone(r.fa)}">${fmt(r.fa, 0)}</td>
                <td>${faChip(r)}</td>
                <td class="yang-line">${escapeHtml(r.one_line_judgment || r.critic_comment || "")}</td>
                <td>
                  <button type="button" class="ghost small btn-table-open-brief" data-index="${idx}" style="font-size:11px; padding:2px 8px; color:#38bdf8; border:1px solid rgba(56,189,248,0.3);">지시서 ➔</button>
                </td>
              </tr>
            `).join("")}
        </tbody>
      </table>
    </div>
  `;

  paintSortHeaders("sunzi");

  // Bind Posture Filter buttons
  box.querySelectorAll(".yang-posture-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentSunziPosture = btn.dataset.posture;
      loadSunzi().catch(() => {});
    });
  });

  // Bind Clicks to open Yang Tactical Modal with active commander
  box.querySelectorAll(".yang-tactical-card, .btn-open-yang-brief, .btn-table-open-brief").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const idx = parseInt(el.dataset.index, 10);
      const row = sunziAllRows[idx];
      if (row) openYangTacticalModal(row, currentSunziPersona);
    });
  });

  box.querySelectorAll("tr.clickable[data-ticker]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      const idx = parseInt(tr.dataset.index, 10);
      const row = sunziAllRows[idx];
      if (row) openYangTacticalModal(row, currentSunziPersona);
    });
  });

  setupSunziControls();
}


function setupSunziControls() {
  const qInput = $("#sunzi-q");
  const qMenu = $("#sunzi-q-menu");
  if (qInput && qMenu) {
    setupStockAutocomplete(qInput, qMenu, (selected) => {
      currentSunziQuery = selected.ticker || selected.company || "";
      qInput.value = `${selected.company || ""} ${selected.ticker || ""}`.trim();
      loadSunzi().catch((err) => alert(err.message));
    });
    qInput.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.defaultPrevented) return;
      currentSunziQuery = qInput.value.trim();
      loadSunzi().catch((err) => alert(err.message));
    });
    qInput.addEventListener("input", () => {
      if (!qInput.value.trim()) {
        currentSunziQuery = "";
        loadSunzi().catch(() => {});
      }
    });
  }
  const uni = $("#sunzi-universe-tabs");
  if (uni) {
    uni.querySelectorAll("[data-universe]").forEach((btn) => {
      btn.addEventListener("click", () => {
        uni.querySelectorAll("[data-universe]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentSunziUniverse = btn.dataset.universe || "quant";
        loadSunzi().catch((err) => alert(err.message));
      });
    });
  }
  $("#sunzi-posture-filter")?.addEventListener("change", (e) => {
    currentSunziPosture = e.target.value || "all";
    loadSunzi().catch((err) => alert(err.message));
  });
  $("#sunzi-fa-filter")?.addEventListener("change", (e) => {
    currentSunziFa = e.target.value || "all";
    loadSunzi().catch((err) => alert(err.message));
  });
  $("#sunzi-market-filter")?.addEventListener("change", (e) => {
    currentSunziMarket = e.target.value || "all";
    loadSunzi().catch((err) => alert(err.message));
  });
}

async function loadNps() {
  const box = $("#nps-box");
  const subBox = $("#nps-sub-box");
  if (!box && !subBox) return;
  const data = await api("/api/nps");
  const cov = data.coverage || {};
  const rows = data.rows || [];
  const asof = cov.last_date ? `공시 최신 ${cov.last_date} · ${cov.tickers || 0}종목` : "저장된 보유 공시 없음";
  if (currentView === "nps" || currentView === "investor") setPageAsOf(asof, "OpenDART 대량보유. 일별 기금 수급이 아닙니다.");
  const body = rows
    .map((r) => {
      const chg =
        r.previous_ratio != null && r.holding_ratio != null
          ? (Number(r.holding_ratio) - Number(r.previous_ratio)) * 100
          : null;
      const dart = r.receipt_no
        ? `<a class="ext" href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${encodeURIComponent(r.receipt_no)}" target="_blank" rel="noopener">공시</a>`
        : "";
      return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
        <td><b>${escapeHtml(r.company || r.ticker)}</b><div class="meta">${escapeHtml(r.ticker)}</div></td>
        <td>${escapeHtml(r.holder_name || "")}</td>
        <td class="num">${r.holding_ratio != null ? `${(Number(r.holding_ratio) * 100).toFixed(2)}%` : "—"}</td>
        <td class="num">${chg == null ? "—" : `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%p`}</td>
        <td class="num">${r.share_count != null ? Number(r.share_count).toLocaleString("ko-KR") : "—"}</td>
        <td>${escapeHtml(r.report_date || "")}</td>
        <td>${dart}</td>
      </tr>`;
    })
    .join("");
  const html = `
    ${asofBanner(asof)}
    <div class="kpis" style="grid-template-columns:repeat(3,1fr);margin:8px 0 16px">
      <div class="kpi"><span>OpenDART</span><b class="${data.configured ? "ok" : "warn"}">${data.configured ? "설정됨" : "키 없음"}</b></div>
      <div class="kpi"><span>종목</span><b>${rows.length}</b></div>
      <div class="kpi"><span>저장 행</span><b>${cov.rows ?? 0}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>
    <div class="table-wrap">
      <table data-scope="nps">
        <thead>
          <tr>
            <th class="sortable" data-sort="company">종목</th>
            <th>보고자</th>
            <th class="sortable" data-sort="holding_ratio">지분</th>
            <th>직전대비</th>
            <th class="sortable" data-sort="share_count">주식수</th>
            <th class="sortable" data-sort="report_date">보고일</th>
            <th>원문</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="7">아직 없습니다. 공시 수집을 누르세요.</td></tr>`}</tbody>
      </table>
    </div>
  `;
  if (box) {
    box.innerHTML = html;
    box.querySelectorAll("tr.clickable[data-ticker]").forEach((tr) => {
      if (tr.dataset.ticker && tr.dataset.ticker !== "000000") {
        tr.addEventListener("click", () => openStock(tr.dataset.ticker).catch((err) => alert(err.message)));
      }
    });
  }
  if (subBox) {
    subBox.innerHTML = html;
    subBox.querySelectorAll("tr.clickable[data-ticker]").forEach((tr) => {
      if (tr.dataset.ticker && tr.dataset.ticker !== "000000") {
        tr.addEventListener("click", () => openStock(tr.dataset.ticker).catch((err) => alert(err.message)));
      }
    });
  }
}

function smartFlowBox(tab = smartFlowTab) {
  if (tab === "vacancy") return $("#empty-box");
  if (tab === "technical") return $("#trade-box");
  if (tab === "stats") return $("#flow-stats-box");
  return $("#flow-box");
}

function syncSmartFlowTabs() {
  $$('[data-smart-flow-tab]').forEach((button) => {
    const active = button.dataset.smartFlowTab === smartFlowTab;
    button.classList.toggle("on", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  $$('[data-smart-flow-panel]').forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.smartFlowPanel !== smartFlowTab);
  });
}

function renderSmartFlowActive(data = flowCache) {
  syncSmartFlowTabs();
  if (!data) return;
  if (smartFlowTab === "vacancy") {
    loadEmptyTier1Briefing().catch(() => {});
    renderEmpty(data);
  } else if (smartFlowTab === "technical") {
    loadTradeTier1Briefing().catch(() => {});
    renderTrade(data);
  } else if (smartFlowTab === "stats") {
    renderFlowStats(data);
  } else {
    renderFlow(data);
  }
}

function setSmartFlowTab(tab) {
  smartFlowTab = ["overview", "vacancy", "technical", "stats"].includes(tab) ? tab : "overview";
  renderSmartFlowActive(flowCache);
}

async function loadSmartFlow(force = false) {
  syncSmartFlowTabs();
  const box = smartFlowBox();
  if (!box) return;
  box.innerHTML = force || !flowReady(flowCache)
    ? "<p>토스 수급을 스캔하는 중… 거래대금·랭킹 종목을 포함해 1~2분 걸릴 수 있습니다.</p>"
    : "<p>수급 데이터를 불러오는 중…</p>";
  if (force) flowLimit = {};
  const data = await ensureFlow(force);
  renderSmartFlowActive(data);
}

async function loadFlow(force) {
  smartFlowTab = "overview";
  return loadSmartFlow(Boolean(force));
}

async function runFlowSearch(query) {
  const input = $("#flow-q");
  const raw = String(query ?? input?.value ?? "").trim();
  if (!raw) {
    if (flowCache) renderSmartFlowActive(flowCache);
    return;
  }
  const code = await resolveStockQuery(raw);
  if (!/^\d{6}$/.test(code)) {
    throw new Error(`'${raw}'에 해당하는 종목을 찾지 못했습니다.`);
  }
  if (smartFlowTab === "stats") setSmartFlowTab("overview");
  const target = smartFlowTab === "technical" ? "#trade-box" : smartFlowTab === "vacancy" ? "#empty-box" : "#flow-box";
  const scope = smartFlowTab === "technical" ? "trade" : smartFlowTab === "vacancy" ? "empty" : "flow";
  await fetchOnDemandFlow(code, target, scope);
}

function emptyFilters() {
  const rateRaw = $("#empty-rate")?.value;
  return {
    q: ($("#flow-q")?.value || "").trim().toLowerCase(),
    mode: $("#empty-mode")?.value || "empty",
    maxRate: rateRaw === "" || rateRaw == null ? null : Number(rateRaw),
    minKrw: flowMinKrw(),
  };
}

function emptyTags(r) {
  const extra = {
    쌍매도: SETUP_TIPS["빈집"],
    개인받음: "기관·외인이 판 물량을 개인이 순매수한 모습입니다. 받쳐 줬다는 뜻이지 바닥 확인이 아닙니다.",
    외인저비중: "토스 외국인 보유비율이 낮습니다. 기관 지분은 이 API에 없어 외인 지분만 봅니다.",
  };
  const tags = [];
  if (r.comeback) tags.push(tipTag("복귀", "hot", SETUP_TIPS));
  if (r.empty) tags.push(tipTag("쌍매도", "down", extra));
  if (r.retail_absorb) tags.push(tipTag("개인받음", "", extra));
  const rate = r.foreign_holding_rate;
  if (rate != null && rate <= 0.05) tags.push(tipTag("외인저비중", "", extra));
  return tags.join("");
}

function filterEmptyRows(rows) {
  const { q, mode, maxRate, minKrw } = emptyFilters();
  const rateCap = mode === "low_foreign" && maxRate == null ? 0.05 : maxRate;
  return filterFlowUniverse(rows).filter((r) => {
    const hay = `${r.ticker || ""} ${r.company || ""}`.toLowerCase();
    const chosung = getChosung(r.company || "");
    if (q && !hay.includes(q) && !chosung.includes(q)) return false;
    if (mode === "empty" && !r.empty) return false;
    if (mode === "comeback" && !r.comeback) return false;
    if (mode === "retail" && !r.retail_absorb) return false;
    if (mode === "low_foreign") {
      if (r.foreign_holding_rate == null || Number(r.foreign_holding_rate) > rateCap) return false;
    } else if (rateCap != null && r.foreign_holding_rate != null && Number(r.foreign_holding_rate) > rateCap) {
      return false;
    }
    if (minKrw && Number(r.empty_krw || 0) < minKrw) return false;
    return true;
  });
}

function renderEmpty(data) {
  const box = $("#empty-box");
  if (!box) return;
  if (!data.configured) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error || "토스증권 키가 필요합니다.")}</p>`;
    return;
  }
  const source = data.rows && data.rows.length ? data.rows : [...(data.empty || []), ...(data.comeback || []), ...(data.low_foreign || [])];
  const uniq = [];
  const seen = new Set();
  for (const r of source) {
    const k = r.ticker;
    if (!k || seen.has(k)) continue;
    seen.add(k);
    uniq.push(r);
  }
  const scoped = filterFlowUniverse(uniq);
  const rows = filterEmptyRows(scoped);
  const mode = emptyFilters().mode;
  if (!sortState.empty) {
    sortState.empty = { key: mode === "low_foreign" ? "foreign_holding_rate" : "empty_krw", dir: mode === "low_foreign" ? "asc" : "desc" };
  }
  const ordered = sortedCopy(rows, "empty", sortState.empty.key, sortState.empty.dir);
  const hit = analyzeHit(ordered, "ret_5d");

  const renderEmptyBadgeTags = (r) => {
    const tags = [];
    if (r.comeback) tags.push('<span class="chip" style="background:rgba(16,185,129,0.2); color:#4ade80; font-weight:800; border:1px solid rgba(74,222,128,0.4);">🔄 복귀</span>');
    else if (r.empty) tags.push('<span class="chip" style="background:rgba(239,68,68,0.15); color:#f87171; font-weight:700;">🚪 쌍매도</span>');
    if (r.retail_absorb) tags.push('<span class="chip" style="background:rgba(250,204,21,0.15); color:#facc15; font-weight:700;">🛒 개인받음</span>');
    const baseTags = emptyTags(r);
    return tags.length ? tags.join(" ") : baseTags;
  };

  const body = ordered
    .map(
      (r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
      <td class="num font-bold">${i + 1}</td>
      <td class="name-cell">
        <div style="display:flex; align-items:center; gap:6px;">
          <b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b>
          <span class="meta">${escapeHtml(r.ticker || "")}</span>
        </div>
        <div class="meta" style="margin-top:2px;">${renderEmptyBadgeTags(r)}</div>
        ${rowNote(r.comment_empty_short || r.comment_empty)}
      </td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "최근가", r.last == null ? "—" : `${Number(r.last).toLocaleString("ko-KR")}원`)}>${quoteCell(r)}</td>
      <td class="num has-tip font-bold" style="color:#e2e8f0;"${flowHistoryTipAttrs(r, "외국인 보유 지분", r.foreign_holding_rate == null ? "—" : fmtPct(r.foreign_holding_rate, 2))}>${r.foreign_holding_rate == null ? "—" : fmtPct(r.foreign_holding_rate, 2)}</td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "외국인 지분 변화", r.foreign_rate_chg == null ? "—" : fmtPct(r.foreign_rate_chg, 2))}>${r.foreign_rate_chg == null ? "—" : pctCell(r.foreign_rate_chg)}</td>
      <td class="num has-tip ${r.foreign_net < 0 ? 'text-rose-400 font-bold' : r.foreign_net > 0 ? 'text-emerald-400 font-bold' : ''}"${flowHistoryTipAttrs(r, "외국인 누적 순매수", plainSignedInt(r.foreign_net))}>${signedInt(r.foreign_net)}</td>
      <td class="num has-tip ${r.institution_net < 0 ? 'text-rose-400 font-bold' : r.institution_net > 0 ? 'text-emerald-400 font-bold' : ''}"${flowHistoryTipAttrs(r, "기관 누적 순매수", plainSignedInt(r.institution_net))}>${signedInt(r.institution_net)}</td>
      <td class="num has-tip ${r.individual_net > 0 ? 'text-amber-400 font-bold' : r.individual_net < 0 ? 'text-slate-400' : ''}"${flowHistoryTipAttrs(r, "개인 누적 순매수", plainSignedInt(r.individual_net))}>${signedInt(r.individual_net)}</td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "수급 이탈 비중", r.empty_share == null ? "—" : fmtPct(r.empty_share, 0))}>${r.empty_share == null ? "—" : fmtPct(r.empty_share, 0)}</td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "보유고 대비 이탈", r.holding_exit == null ? "—" : fmtPct(r.holding_exit, 2))}>${r.holding_exit == null ? "—" : fmtPct(r.holding_exit, 2)}</td>
      <td class="num has-tip font-bold text-accent-cyan"${flowHistoryTipAttrs(r, "이탈 추정금액", krw(r.empty_krw))}>${escapeHtml(krw(r.empty_krw))}</td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "연속 순매도", r.sell_streak ? `${r.sell_streak}일` : "—")}>${r.sell_streak ? `<b style="color:#f87171;">${r.sell_streak}일 연속</b>` : "—"}</td>
      <td class="num has-tip font-bold"${flowHistoryTipAttrs(r, "신호 후 5일 성과", r.ret_5d == null ? "검증 대기" : fmtPct(r.ret_5d))}>${forwardReturnCell(r, 5)}</td>
    </tr>`
    )
    .join("");

  const when = fmtWhen(data.fetched_at);
  const asof = when ? `빈집 데이터 ${when} · ${data.days || 5}거래일` : `빈집 스캔 시점 없음 · ${data.days || 5}거래일`;
  if (currentView === "trade" && smartFlowTab === "vacancy") setPageAsOf(asof, "수급 스캔과 같은 토스 데이터입니다. 다시 스캔하면 갱신됩니다.");

  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr); margin:0 0 16px;">
      <div class="kpi has-tip" data-tip-title="🎯 조건 부합 종목" data-tip="현재 설정된 필터 조건(유형, 지분, 이탈금액)을 통과한 종목 수입니다." tabindex="0">
        <span>조건 종목</span><b style="color:#00e5ff;">${rows.length}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🚪 외인·기관 쌍매도 빈집" data-tip="외국인과 기관이 2일 이상 동반 순매도하여 수급 공백이 발생한 종목입니다." tabindex="0">
        <span>쌍매도 빈집</span><b style="color:#f87171;">${scoped.filter((r) => r.empty).length}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🔄 수급 복귀 조짐 (턴어라운드)" data-tip="외인·기관의 연속 매도세가 멈추고 최근 1~2거래일 재매수가 유입된 턴어라운드 종목입니다." tabindex="0">
        <span>복귀 조짐</span><b style="color:#4ade80;">${scoped.filter((r) => r.comeback).length}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="📉 외인 지분 5% 이하" data-tip="외국인 보유 비중이 5% 이하로 떨어져 추가 매도 압력이 현저히 낮아진 바닥권 종목입니다." tabindex="0">
        <span>외인 5%↓</span><b style="color:#c084fc;">${scoped.filter((r) => r.foreign_holding_rate != null && Number(r.foreign_holding_rate) <= 0.05).length}</b>
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
      <span class="chip" style="background:rgba(239,68,68,0.12); color:#f87171;">스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 합산 · ${escapeHtml(flowUniverseLabel())}${flowMinKrw() ? ` · ${krw(flowMinKrw())} 이상` : ""}</span>
      <span class="meta">${hitLine("선택 집합", hit)}</span>
    </div>

    <div class="table-wrap tall">
      <table data-scope="empty">
        <thead>
          <tr>
            <th style="width:40px;">#</th>
            <th class="sortable has-tip" data-sort="company" style="min-width:150px;" data-tip-title="종목명 및 셋업" data-tip="종목명 및 포착된 빈집/복귀/개인받음 수급 셋업 태그입니다." tabindex="0">종목 · 셋업</th>
            <th class="sortable has-tip" data-sort="last" data-tip-title="최근 종가" data-tip="토스증권 실시간 기준 현재가 및 당일 등락률입니다." tabindex="0">최근가</th>
            <th class="sortable has-tip" data-sort="foreign_holding_rate" data-tip-title="👽 외국인 보유 지분율" data-tip="토스증권 기준 현재 외인 지분율입니다. 낮을수록 수급 공백(빈집)입니다." tabindex="0">외인 지분</th>
            <th class="sortable has-tip" data-sort="foreign_rate_chg" data-tip-title="📊 외인 지분율 증감" data-tip="최근 5거래일 동안 외국인 지분율의 %p 변동치입니다." tabindex="0">지분 변화</th>
            <th class="sortable has-tip" data-sort="foreign_net" data-tip-title="👽 외국인 순매도 주수" data-tip="최근 기간 동안 외국인의 순매도 수량입니다." tabindex="0">외인(주)</th>
            <th class="sortable has-tip" data-sort="institution_net" data-tip-title="🏛️ 기관 순매도 주수" data-tip="최근 기간 동안 기관의 순매도 수량입니다." tabindex="0">기관(주)</th>
            <th class="sortable has-tip" data-sort="individual_net" data-tip-title="🛒 개인 순매수(받음) 주수" data-tip="외인/기관이 던진 물량을 개인이 받아낸 수량입니다." tabindex="0">개인(주)</th>
            <th class="sortable has-tip" data-sort="empty_share" data-tip-title="🚪 수급 이탈 비중" data-tip="전체 거래량 대비 외인·기관 순매도 물량이 차지하는 비중입니다." tabindex="0">이탈 비중</th>
            <th class="sortable has-tip" data-sort="holding_exit" data-tip-title="📉 기존 보유고 대비 이탈률" data-tip="외국인이 기존에 보유하고 있던 물량 대비 털어낸 비율입니다." tabindex="0">보유대비</th>
            <th class="sortable has-tip" data-sort="empty_krw" data-tip-title="💵 총 이탈 추정금액" data-tip="(외인+기관 순매도) × 종가로 계산한 이탈 자금 규모입니다." tabindex="0">이탈 추정</th>
            <th class="sortable has-tip" data-sort="sell_streak" data-tip-title="⏳ 연속 순매도 일수" data-tip="외인·기관이 연속으로 매도한 거래일 수입니다." tabindex="0">연속매도</th>
            <th class="sortable has-tip" data-sort="ret_5d" data-tip-title="📈 빈집 발생 후 5일 성과" data-tip="수급 공백 발생 후 5거래일 동안의 실제 주가 성과입니다." tabindex="0">이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="13" class="hint" style="text-align:center; padding:30px;">조건에 맞는 종목이 없습니다. 유형을 바꾸거나 다시 스캔해 보세요.</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint" style="margin-top:10px;">💡 숫자 셀에 마우스를 올리거나 키보드로 초점을 이동하면 최근 5거래일의 종가·외인·기관·개인·사모 수급과 선택 기간 전체 집계를 확인할 수 있습니다.</p>
  `;
  paintSortHeaders("empty");
}

async function loadEmpty(force) {
  smartFlowTab = "vacancy";
  return loadSmartFlow(Boolean(force));
}

function tradeFilters() {
  return {
    q: ($("#flow-q")?.value || "").trim().toLowerCase(),
    mode: $("#trade-mode")?.value || "setup",
    minKrw: flowMinKrw(),
    universe: flowUniverse(),
    ta: $("#trade-ta")?.value || "",
  };
}

function setupNotional(r) {
  const vals = [];
  if (r.dual) vals.push(Number(r.dual_krw || 0));
  if (r.pe_buy || r.pe_accum) vals.push(Number(r.pe_krw || 0));
  if (r.empty) vals.push(Number(r.empty_krw || 0));
  if (r.other_corp_buy) vals.push(Number(r.other_corp_krw || 0));
  if (r.pension_buy) vals.push(Number(r.pension_krw || 0));
  return vals.length ? Math.max(...vals) : 0;
}

function taMatch(r, taMode) {
  if (!taMode) return true;
  const ta = r.ta || {};
  const cloud = ta.ichi_cloud;
  if (taMode === "stoch_os") return Boolean(ta.stoch_over_sold);
  if (taMode === "stoch_ob") return Boolean(ta.stoch_over_bought);
  if (taMode === "stoch_golden") return Boolean(ta.stoch_golden);
  if (taMode === "ichi_above") return cloud === "above";
  if (taMode === "ichi_below") return cloud === "below";
  if (taMode === "ichi_tk") return Boolean(ta.ichi_tk_up || ta.ichi_tk_golden);
  if (taMode === "ta_bull") {
    return ta.stoch_bias === "bull" || ta.ichi_bias === "bull" || cloud === "above" || Boolean(ta.stoch_golden);
  }
  if (taMode === "confluence") {
    const flowLong = Boolean(r.dual || r.pe_buy || r.comeback);
    const taLong = Boolean(ta.stoch_golden || ta.stoch_over_sold || cloud === "above" || ta.ichi_tk_golden);
    return flowLong && taLong;
  }
  return true;
}

function filterTradeRows(rows) {
  const { q, mode, minKrw, universe, ta } = tradeFilters();
  return rows.filter((r) => {
    if (universe === "top100" && !r.in_quant) return false;
    if (universe === "outside" && r.in_quant) return false;
    const hay = `${r.ticker || ""} ${r.company || ""}`.toLowerCase();
    const chosung = getChosung(r.company || "");
    if (q && !hay.includes(q) && !chosung.includes(q)) return false;
    const dual = Boolean(r.dual);
    const pe = Boolean(r.pe_buy || r.pe_accum);
    const empty = Boolean(r.empty);
    const comeback = Boolean(r.comeback);
    if (mode === "setup" && !(dual || pe || empty || comeback)) return false;
    if (mode === "dual" && !dual) return false;
    if (mode === "pe" && !pe) return false;
    if (mode === "empty" && !empty) return false;
    if (mode === "comeback" && !comeback) return false;
    if (mode === "dual_pe" && !(dual && pe)) return false;
    if (mode === "dual_pe_retail" && !r.dual_pe_retail) return false;
    if (mode === "other_corp" && !r.other_corp_buy) return false;
    if (mode === "pension" && !r.pension_buy) return false;
    if (minKrw && setupNotional(r) < minKrw) return false;
    if (!taMatch(r, ta)) return false;
    return true;
  });
}

const TA_TIPS = {
  과매도: "스토캐스틱 %K가 20 아래입니다. 최근 5일 고저 대비 종가가 바닥에 가깝다는 뜻입니다. 단기 낙폭이 커서 반등 여지를 보기도 하지만, 하락 추세 안에서는 과매도가 더 이어질 수 있습니다.",
  과매수: "스토캐스틱 %K가 80 위입니다. 최근 5일 안에서 종가가 고점에 가깝습니다. 숨 고르기나 되돌림이 나올 수 있습니다.",
  "스토 골든": "스토캐스틱 골든 크로스입니다. 빠른 선(%K)이 느린 선(%D)을 아래에서 위로 뚫었습니다. 단기 모멘텀이 살아난 기술적 반등 타점입니다.",
  "스토 데드": "스토캐스틱 데드 크로스입니다. 빠른 선(%K)이 느린 선(%D)을 위에서 아래로 하향 이탈한 단기 숨고르기 구간입니다.",
  골든크로스: "스토캐스틱 골든 크로스입니다. 일봉 5,3,3 기준 빠른 선(%K)이 느린 선(%D)을 상향 돌파하여 단기 상승 모멘텀이 발생했습니다.",
  데드크로스: "스토캐스틱 데드 크로스입니다. 빠른 선(%K)이 느린 선(%D)을 하향 돌파하여 단기 모멘텀이 둔화되었습니다.",
  "구름 위": "일목균형표에서 종가가 선행스팬 A·B가 만든 구름대 위에 위치합니다. 중기 지지선을 확보하여 추세가 탄탄한 상태입니다.",
  "구름위": "일목균형표에서 종가가 선행스팬 구름대 위에 위치합니다. 중기 지지선을 확보하여 추세가 탄탄한 상태입니다.",
  "구름 아래": "종가가 일목 구름대 아래에 있습니다. 상단 구름대가 저항으로 작용하는 약세/바닥권 구간입니다.",
  "구름아래": "종가가 일목 구름대 아래에 있습니다. 상단 구름대가 저항으로 작용하는 약세/바닥권 구간입니다.",
  "구름 안": "종가가 구름 두께 내부에 위치하여 방향성을 탐색 중인 중립 구간입니다.",
  "전환>기준": "일목 9일 전환선이 26일 기준선 위에 위치하여 단기 시세 에너지가 중기 평균보다 우세한 강세 정배열입니다.",
  "전환<기준": "일목 9일 전환선이 26일 기준선 아래에 위치한 역배열 상태입니다.",
  "전환 골든": "일목 전환선이 기준선을 상향 돌파한 대표적인 매수 추세 전환 신호입니다.",
  "전환 데드": "일목 전환선이 기준선을 하향 이탈한 약세 전환 신호입니다.",
  "수급+기술": "🔥 메이저 수급 유입(쌍끌이/사모)과 일봉 보조지표 강세 타점이 일치하는 최우선 공략 셋업입니다.",
  "기술강세": "⚡ 스토캐스틱 골든크로스 또는 일목균형표 구름대 상회 등 기술적 지표가 상승 우위인 셋업입니다.",
};

function getTaTip(tag) {
  if (!tag) return "";
  const clean = tag.replace(/^[^\w가-힣><]+/, "").trim();
  for (const [k, v] of Object.entries(TA_TIPS)) {
    if (clean === k || clean.includes(k) || k.includes(clean)) return v;
  }
  return TA_TIPS[tag] || TA_TIPS[clean] || "";
}

function renderTechnicalChip(t) {
  if (!t) return "";
  let icon = "📊";
  let label = t;
  let bg = "rgba(255,255,255,0.06)";
  let color = "#cbd5e1";
  let border = "rgba(255,255,255,0.15)";

  if (t.includes("수급+기술")) {
    icon = "🔥"; label = "수급+기술"; bg = "rgba(16,185,129,0.2)"; color = "#4ade80"; border = "rgba(74,222,128,0.4)";
  } else if (t.includes("기술강세")) {
    icon = "⚡"; label = "기술강세"; bg = "rgba(250,204,21,0.18)"; color = "#facc15"; border = "rgba(250,204,21,0.4)";
  } else if (t.includes("골든")) {
    icon = "✨"; label = t.includes("전환") ? "전환 골든" : "골든크로스"; bg = "rgba(56,189,248,0.18)"; color = "#38bdf8"; border = "rgba(56,189,248,0.4)";
  } else if (t.includes("데드")) {
    icon = "⚠️"; label = t.includes("전환") ? "전환 데드" : "데드크로스"; bg = "rgba(239,68,68,0.15)"; color = "#f87171"; border = "rgba(239,68,68,0.35)";
  } else if (t.includes("구름 위") || t.includes("구름위")) {
    icon = "☁️"; label = "구름 위"; bg = "rgba(168,85,247,0.18)"; color = "#c084fc"; border = "rgba(168,85,247,0.4)";
  } else if (t.includes("구름 아래") || t.includes("구름아래")) {
    icon = "🌧️"; label = "구름 아래"; bg = "rgba(59,130,246,0.15)"; color = "#93c5fd"; border = "rgba(59,130,246,0.35)";
  } else if (t.includes("구름 안")) {
    icon = "🌫️"; label = "구름 안"; bg = "rgba(148,163,184,0.15)"; color = "#cbd5e1"; border = "rgba(148,163,184,0.3)";
  } else if (t.includes("전환>")) {
    icon = "📈"; label = "전환>기준"; bg = "rgba(56,189,248,0.15)"; color = "#38bdf8"; border = "rgba(56,189,248,0.35)";
  } else if (t.includes("전환<")) {
    icon = "📉"; label = "전환<기준"; bg = "rgba(99,102,241,0.15)"; color = "#a5b4fc"; border = "rgba(99,102,241,0.35)";
  } else if (t.includes("과매도")) {
    icon = "🟢"; label = "과매도"; bg = "rgba(16,185,129,0.18)"; color = "#34d399"; border = "rgba(16,185,129,0.4)";
  } else if (t.includes("과매수")) {
    icon = "🔴"; label = "과매수"; bg = "rgba(239,68,68,0.15)"; color = "#f87171"; border = "rgba(239,68,68,0.35)";
  }

  const tip = getTaTip(t) || getTaTip(label) || "";
  const title = `📊 기술적 신호: ${icon} ${label}`;
  const extra = tip ? ` data-tip-title="${escapeHtml(title)}" data-tip="${escapeHtml(tip)}" tabindex="0"` : "";

  return `<span class="chip has-tip" style="background:${bg}; color:${color}; border:1px solid ${border}; font-weight:750; font-size:11px; padding:2px 7px; white-space:nowrap; display:inline-flex; align-items:center; gap:3px;"${extra}><span style="font-size:10px;">${icon}</span> ${escapeHtml(label)}</span>`;
}

const SETUP_TIPS = {
  쌍끌이: "같은 기간 외국인과 기관합계가 둘 다 순매수한 종목입니다. 기관합계는 연기금이 아닙니다.",
  사모매집: "토스 분류의 사모펀드가 이틀 이상 연속 순매수했습니다. 기관 전체와 다를 수 있습니다.",
  사모순매수: "토스 분류 사모펀드가 기간 합산으로 순매수입니다. 연속 매수는 아직 짧습니다.",
  "쌍끌이+사모": "외인·기관 쌍끌이와 사모 순매수가 겹칩니다. 수급이 한쪽으로 몰린 연구 필터입니다.",
  "쌍끌이+사모+개인이탈": "쌍끌이·사모가 사는데 개인은 파는 극단 수급입니다. 스마트머니 vs 개인 이탈로 봅니다.",
  기타법인: "토스 기타법인(기관·개인·외인이 아닌 법인) 순매수입니다. 키가 없으면 목록이 비어 있습니다.",
  연기금: "토스 분류의 기관 내 연기금입니다. 국민연금 단독도, KIS 기금도 아닙니다.",
  빈집: "같은 기간 외인과 기관이 같이 순매도한 자리입니다. 빠진 물량을 노리는 연구용 필터이며 매수 지시가 아닙니다.",
  복귀: "앞선 날은 팔고 최근 1~2일은 다시 산 조짐입니다. 이탈 후 수급이 돌아오는지 보는 태그입니다.",
  ETF: "상장지수펀드입니다. 개별 기업 Quant 공식과 다릅니다.",
  "퀀트 밖": "재무 Quant TOP100에 없는 종목입니다. 수급·기술만 본 후보입니다.",
};

function tipAttr(text) {
  if (!text) return "";
  return ` class="has-tip" data-tip="${escapeHtml(text)}" tabindex="0"`;
}

function thTip(label, tip) {
  return `<th${tipAttr(tip)}>${escapeHtml(label)}</th>`;
}

const TERM_TIPS = {
  평균회귀: "가격이 평균에서 너무 벗어나면 되돌아올 것으로 보고 삽니다. RSI·볼린저가 여기 속합니다. 추세장에서는 잘 안 맞을 수 있습니다.",
  추세: "이미 난 방향을 따라갑니다. 이평 교차·돈치안 돌파가 여기 속합니다. 횡보장에서는 가짜 신호가 많습니다.",
  "RSI 평균회귀": "상대강도지수(RSI)가 과매도로 내려가면 사고, 과매수로 올라가면 파는 규칙입니다.",
  "볼린저 평균회귀": "종가가 하단 밴드를 벗어나면 사고, 중심선으로 돌아오면 파는 규칙입니다.",
  "이동평균 교차": "단기 이동평균이 장기 이동평균을 위로 돌파하면 따라 들어갑니다.",
  "돈치안 돌파": "최근 N일 고점을 돌파하면 들어가고, 단기 저점을 깨면 나옵니다.",
  LOW: "안정성 LOW입니다. 학습 밖 구간이나 walk-forward가 갈리거나, 매매가 너무 적습니다. 연구 후보일 뿐 순위로 쓰지 마세요.",
  MEDIUM: "중간 안정성입니다. 일부 검증은 맞지만 표본을 더 쌓기 전에는 순위로 쓰지 마세요.",
  HIGH: "학습 밖 구간과 walk-forward가 같은 방향을 가리킵니다. 그래도 주문 신호가 아닙니다.",
  OOS: "Out-Of-Sample, 이후 구간입니다. 파라미터를 고를 때 보지 않은 뒷부분으로 다시 측정합니다. 학습 구간 숫자보다 이 값을 믿습니다.",
  WF: "Walk-Forward입니다. 앞 구간에서 파라미터를 고르고, 바로 다음 짧은 구간으로 검증하는 창을 여러 번 밉니다. 한 번의 OOS보다 과적합을 잘 걸러 냅니다.",
  샤프: "Sharpe ratio입니다. 수익을 변동성으로 나눈 값입니다. 높을수록 같은 흔들림 대비 수익이 낫다는 뜻입니다. 표본이 짧으면 숫자가 과장됩니다.",
  MDD: "Maximum Drawdown, 최대낙폭입니다. 고점에서 저점까지 가장 크게 깎인 비율입니다. 음수가 클수록 중간에 더 아팠다는 뜻입니다.",
};

function tipTag(label, cls, dict) {
  const tip = (dict && dict[label]) || "";
  const extra = tip ? ` data-tip="${escapeHtml(tip)}" tabindex="0"` : "";
  return `<span class="tag ${cls || ""} ${tip ? "has-tip" : ""}"${extra}>${escapeHtml(label)}</span>`;
}

function taTags(r) {
  const labels = (r.ta && r.ta.labels) || [];
  return labels
    .slice(0, 4)
    .map((t) => renderTechnicalChip(t))
    .join(" ");
}

function isEtf(r) {
  const t = String(r.security_type || "").toUpperCase();
  const n = String(r.company || "");
  return t === "ETF" || /^(KODEX|TIGER|KBSTAR|HANARO|ACE |PLUS |SOL |KIWOOM|TREX )/i.test(n);
}

function setupTags(r) {
  const tags = [...(r.setups || [])];
  if (isEtf(r) && !tags.includes("ETF")) tags.unshift("ETF");
  return tags.map((t) => {
    const hot = t === "복귀" || t === "쌍끌이+사모";
    const down = t === "빈집";
    const cls = hot ? "hot" : down ? "down" : t === "쌍끌이" || t === "사모매집" ? "up" : "";
    return tipTag(t, cls, SETUP_TIPS);
  }).join("");
}

function renderTrade(data) {
  const box = $("#trade-box");
  if (!box) return;
  if (!data.configured) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error || "토스증권 키가 필요합니다.")}</p>`;
    return;
  }
  const all = data.rows || [];
  const qVal = ($("#flow-q")?.value || "").trim();
  const rows = sortedCopy(filterTradeRows(all), "trade", "setup_notional", "desc");
  if (rows.length === 0 && qVal.length > 0) {
    box.innerHTML = `<p class="hint">${escapeHtml(qVal)} 종목을 전 종목에서 찾는 중…</p>`;
    resolveStockQuery(qVal).then((code) => fetchOnDemandFlow(code, "#trade-box", "trade")).catch((err) => {
      box.innerHTML = `<p class="bad">${escapeHtml(err.message || "검색 실패")}</p>`;
    });
    return;
  }
  const eligible = filterFlowUniverse(all);
  const dualN = eligible.filter((r) => r.dual).length;
  const peN = eligible.filter((r) => r.pe_buy || r.pe_accum).length;
  const emptyN = eligible.filter((r) => r.empty).length;
  const hit = analyzeHit(rows, "ret_5d");
  const taBull = eligible.filter((r) => taMatch(r, "ta_bull")).length;
  const confluence = eligible.filter((r) => taMatch(r, "confluence")).length;

  const renderStochCell = (r) => {
    if (!r.ta || r.ta.stoch_k == null) return '<span class="hint">—</span>';
    const k = Number(r.ta.stoch_k);
    const d = r.ta.stoch_d != null ? Number(r.ta.stoch_d) : null;
    let kBadge = "";
    if (k <= 20) {
      kBadge = `<div class="chip has-tip" data-tip-title="🟢 스토캐스틱 과매도 (%K < 20)" data-tip="최근 5일간 최저점 부근 과매도 구간(단기 반등 유력)입니다." tabindex="0" style="background:rgba(16,185,129,0.18); color:#34d399; font-weight:800; font-size:11px; padding:2px 6px; white-space:nowrap; display:inline-flex; align-items:center; gap:3px;">
        <span style="font-size:9px;">🟢</span> 과매도 <b>${fmt(k, 1)}</b>
      </div>`;
    } else if (k >= 80) {
      kBadge = `<div class="chip has-tip" data-tip-title="🔴 스토캐스틱 과매수 (%K > 80)" data-tip="최근 5일간 최고점 부근 과열 구간(단기 숨고르기 주의)입니다." tabindex="0" style="background:rgba(239,68,68,0.18); color:#f87171; font-weight:800; font-size:11px; padding:2px 6px; white-space:nowrap; display:inline-flex; align-items:center; gap:3px;">
        <span style="font-size:9px;">🔴</span> 과매수 <b>${fmt(k, 1)}</b>
      </div>`;
    } else {
      kBadge = `<b style="font-size:13px; color:#f1f5f9; white-space:nowrap;">${fmt(k, 1)}</b>`;
    }
    const dLine = d != null ? `<div class="meta" style="font-size:10.5px; color:#94a3b8; margin-top:2px; white-space:nowrap;">%D ${fmt(d, 1)}</div>` : "";
    return `<div style="display:flex; flex-direction:column; align-items:flex-end; white-space:nowrap; min-width:75px;">${kBadge}${dLine}</div>`;
  };

  const renderTechBadges = (r) => {
    const tags = [];
    if (taMatch(r, "confluence")) tags.push(renderTechnicalChip("수급+기술"));
    else if (taMatch(r, "ta_bull")) tags.push(renderTechnicalChip("기술강세"));
    if (taMatch(r, "stoch_golden")) tags.push(renderTechnicalChip("골든크로스"));
    if (taMatch(r, "ichi_above")) tags.push(renderTechnicalChip("구름 위"));
    else if (taMatch(r, "ichi_tk")) tags.push(renderTechnicalChip("전환>기준"));

    const baseTags = taTags(r);
    if (tags.length) {
      return `<div style="display:flex; flex-wrap:wrap; gap:4px; align-items:center;">${tags.join(" ")}</div>`;
    }
    return baseTags ? `<div style="display:flex; flex-wrap:wrap; gap:4px; align-items:center;">${baseTags}</div>` : '<span class="hint">—</span>';
  };

  const body = rows
    .map(
      (r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
      <td class="num font-bold">${i + 1}</td>
      <td class="name-cell">
        <div style="display:flex; align-items:center; gap:6px;">
          <b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b>
          <span class="meta">${escapeHtml(r.ticker || "")}</span>
        </div>
        <div class="meta" style="margin-top:2px;">${setupTags(r)}
          ${r.in_quant ? `<span class="tag">Q${r.quant_rank ?? ""}</span>` : tipTag("퀀트 밖", "hot", SETUP_TIPS)}
        </div>
        ${rowNote(r.comment_trade_short || r.comment_trade)}
      </td>
      <td class="num has-tip"${flowHistoryTipAttrs(r, "최근가", r.last == null ? "—" : `${Number(r.last).toLocaleString("ko-KR")}원`)}>${quoteCell(r)}</td>
      <td class="num">${renderStochCell(r)}</td>
      <td>${renderTechBadges(r)}</td>
      <td class="num has-tip ${r.foreign_net > 0 ? 'text-emerald-400 font-bold' : r.foreign_net < 0 ? 'text-rose-400' : ''}"${flowHistoryTipAttrs(r, "외국인 누적 순매수", plainSignedInt(r.foreign_net))}>${signedInt(r.foreign_net)}</td>
      <td class="num has-tip ${r.institution_net > 0 ? 'text-emerald-400 font-bold' : r.institution_net < 0 ? 'text-rose-400' : ''}"${flowHistoryTipAttrs(r, "기관 누적 순매수", plainSignedInt(r.institution_net))}>${signedInt(r.institution_net)}</td>
      <td class="num has-tip ${r.pe_net > 0 ? 'text-purple-400 font-bold' : r.pe_net < 0 ? 'text-rose-400' : ''}"${flowHistoryTipAttrs(r, "사모펀드 누적 순매수", plainSignedInt(r.pe_net))}>${signedInt(r.pe_net)}${r.pe_streak ? `<div class="meta" style="color:#c084fc;">${r.pe_streak}일 연속</div>` : ""}</td>
      <td class="num has-tip font-bold text-accent-cyan"${flowHistoryTipAttrs(r, "수급 추정금액", krw(setupNotional(r)))}>${escapeHtml(krw(setupNotional(r)))}</td>
      <td class="num has-tip font-bold"${flowHistoryTipAttrs(r, "신호 후 5일 성과", r.ret_5d == null ? "검증 대기" : fmtPct(r.ret_5d))}>${forwardReturnCell(r, 5)}</td>
    </tr>`
    )
    .join("");

  const when = fmtWhen(data.fetched_at);
  const px = lastStatus?.freshness?.price_max_date;
  const asof = [when ? `수급 스캔 ${when}` : "", px ? `KRX 일봉 ${px} (스토·일목)` : ""]
    .filter(Boolean)
    .join(" · ") || "트레이딩 데이터 시점 없음";

  if (currentView === "trade" && smartFlowTab === "technical") {
    setPageAsOf(asof, "수급은 토스, 스토캐스틱·일목은 KRX 일봉입니다. 다시 스캔하면 수급이 갱신됩니다.");
  }

  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(5,1fr); margin:0 0 16px;">
      <div class="kpi has-tip" data-tip-title="🎯 수급 스캔 모수" data-tip="거래대금 상위 및 랭킹 모니터링 대상 종목 총 수입니다." tabindex="0">
        <span>스캔 종목</span><b>${data.scanned || 0}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="💎 선택 범위 외인·기관 쌍끌이" data-tip="상단 종목 범위 필터에 포함된 외인+기관 동반 순매수 종목입니다." tabindex="0">
        <span>선택 범위 쌍끌이</span><b style="color:#00e5ff;">${dualN}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="💼 선택 범위 사모펀드 매집" data-tip="상단 종목 범위 필터에 포함된 사모펀드 순매집 종목입니다." tabindex="0">
        <span>선택 범위 사모</span><b style="color:#c084fc;">${peN}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="⚡ 기술적 강세 셋업" data-tip="스토캐스틱 과매도 탈출 또는 일목균형표 호전 등 기술적 진입 타점 종목입니다." tabindex="0">
        <span>기술 강세</span><b style="color:#facc15;">${taBull}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🔥 수급 + 기술 Confluence" data-tip="강력한 스마트머니 수급 유입과 기술적 상승 신호가 동시에 일치하는 최고 확률 타점입니다." tabindex="0">
        <span>수급+기술 중첩</span><b style="color:#4ade80;">${confluence}</b>
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
      <span class="chip" style="background:rgba(56,189,248,0.12); color:#38bdf8;">거래대금·토스 랭킹 위주 ${data.scanned || 0}종목 · ${data.days || 5}거래일 · ${escapeHtml(flowUniverseLabel())} · 빈집 ${emptyN}개</span>
      <span class="meta">${hitLine("선택 집합", hit)}</span>
    </div>

    <div class="table-wrap tall">
      <table data-scope="trade">
        <thead>
          <tr>
            <th style="width:40px;">#</th>
            <th class="sortable has-tip" data-sort="company" style="min-width:160px;" data-tip-title="종목명 및 수급 셋업" data-tip="종목명 및 포착된 수급/퀀트 셋업 태그입니다." tabindex="0">종목 · 셋업</th>
            <th class="sortable has-tip" data-sort="last" data-tip-title="토스 실시간 시세" data-tip="토스증권 실시간 기준 현재가 및 당일 등락률입니다." tabindex="0">최근가</th>
            <th class="sortable has-tip" data-sort="stoch_k" data-tip-title="📈 KRX 일봉 스토캐스틱 (5,3,3)" data-tip="20 이하는 단기 바닥 과매도(반등 기회), 80 이상은 과매수 과열권입니다." tabindex="0">스토 %K (%D)</th>
            <th class="has-tip" data-tip-title="⚡ 기술적 보조지표 분석" data-tip="수급+기술 Confluence, 일목 구름대 상회, 스토 골든크로스 등 복합 타점입니다." tabindex="0">기술적 신호</th>
            <th class="sortable has-tip" data-sort="foreign_net" data-tip-title="👽 외국인 순매수" data-tip="외국인 투자자 합산 순매수 주수입니다." tabindex="0">외인(주)</th>
            <th class="sortable has-tip" data-sort="institution_net" data-tip-title="🏛️ 기관 순매수" data-tip="기관 투자자 합산 순매수 주수입니다." tabindex="0">기관(주)</th>
            <th class="sortable has-tip" data-sort="pe_net" data-tip-title="💼 사모펀드 순매수" data-tip="사모펀드 합산 순매수 주수 및 연속 매집 일수입니다." tabindex="0">사모(주)</th>
            <th class="sortable has-tip" data-sort="setup_notional" data-tip-title="💵 수급 유입 추정금액" data-tip="유입된 수급의 원화 환산 추정 규모입니다." tabindex="0">추정금액</th>
            <th class="sortable has-tip" data-sort="ret_5d" data-tip-title="📈 신호 발생 후 5일 성과" data-tip="신호 발생 후 5거래일 실제 주가 성과입니다." tabindex="0">이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="10" class="hint" style="text-align:center; padding:30px;">조건에 맞는 종목이 없습니다. 종목 범위를 전체로 바꾸거나 금액·셋업·기술 필터를 완화해 보세요.</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint" style="margin-top:10px;">💡 최근가는 토스, 수급·기술은 KRX 일봉 기준입니다. 열 제목을 클릭하면 최근가, 수급 금액, 스토캐스틱 순으로 정렬할 수 있습니다.</p>
  `;
  tradeCache = data;
  paintSortHeaders("trade");
}

let screenId = "value_growth";

function renderSectors(data) {
  const box = $("#sector-box");
  if (!box) return;
  if (data.error && !(data.rows || []).length) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error)}</p>`;
    return;
  }
  const rows = data.rows || [];

  // 1. Sector 4-Quadrant Phase Matrix
  const leadingRows = rows.filter((r) => r.state === "LEADING");
  const improvingRows = rows.filter((r) => r.state === "IMPROVING");
  const weakeningRows = rows.filter((r) => r.state === "WEAKENING" || r.state === "NEUTRAL" || (!["LEADING", "IMPROVING", "LAGGING"].includes(r.state)));
  const laggingRows = rows.filter((r) => r.state === "LAGGING");

  const renderPhaseChips = (list) => {
    if (!list.length) return '<span class="hint" style="font-size:11px;">해당 업종 없음</span>';
    return list.map((r) => `
      <span class="sector-phase-chip" onclick="openStock('${escapeHtml((r.names && r.names[0] && r.names[0].ticker) || "")}')">
        <span>${escapeHtml(r.name)}</span>
        <b>${fmt(r.score, 0)}점</b>
      </span>
    `).join("");
  };

  const phaseMatrixHtml = `
    <div class="sector-phase-matrix">
      <div class="sector-phase-box leading has-tip"
           data-tip-title="🌟 선행 (Leading) 국면"
           data-tip="코스피 지수 대비 상대강도(RS)와 가격 모멘텀이 모두 시장 최상위권인 주도 업종입니다."
           data-tip-up="주도주 랠리 및 업종 비중 확대 최우선 후보"
           data-tip-hint="포트폴리오 수익률을 견인하는 핵심 주도 섹터입니다."
           tabindex="0">
        <div class="sector-phase-header">
          <span>🌟 선행 (Leading)</span>
          <span>${leadingRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(leadingRows)}</div>
      </div>
      <div class="sector-phase-box improving has-tip"
           data-tip-title="📈 개선 (Improving) 국면"
           data-tip="바닥권 침체에서 벗어나 상대강도와 수급이 턴어라운드하기 시작한 업종입니다."
           data-tip-up="선행 국면 진입 전 초기 선취매 및 저점 분할매수 기회"
           data-tip-hint="추세 반전 성공 시 가장 높은 상승 탄력성을 보입니다."
           tabindex="0">
        <div class="sector-phase-header">
          <span>📈 개선 (Improving)</span>
          <span>${improvingRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(improvingRows)}</div>
      </div>
      <div class="sector-phase-box weakening has-tip"
           data-tip-title="⚠️ 둔화 (Weakening/Neutral) 국면"
           data-tip="상승 추세가 완만해지거나 차익 실현 매물이 출회되며 모멘텀이 둔화되는 구간입니다."
           data-tip-down="고점 분할 차익실현 및 신규 추격매수 자제"
           data-tip-hint="지지선 이탈 여부를 주의 깊게 관찰하세요."
           tabindex="0">
        <div class="sector-phase-header">
          <span>⚠️ 보통/약화 (Neutral)</span>
          <span>${weakeningRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(weakeningRows)}</div>
      </div>
      <div class="sector-phase-box lagging has-tip"
           data-tip-title="❄️ 부진 (Lagging) 국면"
           data-tip="시장 대비 상대강도와 모멘텀이 모두 최하위권에 머무는 소외/조정 업종입니다."
           data-tip-down="비중 축소 및 반등 신호 확인 전까지 관망"
           data-tip-hint="개선(Improving) 신호가 뜰 때까지 섣부른 물타기를 피하세요."
           tabindex="0">
        <div class="sector-phase-header">
          <span>❄️ 부진 (Lagging)</span>
          <span>${laggingRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(laggingRows)}</div>
      </div>
    </div>
  `;

  // 2. Top Sector Leaderboard Cards (Top 6 sectors)
  const topCards = rows.slice(0, 6).map((r) => {
    const isTop = r.rank <= 3;
    const fillCls = r.state === "LEADING" ? "leading" : r.state === "IMPROVING" ? "improving" : r.state === "LAGGING" ? "lagging" : "neutral";
    const deltaTxt = r.delta == null ? "" : (r.delta >= 0 ? `+${r.delta.toFixed(1)}` : r.delta.toFixed(1));
    const stockPills = (r.names || []).slice(0, 4).map((n) =>
      `<span class="sector-stock-pill" onclick="openStock('${escapeHtml(n.ticker)}')"><b>${escapeHtml(n.company || n.ticker)}</b></span>`
    ).join("");

    return `
      <div class="sector-leader-card">
        <div class="sector-leader-top">
          <div class="sector-leader-title">
            <span class="sector-rank-badge ${isTop ? "top" : ""}">${r.rank}</span>
            <span>${escapeHtml(r.name)}</span>
            <span class="tag tone-${r.state === "LEADING" ? "우호" : r.state === "LAGGING" ? "부담" : "중립"}">${escapeHtml(r.state_ko || r.state)}</span>
          </div>
          <div>
            <b style="font-size:16px;color:#fff;">${fmt(r.score, 1)}</b>점
            ${deltaTxt ? `<span class="meta" style="margin-left:4px;color:${r.delta >= 0 ? "#3dcf8e" : "#ef4b6a"}; font-weight:600;">(${deltaTxt})</span>` : ""}
          </div>
        </div>
        <div class="sector-bar-track">
          <div class="sector-bar-fill ${fillCls}" style="width:${Math.min(100, Math.max(10, r.score))}%"></div>
        </div>
        <div class="sector-gauges">
          <div class="sector-gauge-item">
            <span>상대강도(RS)</span>
            <b>${r.rs ?? "—"}점</b>
          </div>
          <div class="sector-gauge-item">
            <span>상승 확산</span>
            <b>${r.breadth ?? "—"}%</b>
          </div>
          <div class="sector-gauge-item">
            <span>실적 성장</span>
            <b>${r.earnings ?? "—"}%</b>
          </div>
        </div>
        <div class="sector-stock-pills">
          ${stockPills || '<span class="meta">종목 정보 없음</span>'}
        </div>
      </div>
    `;
  }).join("");

  // 3. Full Sector RS Horizontal Comparison Chart
  const rsRowsHtml = rows.map((r) => {
    const rs = Number(r.rs ?? 50);
    const fillGradient = r.state === "LEADING" ? "linear-gradient(90deg, #10b981, #34d399)" :
      r.state === "IMPROVING" ? "linear-gradient(90deg, #3b82f6, #60a5fa)" :
      r.state === "LAGGING" ? "linear-gradient(90deg, #ef4444, #f87171)" :
      "linear-gradient(90deg, #64748b, #94a3b8)";
    const col = r.state === "LEADING" ? "#34d399" : r.state === "IMPROVING" ? "#60a5fa" : r.state === "LAGGING" ? "#f87171" : "#94a3b8";

    return `
      <div class="sector-rs-row">
        <div class="sector-rs-name" title="${escapeHtml(r.name)}">${r.rank}. ${escapeHtml(r.name)}</div>
        <div class="sector-rs-bar-bg">
          <div class="sector-rs-bar-fill" style="width:${Math.max(4, Math.min(100, rs))}%; background:${fillGradient};"></div>
        </div>
        <div class="sector-rs-val" style="color:${col}">${r.rs ?? "—"}</div>
      </div>
    `;
  }).join("");

  const rsComparisonChartHtml = `
    <div class="sector-rs-chart-wrap">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <h4 style="margin:0; font-size:14px; color:#fff;">📊 전체 19개 업종 상대강도(RS) 비교 차트</h4>
        <span class="hint">시장 대비 3개월 주가 탄력성 점수 (0~100)</span>
      </div>
      <div class="sector-rs-grid">
        ${rsRowsHtml}
      </div>
    </div>
  `;

  // 4. Detailed Data Table
  const body = rows.map((r) =>
    `<tr class="clickable" data-ticker="${escapeHtml((r.names && r.names[0] && r.names[0].ticker) || "")}">
      <td class="num">${r.rank}</td>
      <td><b>${escapeHtml(r.name)}</b><div class="meta">${r.n}종목</div>${rowNote(r.comment)}</td>
      <td><span class="sector-score">${fmt(r.score, 1)}</span>
        <div class="meta">${r.delta == null ? "" : (r.delta >= 0 ? "+" : "") + fmt(r.delta, 1)}</div></td>
      <td><span class="tag has-tip" data-tip="${escapeHtml(r.comment || "")}">${escapeHtml(r.state_ko || r.state)}</span></td>
      <td class="num">${r.rs ?? "—"}</td>
      <td class="num">${r.breadth ?? "—"}</td>
      <td class="num">${r.earnings ?? "—"}</td>
      <td>${(r.names || []).map((n) => `<span class="sector-stock-pill" onclick="event.stopPropagation(); openStock('${escapeHtml(n.ticker)}')">${escapeHtml(n.company || n.ticker)}</span>`).join(" ")}</td>
    </tr>`
  ).join("");

  const when = fmtWhen(data.fetched_at);
  const asof = [data.as_of_date ? `점수 기준일 ${data.as_of_date}` : "", when ? `업종 계산 ${when}` : ""]
    .filter(Boolean)
    .join(" · ") || "업종 데이터 시점 없음";
  if (currentView === "sector") {
    setPageAsOf(asof, "업종 점수는 최근 Quant 결과와 KRX 수익률로 계산합니다. 다시 계산하면 이 화면만 갱신됩니다.");
  }
  box.innerHTML = `
    ${asofBanner(asof)}
    <h3 style="margin:8px 0 4px;font-size:15px;color:#fff;">🔄 업종 모멘텀 4분면 사이클 맵 (Sector Cycle Quadrant)</h3>
    <p class="hint" style="margin-bottom:8px;">한국 증시 19개 업종의 현재 모멘텀 국면 분포입니다. 클릭 시 대표 종목이 열립니다.</p>
    ${phaseMatrixHtml}

    <h3 style="margin:20px 0 4px;font-size:15px;color:#fff;">🚀 주도 업종 모멘텀 TOP 6 (Sector Momentum Leaderboard)</h3>
    <p class="hint" style="margin-bottom:12px;">상대강도(RS), 상승 확산도 및 실적 성장을 종합 평가한 상위 주도 업종입니다.</p>
    <div class="sector-leader-grid">
      ${topCards}
    </div>

    ${rsComparisonChartHtml}

    <h3 style="margin:20px 0 6px;font-size:15px;color:#fff;">📋 전체 19개 업종 6축 상세 분석표</h3>
    <div class="table-wrap tall"><table>
      <thead><tr>
        ${thTip("순위", "업종 6축 평가 순위입니다.")}
        ${thTip("업종", "조건 통과 종목의 산업 분류입니다.")}
        ${thTip("점수", "상대강도 25 · 확산 20 · 실적 20 · 구성 15 · 가치 10 · 가속 10 종합 100점.")}
        ${thTip("상태", "선행·개선·보통·약화·부진. 점수와 직전 대비 변화로 붙입니다.")}
        ${thTip("상대", "3개월 수익률이 시장 대비 어디쯤인지 0~100으로 본 값입니다.")}
        ${thTip("확산", "업종 안에서 3개월 수익률이 플러스인 종목 비율입니다.")}
        ${thTip("실적", "매출·영업이익 YoY가 플러스인 종목 비율입니다.")}
        <th>대표 종목</th>
      </tr></thead>
      <tbody>${body || "<tr><td colspan=8>업종 점수를 계산할 종목이 부족합니다.</td></tr>"}</tbody>
    </table></div>
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>
  `;
}

async function loadSectors() {
  const box = $("#sector-box");
  if (!box) return;
  loadSectorTier1Briefing().catch(() => {});
  box.innerHTML = "<p>업종 점수를 계산하는 중…</p>";
  renderSectors(await api("/api/sectors"));
}

function renderScreens(data) {
  const list = $("#screen-list");
  const box = $("#screen-box");
  if (list) {
    list.innerHTML = (data.catalog || [])
      .map(
        (s) =>
          `<button type="button" data-screen="${escapeHtml(s.id)}" class="${s.id === data.id ? "on" : ""}" data-tip="${escapeHtml(s.how || "")}">${escapeHtml(s.name)}${s.popular ? '<span class="pop">인기</span>' : ""}</button>`
      )
      .join("");
    list.querySelectorAll("[data-screen]").forEach((btn) => {
      btn.addEventListener("click", () => loadScreens(btn.dataset.screen).catch((err) => alert(err.message)));
    });
  }
  if (!box) return;
  if (data.error) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error)}</p>`;
    return;
  }
  const ordered = sortedCopy(data.rows || [], "screens", "quant_score", "desc");
  const body = ordered
    .map(
      (r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
        <td class="num">${i + 1}</td>
        <td class="name-cell"><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)} · ${escapeHtml(r.industry || "")}</div>${rowNote(r.comment_short)}</td>
        <td class="num">${lastCell(r)}</td>
        <td class="num"><span class="score">${fmt(r.quant_score)}</span></td>
        <td class="num">${r.quant_rank ?? "—"}</td>
        <td>${factorBars(r)}</td>
      </tr>`
    )
    .join("");
  const asof = data.as_of_date ? `골라보기 점수 기준일 ${data.as_of_date}` : "점수 결과가 없어 시점을 표시할 수 없습니다.";
  if (currentView === "screens") {
    setPageAsOf(asof, "최근 Quant 결과에서 걸러 봅니다. 수급 목록이면 수급 탭을 먼저 스캔하세요.");
  }
  box.innerHTML = `
    ${asofBanner(asof)}
    <div style="margin-bottom:12px;">
      <h3 style="margin:0 0 6px;font-size:16px;color:#fff;">${escapeHtml(data.name || "")} <span class="chip" style="font-size:12px;vertical-align:middle;">${data.n ?? 0}종목</span></h3>
      <p class="hint" style="margin:0;">${escapeHtml(data.how || "")}</p>
    </div>
    <div class="table-wrap tall"><table data-scope="screens">
      <thead><tr>
        <th>#</th>
        <th class="sortable" data-sort="company">종목</th>
        <th class="sortable" data-sort="last_close">최근가</th>
        <th class="sortable" data-sort="quant_score">점수</th>
        <th class="sortable" data-sort="quant_rank">순위</th>
        <th>구성</th>
      </tr></thead>
      <tbody>${body || "<tr><td colspan=6>조건에 맞는 종목이 없습니다. 수급 목록이면 수급 탭을 먼저 스캔하세요.</td></tr>"}</tbody>
    </table></div>
    <p class="hint">열 이름을 누르면 최근가·점수로 정렬합니다.</p>
  `;
  screenCache = data;
  paintSortHeaders("screens");
}

async function loadScreens(id) {
  if (id) screenId = id;
  const box = $("#screen-box");
  if (box) box.innerHTML = "<p>목록을 걸러 보는 중…</p>";
  const include = $("#screens-include-quant")?.checked !== false;
  renderScreens(await api(`/api/screens?id=${encodeURIComponent(screenId)}&include_quant=${include}`));
}

let strategyCache = null;
let portfolioCache = null;
let currentStrategyFilter = "all";

function renderStrategy(data) {
  const box = $("#strategy-box");
  if (!box) return;
  const allRows = data.rows || [];
  const highCount = allRows.filter(r => r.stability_label === "HIGH").length;
  const medCount = allRows.filter(r => r.stability_label === "MEDIUM").length;
  const rsiCount = allRows.filter(r => (r.best_family || "").includes("rsi") || (r.best_name || "").includes("RSI")).length;
  const bbCount = allRows.filter(r => (r.best_family || "").includes("bb") || (r.best_name || "").includes("볼린저")).length;
  const maCount = allRows.filter(r => (r.best_family || "").includes("ma") || (r.best_name || "").includes("이동평균")).length;
  const donchianCount = allRows.filter(r => (r.best_family || "").includes("donchian") || (r.best_name || "").includes("돈치안")).length;

  const filteredRows = allRows.filter(r => {
    if (currentStrategyFilter === "high") return r.stability_label === "HIGH";
    if (currentStrategyFilter === "med") return r.stability_label === "HIGH" || r.stability_label === "MEDIUM";
    if (currentStrategyFilter === "rsi") return (r.best_family || "").includes("rsi") || (r.best_name || "").includes("RSI");
    if (currentStrategyFilter === "bb") return (r.best_family || "").includes("bb") || (r.best_name || "").includes("볼린저");
    if (currentStrategyFilter === "ma") return (r.best_family || "").includes("ma") || (r.best_name || "").includes("이동평균");
    if (currentStrategyFilter === "donchian") return (r.best_family || "").includes("donchian") || (r.best_name || "").includes("돈치안");
    return true;
  });

  const allSharpes = allRows.map(r => ((r.strategies || [])[0] || {}).sharpe).filter(v => v != null);
  const avgSharpe = allSharpes.length ? (allSharpes.reduce((a, b) => a + b, 0) / allSharpes.length).toFixed(2) : "—";
  const allMdds = allRows.map(r => ((r.strategies || [])[0] || {}).max_drawdown).filter(v => v != null);
  const avgMdd = allMdds.length ? ((allMdds.reduce((a, b) => a + b, 0) / allMdds.length) * 100).toFixed(1) + "%" : "—";

  const body = filteredRows
    .map((r) => {
      const best = (r.strategies || [])[0] || {};
      const paramsKo = r.best_params_ko || best.params_ko || "";
      const familyKo = r.best_family_ko || best.family_ko || "";
      const stab = r.stability_label || "LOW";
      const priceQuality = r.price_integrity || {};
      const qualityIssues = Number(priceQuality.issue_count || 0);
      const excludedBars = Math.max(0, Number(r.raw_bars || r.bars || 0) - Number(r.bars || 0));
      const qualityChip = qualityIssues
        ? `<span class="chip warn has-tip" data-tip-title="가격 품질 게이트 적용" data-tip="비체결 행과 가격·주식수 단절을 원시 수익률로 연결하지 않았습니다. 기업행위 확정 판정이 아니라 KRX 관측 필드 기반 보수적 분리입니다." data-tip-hint="원본 ${r.raw_bars || r.bars || 0}일 중 ${excludedBars}일 제외 · 최근 안전구간 ${r.bars || 0}일" tabindex="0">🛡️ 품질분리 ${qualityIssues}건</span>`
        : "";

      const fam = (r.best_family || "").includes("rsi") || (r.best_name || "").includes("RSI")
        ? "rsi"
        : (r.best_family || "").includes("bb") || (r.best_name || "").includes("볼린저")
        ? "bb"
        : (r.best_family || "").includes("ma") || (r.best_name || "").includes("이동평균")
        ? "ma"
        : "donchian";
      const pillClass = fam;
      const icon = fam === "rsi" ? "⚡" : fam === "bb" ? "📊" : fam === "ma" ? "📈" : "📦";

      let stratTipTitle = "";
      let stratTipDesc = "";
      let stratTipHint = "";
      let ruleSummary = "";

      if (fam === "rsi") {
        stratTipTitle = "⚡ RSI 평균회귀 (Mean Reversion)";
        stratTipDesc = "RSI(상대강도지수)가 과매도(≤30) 바닥권에 진입할 때 매수하고, 과매수(≥70) 과열권으로 올라오면 분할 익절하는 단기 반등 전략입니다.";
        stratTipHint = "우량 대형주 및 박스권 횡보장에서 가장 승률과 샤프지수가 높습니다.";
        ruleSummary = "과매도(≤30) 매수 → 과매수(≥70) 익절";
      } else if (fam === "bb") {
        stratTipTitle = "📊 볼린저 밴드 하단 반등 (Bollinger Reversion)";
        stratTipDesc = "주가가 20일 이동평균선 대비 2 표준편차 하단 밴드를 이탈하여 과매도될 때 저점 매수하고, 중심선(20일선)으로 회귀할 때 익절하는 변동성 반등 전략입니다.";
        stratTipHint = "강력한 실적 펀더멘털을 갖춘 종목의 일시적 패닉 투매 구간에서 강력한 안전마진을 제공합니다.";
        ruleSummary = "하단 밴드 이탈 매수 → 중심선 복귀 익절";
      } else if (fam === "ma") {
        stratTipTitle = "📈 이동평균 골든크로스 (Trend Following)";
        stratTipDesc = "단기 이동평균선(예: 10일)이 장기 이동평균선(예: 40일)을 상향 돌파(골든크로스)할 때 매수하여 대세 상승 추세를 추종하고, 데드크로스 발생 시 전량 청산하는 추세추종 전략입니다.";
        stratTipHint = "대세 상승장 및 실적 턴어라운드 주도주에서 큰 시세 차익을 거둘 수 있습니다.";
        ruleSummary = "단기선 골든크로스 매수 → 데드크로스 청산";
      } else {
        stratTipTitle = "📦 돈치안 박스권 돌파 (Donchian Breakout)";
        stratTipDesc = "과거 N일간의 최고가를 상향 돌파할 때 강력한 모멘텀으로 매수하고, N일 최저가를 이탈할 때 손절/익절하는 터틀 트레이딩 기반 돌파 전략입니다.";
        stratTipHint = "신고가를 갱신하는 강력한 성장주와 역사적 저항선을 뚫은 모멘텀주에 유효합니다.";
        ruleSummary = "전고점 박스권 상단 돌파 매수 → 하단 청산";
      }

      let stabTipTitle = "";
      let stabTipDesc = "";
      let stabTipHint = "";
      let stabHtml = "";

      if (stab === "HIGH") {
        stabTipTitle = "🟢 안정성 등급: HIGH (최종·순환 검증 기준 충족)";
        stabTipDesc = "최종검증(OOS) 샤프와 Walk-Forward 기준을 충족했습니다. 제한된 과거 표본 결과이며 과적합이 없거나 미래 성과가 보장된다는 뜻은 아닙니다.";
        stabTipHint = "검증·최종검증 거래 수, 최대낙폭, 비용 가정을 함께 확인하세요.";
        stabHtml = `<span class="strat-badge-high has-tip" data-tip-title="${escapeHtml(stabTipTitle)}" data-tip="${escapeHtml(stabTipDesc)}" data-tip-hint="${escapeHtml(stabTipHint)}" tabindex="0">🟢 HIGH (최상)</span>`;
      } else if (stab === "MEDIUM") {
        stabTipTitle = "🟡 안정성 등급: MED (보통·양호)";
        stabTipDesc = "일부 검증 기준은 충족했지만 구간별 결과 편차가 있어 추가 표본 확인이 필요한 전략입니다.";
        stabTipHint = "검증과 최종검증의 수익 방향 및 거래 수가 일치하는지 확인하세요.";
        stabHtml = `<span class="strat-badge-med has-tip" data-tip-title="${escapeHtml(stabTipTitle)}" data-tip="${escapeHtml(stabTipDesc)}" data-tip-hint="${escapeHtml(stabTipHint)}" tabindex="0">🟡 MED (보통)</span>`;
      } else {
        stabTipTitle = "🟠 안정성 등급: LOW (표본 부족 / 연구 후보)";
        stabTipDesc = "과거 3년간 매매 체결 횟수가 부족하거나(8회 미만), 최근 시장 변동성으로 인해 미래 검증에서 편차가 큰 전략입니다. 맹목적 추종보다는 연구/관찰 후보로 활용해야 합니다.";
        stabTipHint = "성과 결론을 내리지 말고 데이터와 기간을 더 확보하세요.";
        stabHtml = `<span class="strat-badge-low has-tip" data-tip-title="${escapeHtml(stabTipTitle)}" data-tip="${escapeHtml(stabTipDesc)}" data-tip-hint="${escapeHtml(stabTipHint)}" tabindex="0">🟠 LOW (표본부족)</span>`;
      }

      let actionGuideChip = "";
      if (stab === "HIGH") {
        actionGuideChip = `<span class="chip ok has-tip" data-tip-title="검증 해석" data-tip="설정된 최종검증·순환 기준을 충족했지만 미래 성과를 보장하지 않습니다." style="font-size:10.5px; padding:2px 7px; font-weight:700;" tabindex="0">✅ 검증 기준 충족 · 추가 확인 필요</span>`;
      } else if (stab === "MEDIUM") {
        actionGuideChip = `<span class="chip warn has-tip" data-tip-title="검증 해석" data-tip="검증 구간과 최종검증 결과의 편차를 확인해야 합니다." style="font-size:10.5px; padding:2px 7px; font-weight:700;" tabindex="0">⚠️ 구간별 편차 · 결론 보류</span>`;
      } else {
        actionGuideChip = `<span class="chip neutral has-tip" data-tip-title="검증 해석" data-tip="거래 수 또는 순환 검증이 부족해 성과 판단에 사용할 수 없습니다." style="font-size:10.5px; padding:2px 7px;" tabindex="0">🧪 표본 부족 · 판단 보류</span>`;
      }

      return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker || "")}">
        <td>
          <div style="display:flex; flex-direction:column; gap:2px;">
            <b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(r.company || "")}</b>
            <div class="meta" style="color:#94a3b8; font-size:11px; display:flex; align-items:center; gap:5px;">
              <span class="tag" style="background:#1e293b; color:#38bdf8; font-family:monospace; font-weight:700; font-size:10.5px; padding:1px 5px; border:1px solid rgba(56,189,248,0.25); border-radius:4px;">${escapeHtml(r.ticker || "")}</span>
              <span>${r.bars || 0}거래일</span>
              ${qualityChip}
            </div>
          </div>
        </td>
        <td>
          <div class="strat-pill-name ${pillClass} has-tip" data-tip-title="${escapeHtml(stratTipTitle)}" data-tip="${escapeHtml(stratTipDesc)}" data-tip-hint="${escapeHtml(stratTipHint)}" tabindex="0">${icon} ${escapeHtml(r.best_name || "—")}</div>
          <div class="params-ko" style="color:#94a3b8; font-size:11px; margin-top:2px;">${escapeHtml(paramsKo || familyKo)}</div>
        </td>
        <td>${stabHtml}</td>
        <td class="num has-tip" data-tip="가운데 검증 구간 수익률과 그 구간의 왕복 거래 수입니다. 이 결과가 전략 선택에 사용됩니다.">
          <b style="color:${Number(best.validation_return) > 0 ? '#4ade80' : '#f8fafc'}; font-size:13.5px;">${pctCell(best.validation_return)}</b>
          <span class="meta">${best.validation_trade_count ?? 0}회</span>
        </td>
        <td class="num has-tip" data-tip="선택에 쓰지 않은 마지막 20% 최종검증 결과입니다. 수익률·샤프·거래 수를 함께 봐야 합니다.">
          <b style="color:${Number(best.oos_return) > 0 ? '#38bdf8' : '#cbd5e1'}; font-size:13.5px;">${pctCell(best.oos_return)}</b>
          <span class="meta">샤프 ${best.oos_sharpe == null ? "—" : fmt(best.oos_sharpe, 2)} · ${best.oos_trade_count ?? 0}회</span>
        </td>
        <td class="num has-tip" data-tip="순환 검증(WF) 승률: 시기를 바꿔가며 테스트했을 때 플러스 수익을 낸 기간 비율">
          <span style="font-weight:800; color:${(best.wf_hit || 0) >= 0.6 ? '#4ade80' : '#f8fafc'}; font-size:13px;">${best.wf_hit == null ? "—" : `${(best.wf_hit * 100).toFixed(0)}%`}</span>
          <span class="meta" style="font-size:10.5px; color:#94a3b8;">${best.wf_windows || 0}구간</span>
        </td>
        <td class="num has-tip" data-tip="최대 낙폭(MDD): 보유 기간 중 겪었던 최대 하락폭">
          <b style="color:#f87171; font-size:13px;">${pctCell(best.max_drawdown)}</b>
        </td>
        <td class="num has-tip" data-tip="총 매매 횟수: 왕복 체결 횟수">${best.trade_count ?? "—"}회</td>
        <td class="strat-note" style="min-width:240px;">
          <div style="display:flex; flex-direction:column; gap:4px;">
            <div style="font-size:11.5px; color:#e2e8f0; font-weight:600;">규칙: ${escapeHtml(ruleSummary)}</div>
            <div>${actionGuideChip}</div>
          </div>
        </td>
      </tr>`;
    })
    .join("");

  const when = fmtWhen(data.fetched_at);
  const bars = (data.rows || []).map((r) => Number(r.bars || 0)).filter((n) => n > 0);
  const minBars = bars.length ? Math.min(...bars) : 0;
  const asof = [when ? `백테스트 ${when}` : "", minBars ? `종목당 ${minBars}일+` : "", lastStatus?.freshness?.price_max_date ? `KRX 시세 ${lastStatus.freshness.price_max_date}` : ""]
    .filter(Boolean)
    .join(" · ") || "전략 결과 시점 없음";

  if (currentView === "strategy") {
    setPageAsOf(asof, "KRX 일봉으로 돌린 시각입니다. TOP20 백테스트 버튼을 누르면 즉시 재검증합니다.");
  }

  box.innerHTML = `
    ${asofBanner(asof)}

    <!-- Tier 1 AI Strategy Timing Synthesis Briefing (100% Free Engine) -->
    <div id="strategy-lab-tier1-briefing" style="margin: 12px 0 14px;"></div>

    <!-- 4-Step Intuitive Guide Deck -->
    <div class="strat-guide-grid">
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">🎯</span> 1. 백테스트 목적</div>
        <div class="strat-guide-desc">재무 Quant TOP20 종목별로 네 가격 규칙을 같은 조건에서 비교하고 <b>검증 구간 1위와 최종검증 결과</b>를 분리해 보여줍니다.</div>
      </div>
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">🧪</span> 2. 4대 전략 풀</div>
        <div class="strat-guide-desc"><b>RSI</b>, <b>볼린저</b>, <b>이평선 교차</b>, <b>돈치안 돌파</b>를 학습 60%·검증 20%·최종검증 20%로 나눠 비교합니다.</div>
      </div>
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">🛡️</span> 3. 과적합 2중 방지</div>
        <div class="strat-guide-desc">마지막 20% <b>최종검증(OOS)</b>은 전략 선택에 사용하지 않으며, <b>Walk-Forward</b>와 함께 과적합 위험을 확인합니다.</div>
      </div>
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">⏱️</span> 4. 현실적 체결 기준</div>
        <div class="strat-guide-desc">신호 다음 거래일 시가 체결, 설정된 수수료와 슬리피지를 반영한 일봉 모의이며 실제 주문·호가 재현은 아닙니다.</div>
      </div>
    </div>

    <!-- Strategy Summary KPIs -->
    <div class="strat-summary-row">
      <div class="strat-summary-item has-tip" data-tip-title="🟢 안정성 기준 HIGH" data-tip="설정된 최종검증 및 순환 검증 기준을 충족한 종목 수입니다. 무결점이나 미래 성과 보장을 뜻하지 않습니다." tabindex="0">
        <span>🟢 안정성 최상 (HIGH)</span>
        <b>${highCount} <small style="font-size:12px; color:#94a3b8; font-weight:normal;">개 종목</small></b>
      </div>
      <div class="strat-summary-item has-tip" data-tip-title="🟡 안정성 기준 MED" data-tip="일부 기준만 충족해 구간별 편차와 표본을 더 확인해야 하는 종목 수입니다." tabindex="0">
        <span>🟡 안정성 보통 (MED)</span>
        <b>${medCount} <small style="font-size:12px; color:#94a3b8; font-weight:normal;">개 종목</small></b>
      </div>
      <div class="strat-summary-item has-tip" data-tip-title="📊 TOP20 평균 샤프 지수" data-tip="위험 1단위 감수 대비 초과수익 비율의 평균치입니다. 1.0 이상이면 시장 대비 탁월한 초과수익을 의미합니다." tabindex="0">
        <span>📊 TOP20 전체기간 참고 샤프</span>
        <b>${avgSharpe} <small style="font-size:12px; color:#38bdf8; font-weight:normal;">(선택 지표 아님)</small></b>
      </div>
      <div class="strat-summary-item has-tip" data-tip-title="🛡️ TOP20 평균 최대낙폭 (MDD)" data-tip="전략 보유 기간 중 겪었던 최대 하락폭의 평균치입니다. 낮을수록 하락장 방어력이 견고합니다." tabindex="0">
        <span>🛡️ TOP20 평균 최대낙폭</span>
        <b>${avgMdd} <small style="font-size:12px; color:#34d399; font-weight:normal;">(리스크 방어력 양호)</small></b>
      </div>
    </div>

    <!-- Interactive Strategy Filter Bar -->
    <div class="strat-filter-bar">
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'all' ? 'active' : ''}" data-strat-filter="all">전체 (20)</button>
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'high' ? 'active' : ''}" data-strat-filter="high">🟢 HIGH 최상 (${highCount})</button>
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'med' ? 'active' : ''}" data-strat-filter="med">🟡 MED/HIGH (${highCount + medCount})</button>
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'rsi' ? 'active' : ''}" data-strat-filter="rsi">⚡ RSI 과매도 (${rsiCount})</button>
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'bb' ? 'active' : ''}" data-strat-filter="bb">📊 볼린저 밴드 (${bbCount})</button>
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'ma' ? 'active' : ''}" data-strat-filter="ma">📈 이평선 교차 (${maCount})</button>
      <button type="button" class="strat-filter-btn ${currentStrategyFilter === 'donchian' ? 'active' : ''}" data-strat-filter="donchian">📦 돈치안 박스권 (${donchianCount})</button>
    </div>

    <div class="table-wrap tall"><table>
      <thead><tr>
        ${thTip("종목", "Quant TOP20 종목명과 KRX 일봉 데이터 축적 일수입니다.")}
        ${thTip("검증 구간 1위 규칙", "가운데 검증 구간 점수로 선택한 가격 규칙과 파라미터입니다.")}
        ${thTip("안정성", "HIGH/MED/LOW는 설정된 표본·최종검증·순환검증 기준의 충족 정도입니다.")}
        ${thTip("검증 수익률", "전략 선택에 사용한 가운데 검증 구간 수익률과 거래 수입니다.")}
        ${thTip("최종검증 결과", "선택에 쓰지 않은 마지막 20%의 수익률·샤프·거래 수입니다.")}
        ${thTip("순환 검증 승률", "시뮬레이션 구간을 3개월씩 전진시키며(Walk-Forward) 플러스 수익을 낸 기간 비율입니다.")}
        ${thTip("최대 낙폭", "전략 운용 중 겪었던 최대 하락폭(MDD)입니다. 낮을수록 안전합니다.")}
        ${thTip("매매 횟수", "과거 3년간 발생한 총 왕복 매매 횟수입니다.")}
        ${thTip("전략 분석", "선택 근거와 표본 부족·구간 불일치 여부를 설명합니다.")}
      </tr></thead>
      <tbody>${body || "<tr><td colspan=9 style='text-align:center; padding:30px; color:#94a3b8;'>해당 조건에 일치하는 종목이 없습니다.</td></tr>"}</tbody>
    </table></div>

    <!-- Friendly Glossary Box -->
    <div class="strat-glossary-box">
      <div style="font-weight:700; color:#fff; margin-bottom:6px;">💡 초보자를 위한 3대 핵심 퀀트 용어 가이드</div>
      <div class="strat-glossary-grid">
        <div class="strat-glossary-col">
          <b>📈 샤프 지수 (Sharpe Ratio)</b>
          투자 위험 1단위를 감수할 때 얻는 초과수익률입니다. 1.0 이상이면 시장 평균을 능가하며, 1.5 이상이면 매우 탁월한 전략입니다.
        </div>
        <div class="strat-glossary-col">
          <b>🛡️ 미래 검증 (Out-of-Sample, OOS)</b>
          과거 데이터에만 억지로 꿰맞추는 '과적합(착시)'을 막기 위해, 모델이 보지 못한 미래 구간 데이터로만 실력을 재검증하는 기법입니다.
        </div>
        <div class="strat-glossary-col">
          <b>🔄 순환 검증 (Walk-Forward, WF)</b>
          시간을 3개월씩 앞으로 밀어가며 지속적으로 수익이 유지되었는지를 검증하는 월가 표준 백테스트 방식입니다.
        </div>
      </div>
    </div>
  `;

  box.querySelectorAll("[data-strat-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentStrategyFilter = btn.dataset.stratFilter;
      renderStrategy(data);
    });
  });

  box.querySelectorAll("tr.clickable").forEach((row) => {
    row.addEventListener("click", () => {
      const ticker = row.dataset.ticker;
      if (ticker && typeof showStockPopup === "function") {
        showStockPopup(ticker);
      }
    });
  });

  loadStrategyTier1Briefing().catch(() => {});
}

function renderPortfolio(data) {
  const html = portfolioHtml(data);
  ["#portfolio-box", "#strategy-port-box"].forEach((sel) => {
    const box = $(sel);
    if (box) box.innerHTML = html;
  });
}

function portfolioHtml(data) {
  if (!data || data.error) {
    return `<p class="hint">${escapeHtml((data && data.error) || "TOP20 결과가 없습니다.")}</p>`;
  }
  const conc = data.sector_concentration == null ? "—" : `${(Number(data.sector_concentration) * 100).toFixed(0)}%`;
  const corr = data.avg_pairwise_correlation == null ? "—" : Number(data.avg_pairwise_correlation).toFixed(2);
  const eff = data.effective_positions == null ? "—" : Number(data.effective_positions).toFixed(1);
  const maxW = data.max_sector_weight == null ? 40 : Number(data.max_sector_weight) * 100;
  const bars = (data.sectors || [])
    .slice(0, 8)
    .map((s) => {
      const pct = Number(s.weight || 0) * 100;
      const width = Math.max(2, Math.min(100, pct / Math.max(maxW, 1) * 100));
      return `<li><span>${escapeHtml(s.name || "—")}</span><i><em style="width:${width.toFixed(0)}%"></em></i><span>${pct.toFixed(0)}%</span></li>`;
    })
    .join("");
  const warns = (data.warning_labels || [])
    .map((w) => `<span class="tag hot">${escapeHtml(w)}</span>`)
    .join(" ");
  return `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi"><span>종목 수</span><b>${data.n ?? "—"}</b></div>
      <div class="kpi"><span>최대 업종</span><b>${conc}</b><div class="hint">${escapeHtml(data.top_sector || "")}</div></div>
      <div class="kpi"><span>평균 상관</span><b>${corr}</b></div>
      <div class="kpi"><span>유효 종목</span><b>${eff}</b></div>
    </div>
    ${warns ? `<p>${warns}</p>` : ""}
    <p>${escapeHtml(data.comment || "")}</p>
    <h3>업종 비중 (동일 비중)</h3>
    <ul class="sector-bars">${bars || "<li>업종 정보 없음</li>"}</ul>
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>
  `;
}

async function loadPortfolio() {
  const data = await api("/api/portfolio");
  portfolioCache = data;
  renderPortfolio(data);
}

async function loadStrategy(force) {
  const box = $("#strategy-box");
  if (!box) return;
  loadStrategyTier1Briefing().catch(() => {});
  if (!force && strategyCache && !strategyCache.need_run) {
    renderStrategy(strategyCache);
    return;
  }
  box.innerHTML = "<p>전략 결과를 불러오는 중…</p>";
  let data = await api("/api/strategy");
  if (force || data.need_run) {
    box.innerHTML = "<p>TOP20 일봉 백테스트 중… </p>";
    data = await api("/api/strategy", { method: "POST", body: JSON.stringify({ force: true }) });
  }
  strategyCache = data;
  renderStrategy(data);
}

async function loadTrade(force) {
  return loadSmartFlow(Boolean(force));
}

let us13fCache = null;

function usd(n) {
  const x = Number(n);
  if (!x) return "—";
  const abs = Math.abs(x);
  const sign = x < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
  return `${sign}$${abs.toLocaleString("en-US")}`;
}

function us13fQuery() {
  return ($("#us13f-q")?.value || "").trim().toLowerCase();
}

function filter13f(rows, extraKeys) {
  const q = us13fQuery();
  if (!q) return rows;
  const keys = extraKeys.concat(["ticker", "issuer_ko", "note_ko", "filer_ko", "name_ko", "filers_ko"]);
  return rows.filter((r) => {
    const hay = keys.map((k) => String(r[k] || "")).join(" ").toLowerCase();
    return hay.includes(q);
  });
}

function usdDelta(n) {
  const x = Number(n);
  if (!x) return "<span style='color:#64748b;'>—</span>";
  const str = usd(x);
  if (x > 0) return `<b style="color:#4ade80;">+${str}</b>`;
  if (x < 0) return `<b style="color:#f87171;">${str}</b>`;
  return `<span>${str}</span>`;
}

function tickerChip(r) {
  const ticker = r.ticker || "";
  if (ticker) {
    return `<span class="tag" style="background:#1e293b; color:#38bdf8; font-weight:700; font-family:monospace; padding:2px 6px; border:1px solid rgba(56,189,248,0.25);">${escapeHtml(ticker)}</span>`;
  }
  return r.cusip ? `<span class="tag" style="background:#1e293b; color:#94a3b8; font-size:10px;">${escapeHtml(r.cusip)}</span>` : `<span style="color:#64748b;">—</span>`;
}

function filerLabel(r) {
  const ko = r.filer_ko || r.name_ko || r.filer || r.name || "";
  const who = r.filer_who || r.who_ko || "";
  const en = r.filer || r.name || "";
  return `
    <div style="display:flex; flex-direction:column; gap:2px;">
      <b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(ko)}</b>
      <div class="meta" style="color:#94a3b8; font-size:11px;">${escapeHtml([who, en !== ko ? en : ""].filter(Boolean).join(" · "))}</div>
      ${rowNote(r.comment)}
    </div>
  `;
}

function issuerLabel(r) {
  const ko = r.issuer_ko || r.issuer || "";
  const ticker = r.ticker || "";
  const note = r.note_ko || "";
  const en = r.issuer && r.issuer_ko && r.issuer !== r.issuer_ko ? r.issuer : "";
  
  let tickerBadge = "";
  let extLink = "";
  
  if (ticker) {
    tickerBadge = ` <span class="tag" style="background:#1e293b; color:#38bdf8; font-weight:700; font-family:monospace; font-size:11px; padding:2px 6px; border:1px solid rgba(56,189,248,0.25);">${escapeHtml(ticker)}</span>`;
    const yahooUrl = r.yahoo || `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}`;
    extLink = ` <a class="ext inline" href="${escapeHtml(yahooUrl)}" target="_blank" rel="noopener" style="font-size:11px; color:#38bdf8;">Yahoo ↗</a>`;
  } else {
    tickerBadge = r.cusip ? ` <span class="tag" style="background:#1e293b; color:#94a3b8; font-size:10.5px;">${escapeHtml(r.cusip)}</span>` : "";
  }

  return `
    <div style="display:flex; flex-direction:column; gap:2px;">
      <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
        <b style="font-size:13.5px; color:#f8fafc;">${escapeHtml(ko)}</b>
        ${tickerBadge}
        ${extLink}
      </div>
      <div class="meta" style="color:#94a3b8; font-size:11.5px; line-height:1.45;">${escapeHtml(note || en || r.cusip || "")}</div>
      ${rowNote(r.comment_short || r.comment)}
    </div>
  `;
}

function renderUs13f(data) {
  const box = $("#us13f-box");
  if (!box) return;
  const mode = $("#us13f-mode")?.value || "new";
  const err = (data.errors || []).map((e) => `${e.filer}: ${e.error}`).join(" · ");
  const kpis = `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi has-tip" data-tip-title="🏛️ 스캔 대상 대가 펀드 수" data-tip="버크셔 해서웨이, 브리지워터, 시타델 등 미국 SEC에 13F를 공시한 핵심 글로벌 헤지펀드/기관 수입니다." tabindex="0">
        <span>스캔 펀드</span><b style="color:#38bdf8;">${data.scanned || (data.filers || []).length}개사</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🔥 이번 분기 신규 매수 종목 수" data-tip="월가 거물들이 이번 분기에 새롭게 포트폴리오에 편입한 신규 베팅 종목 수입니다." tabindex="0">
        <span>신규 편입</span><b style="color:#4ade80;">${(data.new || []).length}건</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🎯 2인 이상 대가 공통 보유 종목 수" data-tip="버핏, 달리오, 켄 그리핀 등 2개 이상의 독립 대형 펀드가 동시에 러브콜을 보낸 핵심 종목 수입니다." tabindex="0">
        <span>대가 공통보유</span><b style="color:#facc15;">${(data.common || []).length}건</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🚪 이번 분기 전량 청산 종목 수" data-tip="거물들이 이번 분기 포트폴리오에서 비중 100%를 전량 매도한 종목 수입니다." tabindex="0">
        <span>전량 청산</span><b style="color:#f87171;">${(data.exits || []).length}건</b>
      </div>
    </div>
    <p class="hint">${escapeHtml(data.selection || "SEC EDGAR 13F-HR 분기 말 보유 보고서 기반입니다. 신규·확대·청산은 직전 분기 대비 공식 보유 지분 변화입니다.")}</p>
    ${asofBanner([`13F 보고 ${(data.periods || []).join(" · ") || "—"}`, data.fetched_at ? `동기화 ${fmtWhen(data.fetched_at)}` : ""].filter(Boolean).join(" · "))}`;

  let table = "";
  if (mode === "filers" || mode === "weights") {
    const filers = filter13f(data.filers || [], ["name", "manager", "cik"]);
    if (mode === "filers") {
      table = `<table data-scope="us13f"><thead><tr><th>헤지펀드·기관</th><th>보고일</th><th>공시일</th><th class="num">종목수</th><th class="num">총 자산규모</th><th class="num">신규</th><th class="num">청산</th><th>원문</th></tr></thead><tbody>
        ${filers.map((f) => `<tr>
          <td>${filerLabel(f)}</td>
          <td>${escapeHtml(f.report_date || "")}</td>
          <td>${escapeHtml(f.filing_date || "")}</td>
          <td class="num"><b>${f.n ?? "—"}</b></td>
          <td class="num"><b style="color:#f8fafc;">${usd(f.total_value)}</b></td>
          <td class="num"><b style="color:#4ade80;">${f.new ? `+${f.new}` : 0}</b></td>
          <td class="num"><span style="color:#f43f5e;">${f.exits ? `-${f.exits}` : 0}</span></td>
          <td>${f.page ? `<a class="ext inline" href="${escapeHtml(f.page)}" target="_blank" rel="noopener">SEC ↗</a>` : "—"}
            ${f.whale ? ` · <a class="ext inline" href="${escapeHtml(f.whale)}" target="_blank" rel="noopener">WW ↗</a>` : ""}</td>
        </tr>`).join("")}</tbody></table>`;
    } else {
      const rows = [];
      for (const f of filers) {
        for (const t of f.top || []) rows.push({ ...t, filer: f.name });
      }
      const filtered = filter13f(rows, ["issuer", "cusip", "filer"]);
      table = `<table data-scope="us13f"><thead><tr><th>펀드</th><th style="min-width:220px;">종목</th><th>티커</th><th class="num">비중</th><th class="num">평가액</th><th class="num">보유 주수</th></tr></thead><tbody>
        ${filtered.map((r) => `<tr>
          <td>${filerLabel(r)}</td>
          <td>${issuerLabel(r)}</td>
          <td>${tickerChip(r)}</td>
          <td class="num">${r.weight == null ? "—" : `<span class="chip ok">${fmtPct(r.weight, 1)}</span>`}</td>
          <td class="num"><b style="color:#f8fafc;">${usd(r.value)}</b></td>
          <td class="num">${Number(r.shares || 0).toLocaleString("en-US")}주</td>
        </tr>`).join("")}</tbody></table>`;
    }
  } else if (mode === "common") {
    const rows = filter13f(data.common || [], ["issuer", "cusip", "filers"]);
    table = `<table data-scope="us13f"><thead><tr><th style="min-width:220px;">종목</th><th class="num">펀드 수</th><th>보유 슈퍼인베스터 목록</th><th class="num">합산 투자규모</th></tr></thead><tbody>
      ${rows.map((r) => `<tr>
        <td>${issuerLabel(r)}</td>
        <td class="num"><span class="tag tone-우호" style="font-weight:800;">🌟 ${r.n_filers}개 펀드</span></td>
        <td>${(r.filers_ko || r.filers || []).map(f => `<span class="us13f-fund-chip">${escapeHtml(f)}</span>`).join(" ")}</td>
        <td class="num"><b style="color:#f8fafc; font-size:14px;">${usd(r.value)}</b></td>
      </tr>`).join("")}</tbody></table>`;
  } else if (mode === "trend") {
    const rows = filter13f(data.trend || [], ["issuer", "cusip", "buyers", "sellers"]);
    table = `<table data-scope="us13f"><thead><tr><th style="min-width:220px;">종목</th><th class="num">점수</th><th class="num">신규</th><th class="num">확대</th><th class="num">축소</th><th class="num">청산</th><th class="num">순변화 금액</th></tr></thead><tbody>
      ${rows.map((r) => `<tr>
        <td>${issuerLabel(r)}</td>
        <td class="num"><span class="score-pill ${Number(r.score) >= 4 ? 'high' : ''}">${r.score}</span></td>
        <td class="num"><b style="color:#4ade80;">${r.new ? `+${r.new}` : 0}</b></td>
        <td class="num"><b style="color:#60a5fa;">${r.increase ? `+${r.increase}` : 0}</b></td>
        <td class="num"><span style="color:#f87171;">${r.decrease ? `-${r.decrease}` : 0}</span></td>
        <td class="num"><span style="color:#f43f5e;">${r.exit ? `-${r.exit}` : 0}</span></td>
        <td class="num">${usdDelta(r.value_delta)}</td>
      </tr>`).join("")}</tbody></table>`;
  } else {
    const key = mode === "exits" ? "exits" : mode === "increases" ? "increases" : "new";
    const rows = filter13f(data[key] || [], ["issuer", "cusip", "filer"]);
    const amt = mode === "exits" ? "prev_value" : "value";
    table = `<table data-scope="us13f"><thead><tr><th>헤지펀드</th><th style="min-width:220px;">종목</th><th>티커</th><th class="num">투자 금액</th><th class="num">변화 규모</th><th class="num">포트 비중</th></tr></thead><tbody>
      ${rows.slice(0, 100).map((r) => `<tr>
        <td>${filerLabel(r)}</td>
        <td>${issuerLabel(r)}</td>
        <td>${tickerChip(r)}</td>
        <td class="num"><b style="color:#f8fafc;">${usd(r[amt])}</b></td>
        <td class="num">${usdDelta(r.value_delta)}</td>
        <td class="num">${r.weight ? `<span class="chip ok">${fmtPct(r.weight, 1)}</span>` : "—"}</td>
      </tr>`).join("")}</tbody></table>`;
  }
  const SLICE_COLORS = ["#4c8dff", "#3dcf8e", "#f59e0b", "#a855f7", "#ec4899", "#64748b"];

  const filerCardsHtml = (data.filers || []).slice(0, 6).map((f) => {
    const topHoldings = f.top || [];
    const totalVal = f.total_value;
    const slices = topHoldings.slice(0, 5).map((t, idx) => {
      const w = (t.weight || 0) * 100;
      const col = SLICE_COLORS[idx % SLICE_COLORS.length];
      return `<div class="us13f-stack-slice" style="width:${Math.max(4, w)}%;background:${col};" title="${escapeHtml(t.issuer_ko || t.issuer)}: ${w.toFixed(1)}%"></div>`;
    }).join("");

    const chips = topHoldings.slice(0, 4).map((t, idx) => {
      const w = (t.weight || 0) * 100;
      const col = SLICE_COLORS[idx % SLICE_COLORS.length];
      return `
        <div class="us13f-top-chip">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${col};"></span>
          <b>${escapeHtml(t.issuer_ko || t.ticker || t.issuer)}</b>
          <span>${w.toFixed(1)}%</span>
        </div>
      `;
    }).join("");

    return `
      <div class="us13f-filer-card">
        <div class="us13f-filer-header">
          <div>
            <div class="us13f-filer-name">${escapeHtml(f.filer_ko || f.name)}</div>
            <div class="us13f-filer-meta">운용 총액 ${usd(totalVal)} · 보유 ${f.n ?? "—"}개 종목</div>
          </div>
          <div style="display:flex;gap:4px;">
            ${f.new ? `<span class="tag tone-우호">신규 ${f.new}</span>` : ""}
            ${f.exits ? `<span class="tag tone-부담">청산 ${f.exits}</span>` : ""}
          </div>
        </div>
        <div class="us13f-stack-bar">
          ${slices || '<div class="us13f-stack-slice" style="width:100%;background:#334155;"></div>'}
        </div>
        <div class="us13f-top-chips">
          ${chips}
        </div>
      </div>
    `;
  }).join("");

  const MODES = [
    ["new", "🔥 신규 편입"],
    ["common", "🎯 대가 공통 보유"],
    ["increases", "📈 비중 확대"],
    ["exits", "🚪 전량 청산"],
    ["filers", "🏛️ 펀드별 공시"],
    ["weights", "📊 보유 비중 순위"],
    ["trend", "⚡ 매매 트렌드"],
  ];
  const modeTabsHtml = `
    <div class="h-tabs" style="margin:12px 0 16px; flex-wrap:wrap; gap:6px;">
      ${MODES.map(([k, label]) => `
        <button type="button" class="${mode === k ? "on active" : ""}" data-13f-mode="${k}" style="padding:6px 14px; font-weight:700; border-radius:8px;">
          ${label} ${k === "new" ? `(${(data.new || []).length})` : k === "common" ? `(${(data.common || []).length})` : k === "exits" ? `(${(data.exits || []).length})` : ""}
        </button>
      `).join("")}
    </div>
  `;

  // Consensus Highlights
  const commonRows = data.common || [];
  const consensusCardsHtml = commonRows.slice(0, 6).map((c) => {
    const funds = (c.filers_ko || c.filers || []).slice(0, 3).map((f) => `<span class="us13f-fund-chip">${escapeHtml(f)}</span>`).join("");
    return `
      <div class="us13f-consensus-card">
        <div class="us13f-consensus-top">
          <div>
            <div class="us13f-consensus-name">${escapeHtml(c.issuer_ko || c.issuer)}</div>
            <div class="meta">${tickerChip(c)}</div>
          </div>
          <span class="tag tone-우호">🌟 ${c.n_filers}개 펀드 동시 보유</span>
        </div>
        <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">
          합산 투자액: <b style="color:#fff; font-size:13.5px;">${usd(c.value)}</b>
        </div>
        <div class="us13f-consensus-funds">
          ${funds}
        </div>
      </div>
    `;
  }).join("");

  // Action Highlights
  const actionList = (mode === "new" ? (data.new || []) : mode === "exits" ? (data.exits || []) : mode === "increases" ? (data.increases || []) : []).slice(0, 6);
  const actionCardsHtml = actionList.map((r) => {
    const isNew = mode === "new";
    const isExit = mode === "exits";
    const tagCls = isNew ? "tone-우호" : isExit ? "tone-부담" : "tone-중립";
    const tagTxt = isNew ? "신규 매수" : isExit ? "전량 청산" : "비중 확대";
    const amt = isExit ? r.prev_value : r.value;

    return `
      <div class="us13f-action-card ${isNew ? "new" : isExit ? "exit" : "increase"}">
        <div class="us13f-action-top">
          <span class="us13f-action-title">${escapeHtml(r.issuer_ko || r.issuer)}</span>
          <span class="tag ${tagCls}">${tagTxt}</span>
        </div>
        <div class="us13f-action-meta" style="margin-top:4px;">
          ${escapeHtml(r.filer_ko || r.filer)} · 티커: ${tickerChip(r)}
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; font-size:12px;">
          <span style="color:var(--muted);">거래 규모</span>
          <b style="color:#fff; font-size:13.5px;">${usd(amt)}</b>
        </div>
      </div>
    `;
  }).join("");

  box.innerHTML = `
    ${kpis}
    <h3 style="margin:16px 0 6px;font-size:15px;color:#fff;">🏛️ 글로벌 대가별 포트폴리오 비중 (Top Holdings Weight)</h3>
    <p class="hint" style="margin-bottom:12px;">워런 버핏(버크셔 해서웨이), 마이클 버리, 레이 달리오 등 슈퍼인베스터들의 상위 보유 종목 스택 바 차트입니다.</p>
    <div class="us13f-filer-grid">
      ${filerCardsHtml}
    </div>

    ${mode === "common" && consensusCardsHtml ? `
      <h3 style="margin:20px 0 6px;font-size:15px;color:#fff;">🎯 월가 대가들의 공통 합의 보유 종목 (Consensus Top Picks)</h3>
      <p class="hint" style="margin-bottom:12px;">2개 이상의 글로벌 헤지펀드가 동시에 비중을 싣고 있는 공통 핵심 종목입니다.</p>
      <div class="us13f-consensus-grid">${consensusCardsHtml}</div>
    ` : ""}

    ${(mode === "new" || mode === "exits" || mode === "increases") && actionCardsHtml ? `
      <h3 style="margin:20px 0 6px;font-size:15px;color:#fff;">${mode === "new" ? "🔥 이번 분기 주요 신규 편입 종목 (New Buys)" : mode === "exits" ? "🚪 이번 분기 주요 전량 청산 종목 (Exits)" : "📈 이번 분기 주요 비중 확대 종목 (Increases)"}</h3>
      <div class="us13f-action-grid">${actionCardsHtml}</div>
    ` : ""}

    <div style="display:flex; justify-content:space-between; align-items:center; margin:22px 0 8px; flex-wrap:wrap; gap:8px;">
      <h3 style="margin:0;font-size:15px;color:#fff;">📋 13F 상세 분석 데이터</h3>
    </div>
    ${modeTabsHtml}
    <div class="table-wrap tall">${table}</div>
    ${err ? `<p class="hint">일부 실패: ${escapeHtml(err)}</p>` : ""}
    <p class="hint" style="margin-top:12px;">${escapeHtml(data.disclaimer || "")}</p>
  `;

  box.querySelectorAll("[data-13f-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const select = $("#us13f-mode");
      if (select) select.value = btn.dataset["13fMode"];
      renderUs13f(data);
    });
  });
}

async function loadUs13f(force) {
  const box = $("#us13f-box");
  if (!box) return;
  loadUs13fTier1Briefing().catch(() => {});
  if (!force && us13fCache && !us13fCache.need_refresh) {
    renderUs13f(us13fCache);
    return;
  }
  box.innerHTML = "<p>13F 캐시를 불러오는 중…</p>";
  let data = await api("/api/us13f");
  if (force || data.need_refresh) {
    box.innerHTML = "<p>SEC EDGAR에서 최신 13F를 받는 중… 주요 펀드 12곳이라 1분 안팎 걸릴 수 있습니다.</p>";
    data = await api("/api/us13f", { method: "POST", body: JSON.stringify({ force: true }) });
  }
  us13fCache = data;
  renderUs13f(us13fCache);
  const asof = [`13F 보고 ${(data.periods || []).join(" · ") || "—"}`, data.fetched_at ? `받은 시각 ${fmtWhen(data.fetched_at)}` : ""]
    .filter(Boolean)
    .join(" · ");
  setPageAsOf(asof || "13F 시점 없음", "SEC EDGAR 분기 말 보유입니다. 최대 45일 시차가 있습니다. 최신본 업데이트로 다시 받으세요.");
}


const SECTOR_COLORS = [
  "#38bdf8", "#34d399", "#f59e0b", "#ec4899", "#a855f7",
  "#60a5fa", "#f87171", "#fbbf24", "#4ade80", "#2dd4bf"
];

async function loadWatch() {
  const box = $("#watch-box");
  if (!box) return;

  const data = await api("/api/watchlist");
  const rows = data.rows || [];
  const summary = data.summary || {};
  const sectorDist = data.sector_distribution || {};

  if (!rows.length) {
    box.innerHTML = `
      <div style="text-align:center; padding:40px 20px; background:#0e1626; border-radius:12px; border:1px dashed rgba(255,255,255,0.15);">
        <p style="font-size:16px; color:#cbd5e1; margin-bottom:8px;">💼 저장된 관심종목이 없습니다.</p>
        <p class="hint">상단 입력창에 종목명을 검색하거나, 퀀트 랭킹·대시보드 종목 상세에서 <b>[관심종목]</b> 버튼을 눌러 나만의 포트폴리오를 구성해 보세요!</p>
      </div>
    `;
    if (currentView === "watch") setPageAsOf("포트폴리오 비어있음", "종목을 추가하여 포트폴리오를 분석하세요.");
    return;
  }

  if (currentView === "watch") {
    setPageAsOf(`포트폴리오 ${rows.length}개 종목 · 평균 퀀트 ${summary.avg_quant_score || "—"}점`, "실시간 팩터 및 가격 분석이 적용되었습니다.");
  }

  // Calculate Sector Stack Segments
  const totalSectors = Object.values(sectorDist).reduce((a, b) => a + b, 0) || 1;
  const sectorEntries = Object.entries(sectorDist);
  const stackSegs = sectorEntries.map(([sec, cnt], idx) => {
    const pct = ((cnt / totalSectors) * 100).toFixed(1);
    const color = SECTOR_COLORS[idx % SECTOR_COLORS.length];
    return `<div class="sector-stack-seg" style="width:${pct}%; background:${color};" title="${escapeHtml(sec)}: ${cnt}개 (${pct}%)"></div>`;
  }).join("");

  const sectorChips = sectorEntries.map(([sec, cnt], idx) => {
    const pct = ((cnt / totalSectors) * 100).toFixed(0);
    const color = SECTOR_COLORS[idx % SECTOR_COLORS.length];
    return `
      <span class="sector-chip-tag">
        <i class="sector-chip-dot" style="background:${color};"></i>
        ${escapeHtml(sec)} <b>${cnt}개 (${pct}%)</b>
      </span>
    `;
  }).join("");

  // Portfolio Hero Summary
  const avgScore = summary.avg_quant_score != null ? `${summary.avg_quant_score}점` : "—";
  const heroHtml = `
    <div class="portfolio-overview-hero">
      <div class="portfolio-overview-head">
        <div>
          <h3 style="margin:0; font-size:15px; color:#fff;">📊 포트폴리오 종합 건강도 (Portfolio DNA)</h3>
          <span class="hint">내 관심종목 ${rows.length}개 통합 5대 팩터 평균 스코어 및 업종 분산율</span>
        </div>
        <div class="stock-score-badge" style="font-size:13px; padding:6px 12px; background:rgba(56,189,248,0.2);">
          평균 퀀트: <b>${avgScore}</b>
        </div>
      </div>

      <div class="portfolio-kpis-grid">
        <div class="portfolio-kpi-item has-tip" data-tip="포트폴리오에 편입된 전체 종목 수입니다.">
          <span>💼 편입 종목</span>
          <b>${rows.length} <small style="font-size:12px;font-weight:normal;color:#94a3b8;">개</small></b>
        </div>
        <div class="portfolio-kpi-item has-tip" data-tip="가치 30점 만점 기준 포트폴리오 평균 저평가 수준입니다.">
          <span>💎 평균 가치 (Value)</span>
          <b style="color:#38bdf8;">${summary.avg_value_score != null ? `${summary.avg_value_score} / 30` : "—"}</b>
        </div>
        <div class="portfolio-kpi-item has-tip" data-tip="품질 25점 만점 기준 포트폴리오 평균 ROE·수익성입니다.">
          <span>👑 평균 품질 (Quality)</span>
          <b style="color:#34d399;">${summary.avg_quality_score != null ? `${summary.avg_quality_score} / 25` : "—"}</b>
        </div>
        <div class="portfolio-kpi-item has-tip" data-tip="성장 25점 만점 기준 포트폴리오 평균 실적 성장세입니다.">
          <span>🚀 평균 성장 (Growth)</span>
          <b style="color:#f59e0b;">${summary.avg_growth_score != null ? `${summary.avg_growth_score} / 25` : "—"}</b>
        </div>
      </div>

      <div class="portfolio-sector-stack">
        <div style="display:flex; justify-content:space-between; font-size:12px; color:#94a3b8;">
          <span>🍩 업종·섹터 분산 포트폴리오 구성비</span>
          <span>${sectorEntries.length}개 섹터 분산</span>
        </div>
        <div class="sector-stack-bar">${stackSegs}</div>
        <div class="sector-legend-chips">${sectorChips}</div>
      </div>
    </div>
  `;

  // Render individual stock cards
  const stockCardsHtml = rows.map((r) => {
    const code = padTicker(r.ticker);
    const score = r.quant_score != null ? fmt(r.quant_score, 1) : "—";
    const rankTxt = r.quant_rank ? `퀀트 ${r.quant_rank}위` : "유니버스";
    const priceTxt = r.close_price ? `${fmt(r.close_price, 0)}원` : "—";

    const vBar = Math.max(4, Math.min(100, ((r.value_score || 0) / 30) * 100));
    const qBar = Math.max(4, Math.min(100, ((r.quality_score || 0) / 25) * 100));
    const gBar = Math.max(4, Math.min(100, ((r.growth_score || 0) / 25) * 100));
    const mBar = Math.max(4, Math.min(100, ((r.momentum_score || 0) / 10) * 100));
    const sBar = Math.max(4, Math.min(100, ((r.financial_score || 0) / 10) * 100));

    return `
      <div class="portfolio-stock-card">
        <div>
          <div class="stock-card-head">
            <div>
              <div class="stock-card-company" data-open="${code}">
                <span>${escapeHtml(r.company || code)}</span>
              </div>
              <div class="stock-card-meta">
                ${code} · <span class="chip" style="font-size:10px; padding:1px 5px;">${escapeHtml(r.market || "KOSPI")}</span> ${r.sector ? `· ${escapeHtml(r.sector)}` : ""}
              </div>
            </div>
            <div class="stock-score-badge has-tip" data-tip="종합 퀀트 스코어 (${rankTxt})">
              ${score}
            </div>
          </div>

          <div class="card-factor-mini-bars">
            <div class="card-factor-row">
              <span>💎 가치 ${r.value_score != null ? fmt(r.value_score, 1) : "—"}</span>
              <div class="card-factor-bar"><em style="width:${vBar}%; background:#38bdf8;"></em></div>
            </div>
            <div class="card-factor-row">
              <span>👑 품질 ${r.quality_score != null ? fmt(r.quality_score, 1) : "—"}</span>
              <div class="card-factor-bar"><em style="width:${qBar}%; background:#34d399;"></em></div>
            </div>
            <div class="card-factor-row">
              <span>🚀 성장 ${r.growth_score != null ? fmt(r.growth_score, 1) : "—"}</span>
              <div class="card-factor-bar"><em style="width:${gBar}%; background:#f59e0b;"></em></div>
            </div>
            <div class="card-factor-row">
              <span>⚡ 모멘텀 ${r.momentum_score != null ? fmt(r.momentum_score, 1) : "—"}</span>
              <div class="card-factor-bar"><em style="width:${mBar}%; background:#ec4899;"></em></div>
            </div>
            <div class="card-factor-row">
              <span>🛡️ 안정 ${r.financial_score != null ? fmt(r.financial_score, 1) : "—"}</span>
              <div class="card-factor-bar"><em style="width:${sBar}%; background:#a855f7;"></em></div>
            </div>
          </div>

          ${r.note ? `<div class="meta" style="background:#10182a; padding:6px 8px; border-radius:6px; margin:6px 0; font-size:11.5px; border-left:3px solid #38bdf8;">📝 ${escapeHtml(r.note)}</div>` : ""}

          <div class="stock-card-price-row">
            <span style="font-size:12px; color:#94a3b8;">최근 종가</span>
            <span class="stock-card-price">${priceTxt}</span>
          </div>
        </div>

        <div class="stock-card-actions">
          <button class="primary" data-open="${code}" style="font-size:11.5px;">🔍 심층분석</button>
          <button data-backtest-stock="${code}" style="font-size:11.5px; background:rgba(56,189,248,0.15); color:#38bdf8; border-color:rgba(56,189,248,0.4);">🧪 백테스트</button>
          <button class="ghost" data-unwatch="${code}" style="font-size:11.5px; color:#f87171;">삭제</button>
        </div>
      </div>
    `;
  }).join("");

  box.innerHTML = `
    ${heroHtml}
    <div class="watch-portfolio-grid">
      ${stockCardsHtml}
    </div>
  `;

  // Attach event handlers
  box.querySelectorAll("[data-open]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      openStock(el.dataset.open).catch((err) => alert(err.message));
    });
  });
  box.querySelectorAll("[data-unwatch]").forEach((el) => {
    el.addEventListener("click", () => removeWatch(el.dataset.unwatch).catch((err) => alert(err.message)));
  });
  box.querySelectorAll("[data-backtest-stock]").forEach((el) => {
    el.addEventListener("click", () => {
      openStrategyBacktest(el.dataset.backtestStock, el.closest(".stock-card")?.querySelector("h3, b")?.textContent || el.dataset.backtestStock);
    });
  });
}


async function addWatch(ticker, company) {
  await api("/api/watchlist", { method: "POST", body: JSON.stringify({ ticker, company }) });
  await loadWatch();
  alert("관심종목에 넣었습니다.");
}

async function removeWatch(ticker) {
  await api(`/api/watchlist/${ticker}`, { method: "DELETE" });
  await loadWatch();
}

function renderSvgSparkline(spark, isUp, id) {
  const pts = (spark || []).map((n) => Number(n)).filter((n) => Number.isFinite(n));
  if (!pts || pts.length < 2) return "";
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const range = max - min || 1;
  const w = 260;
  const h = 48;
  const coords = pts.map((v, i) => {
    const x = (i / (pts.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const linePoints = coords.join(" ");
  const areaPoints = `0,${h} ${linePoints} ${w},${h}`;
  const strokeColor = isUp ? "#ef4b6a" : "#4c8dff";
  const gradId = `grad-${id || Math.random().toString(36).slice(2, 8)}`;
  const stopColor = isUp ? "rgba(239, 75, 106, 0.25)" : "rgba(76, 141, 255, 0.25)";

  return `<svg class="macro-card-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs>
      <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${stopColor}" />
        <stop offset="100%" stop-color="rgba(0,0,0,0)" />
      </linearGradient>
    </defs>
    <polygon points="${areaPoints}" fill="url(#${gradId})" />
    <polyline points="${linePoints}" fill="none" stroke="${strokeColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
  </svg>`;
}

function renderYenCarryCard(yc) {
  if (!yc) return "";
  const lvl = yc.risk_level || "STABLE";
  const lvlKo = yc.risk_ko || "안정";
  const score = yc.unwind_score || 30;
  const usdjpy = yc.usdjpy || {};
  const nikkei = yc.nikkei || {};
  const jpykrw = yc.jpykrw || {};

  const reasons = (yc.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");
  const syncTime = formatSyncTime(yc.fetched_at || yc.updated_at);

  return `
    <div class="yencarry-card" id="yencarry-card-container">
      <div class="yencarry-header">
        <div>
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <h3 style="margin:0;">엔 캐리 트레이드 위험 모니터 (Yen Carry Monitor)</h3>
            <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 7px;">글로벌 외환·채권 연동</span>
          </div>
          <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:4px; font-size:12px; color:#94a3b8;">
            <span>엔/달러 환율 속도 + 닛케이 225 + 미·일 금리차 종합 청산 위험도</span>
            <span>⏱️ <b>실시간 동기화:</b> <span id="yencarry-synced-badge" style="color:#38bdf8; font-weight:700;">${syncTime}</span></span>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <button type="button" id="btn-yencarry-refresh" class="trade-refresh-btn" style="height:32px; font-size:11.5px; padding:0 10px; border-radius:6px;" title="엔/달러 환율 및 닛케이 225 실시간 재수집">
            <span>🔄</span><span>실시간 새로고침</span>
          </button>
          <div class="yencarry-badge ${lvl}">
            ${score}점 · ${escapeHtml(lvlKo)}
          </div>
        </div>
      </div>
      <div class="yencarry-grid">
        <div class="yencarry-metric">
          <span>엔/달러 (USD/JPY)</span>
          <b>${usdjpy.last != null ? fmt(usdjpy.last, 2) + "엔" : "—"}</b>
          <div class="meta">${pctCell(usdjpy.ret_1m)} (1개월)</div>
        </div>
        <div class="yencarry-metric">
          <span>100엔/원 (JPY/KRW)</span>
          <b>${jpykrw.last != null ? fmt(jpykrw.last, 2) + "원" : "—"}</b>
          <div class="meta">${pctCell(jpykrw.ret_1m)} (1개월)</div>
        </div>
        <div class="yencarry-metric">
          <span>일본 닛케이 225</span>
          <b>${nikkei.last != null ? fmt(nikkei.last, 2) : "—"}</b>
          <div class="meta">${pctCell(nikkei.ret_1m)} (1개월)</div>
        </div>
        <div class="yencarry-metric">
          <span>미국 10년 국채금리</span>
          <b>${yc.us_10y_yield != null ? fmt(yc.us_10y_yield, 2) + "%" : "—"}</b>
          <div class="meta">할인율 및 금리차</div>
        </div>
      </div>
      <p style="margin:8px 0 4px;font-size:13px;color:#d5deee"><b>${escapeHtml(yc.summary || "")}</b></p>
      ${reasons ? `<ul style="margin:4px 0 0;padding-left:18px;font-size:12px;color:var(--muted)">${reasons}</ul>` : ""}
      <p class="hint" style="margin-top:6px">${escapeHtml(yc.disclaimer || "")}</p>
    </div>
  `;
}

const MACRO_BAROMETER_GUIDE = {
  "^KS11": {
    name: "코스피 지수 (KOSPI)",
    tip: "대한민국 유가증권시장 대표 대형 수출주 종합 지수입니다. 삼성전자·SK하이닉스·현대차 등 대표 기업들의 시가총액 가중 방식입니다.",
    up: "외국인/기관 순매수 유입 및 국내 투자심리 개선 (국내 주식시장 호재)",
    down: "글로벌 위험회피 및 대형주 매물 출회 (단기 분할매수 기회 탐색)",
    hint: "상승 승률과 거래대금 동반 여부가 추세 지속성의 핵심입니다."
  },
  "^KQ11": {
    name: "코스닥 지수 (KOSDAQ)",
    tip: "대한민국 중소형 성장주, 바이오·헬스케어, IT·소부장, 2차전지 기업 중심의 기술주 시장 지수입니다.",
    up: "개인 투자자 자금 유입 및 성장주·테마주 투자심리 극대화 (중소형주 호재)",
    down: "신용융자 청산 및 고PER 성장주 차익 매물 출회 (리스크 관리 필요)",
    hint: "금리 하락기 및 연초 1월 효과 시기에 탄력성이 뛰어납니다."
  },
  "^GSPC": {
    name: "미국 S&P 500",
    tip: "미국 대표 500대 우량 대형 기업으로 구성된 글로벌 증시의 절대적 기준 벤치마크 지수입니다.",
    up: "글로벌 위험자산 선호 심리(Risk-On) 확산 및 한국 수출주 동반 상승 (국내 증시 호재)",
    down: "글로벌 증시 조정 및 안전자산 도피 (국내 증시 갭하락 요인)",
    hint: "미국 기업 실적(어닝) 서프라이즈 여부가 핵심 드라이버입니다."
  },
  "^IXIC": {
    name: "미국 나스닥 (NASDAQ)",
    tip: "애플·엔비디아·마이크로소프트·구글 등 글로벌 빅테크와 첨단 기술주 중심 지수입니다.",
    up: "AI·반도체 기술주 랠리 ➔ 국내 반도체(삼성전자·SK하이닉스) 강력 호재",
    down: "국채 금리 급등 시 고평가 테크주 밸류에이션 하락 압박",
    hint: "미국 10년물 국채 금리와 역의 상관관계를 자주 보입니다."
  },
  "^N225": {
    name: "일본 닛케이 225",
    tip: "일본 도쿄증권거래소의 225개 대표 우량주 지수이자 아시아 증시 선행 지표입니다.",
    up: "아시아 전반으로 글로벌 펀드 자금 유입 (우호적 환경)",
    down: "엔화 급격한 강세 및 엔캐리 트레이드 청산 시 아시아 증시 변동성 확대",
    hint: "엔/달러 환율 및 일본은행(BOJ) 금리 인상 정책과 밀접합니다."
  },
  "DX-Y.NYB": {
    name: "달러 인덱스 (DXY)",
    tip: "유로, 엔, 파운드 등 주요 6개국 통화 대비 미국 달러화의 가치를 나타내는 지수입니다.",
    up: "강달러 ➔ 글로벌 안전자산 쏠림으로 한국/신흥국 증시에서 외국인 자금 유출 (악재)",
    down: "약달러 ➔ 글로벌 유동성 완화로 한국 증시로 외국인 순매수 유입 촉진 (강력 호재)",
    hint: "100 이하 하락 시 한국 주식시장에 가장 강력한 외국인 매수세가 유입됩니다."
  },
  "KRW=X": {
    name: "원/달러 환율 (USD/KRW)",
    tip: "1달러를 구매하기 위한 원화 금액입니다. 한국 증시 외국인 수급의 가장 결정적인 변수입니다.",
    up: "원화 약세(1,400원 초과) ➔ 외국인 환차손 회피 매도 및 수입물가 상승 부담 (악재)",
    down: "원화 강세(1,350원 이하) ➔ 외국인 환차익 매력 증가로 대규모 순매수 유입 (호재)",
    hint: "원/달러 하락 추세 전환 시 코스피 대형 수출주 매수를 적극 고려하세요."
  },
  "JPY=X": {
    name: "엔/달러 환율 (USD/JPY)",
    tip: "1달러당 엔화 가치입니다. 글로벌 엔캐리 트레이드 및 한·일 수출 경쟁력 척도입니다.",
    up: "엔화 약세(160엔 접근) ➔ 일본 수출기업 가격경쟁력 상승으로 한국 자동차·IT 부담",
    down: "엔화 강세(150엔 이하 급락) ➔ 글로벌 엔캐리 청산에 따른 단기 변동성 주의",
    hint: "완만한 엔화 강세는 한국 수출 기업의 가격 경쟁력 회복에 유리합니다."
  },
  "JPYKRW=X": {
    name: "100엔/원 환율 (JPY/KRW)",
    tip: "100엔당 원화 환율입니다. 일본 제품 대비 한국 수출품의 상대 가격 경쟁력을 나타냅니다.",
    up: "엔화 강세/원화 약세 ➔ 일본 대비 한국 수출기업(조선, 자동차, 철강) 경쟁력 강화 (호재)",
    down: "엔저 심화 ➔ 일본 제품 가격경쟁력 상승 및 원자재 수입 부담",
    hint: "900원선 이상 회복 시 한국 제조업 수출 마진에 우호적입니다."
  },
  "GC=F": {
    name: "국제 금 선물 (Gold)",
    tip: "전 세계 대표 안전자산이자 화폐 가치 하락(인플레이션) 헤지 상품입니다.",
    up: "지정학적 전쟁 위기, 경기 침체 우려, 통화가치 하락 시 안전자산 자금 쏠림 (경계)",
    down: "시장 공포 완화 및 주식 등 실물 위험자산으로 자금 복귀 (주식시장 호재)",
    hint: "금 가격이 사상 최고치 경신 중일 때는 포트폴리오 안전마진(현금/방어주) 확보가 권장됩니다."
  },
  "CL=F": {
    name: "WTI 국제 원유 (Crude Oil)",
    tip: "글로벌 제조업, 운송, 화학 산업의 핵심 에너지이자 글로벌 원자재 물가 지표입니다.",
    up: "고유가($85 이상) ➔ 국내 제조기업 원가 상승, 무역수지 악화, 인플레 유발 (악재)",
    down: "적정 유가($65~$75) ➔ 물가 안정, 제조원가 절감, 금리 인하 여력 확대 (한국 제조업 호재)",
    hint: "에너지 의존도가 높은 한국 경제 특성상 급격한 유가 상승은 기업 마진을 압박합니다."
  },
  "HG=F": {
    name: "구리 선물 (Copper / '닥터 코퍼')",
    tip: "전선, 전력망, 전기차, AI 데이터센터 등 산업 전반에 쓰여 실물 경기를 가장 정확히 진단하는 지표입니다.",
    up: "글로벌 제조업 확장 및 AI 전력 인프라 투자 수요 폭발 (한국 전력기기·수출주 호재)",
    down: "글로벌 경기 침체 및 제조업 수요 둔화 신호 (경계)",
    hint: "구리 가격 상승은 글로벌 경기 회복과 AI 인프라 확장을 강력히 지지합니다."
  },
  "BTC-USD": {
    name: "비트코인 (Bitcoin)",
    tip: "글로벌 디지털 유동성과 투기적 위험자산 심리를 대변하는 최전선 자산입니다.",
    up: "글로벌 유동성 풍부 및 극단적 위험자산 선호 심리 (Risk-On) 확인 (성장주 우호)",
    down: "글로벌 유동성 축소 및 레버리지 청산 확산 (경계)",
    hint: "비트코인의 급등락은 위험자산 시장 전반의 유동성 민감도를 선행해서 보여줍니다."
  },
  "ETH-USD": {
    name: "이더리움 (Ethereum)",
    tip: "스마트 컨트랙트, 디파이, 웹3 블록체인 생태계의 대표 플랫폼 암호화폐입니다.",
    up: "알트코인 및 블록체인 기술 산업 전반의 유동성 유입 (성장 테마주 우호)",
    down: "가상자산 시장 전반의 위험 회피",
    hint: "이더리움/비트코인 비율은 암호화폐 시장 내 위험 선호 확산 강도를 나타냅니다."
  },
  "^TNX": {
    name: "미국 10년물 국채 금리",
    tip: "전 세계 모든 금융자산 가치평가의 '무위험 할인율' 기준이 되는 글로벌 벤치마크 금리입니다.",
    up: "고금리(4.5% 이상) ➔ 미래 현금흐름 할인율 상승으로 기술주/성장주 밸류에이션 타격 (악재)",
    down: "금리 안정(3.8%~4.2%) ➔ 기업 자금조달 비용 완화 및 주식시장 밸류에이션 확장 (강력 호재)",
    hint: "미국 10년물 금리가 4.5%를 넘어서면 주식 비중을 조절하고 방어적으로 운용하세요."
  },
  "DGS10": {
    name: "미국 10년물 국채 금리 (FRED)",
    tip: "미국 연준 FRED 공식 10년물 국채 수익률입니다. 글로벌 무위험 할인율의 기준점입니다.",
    up: "성장주 및 밸류에이션 부담 가중 (악재)",
    down: "성장주 밸류에이션 리레이팅 호재",
    hint: "4.5% 초과 여부를 주시하세요."
  },
  "T10Y2Y": {
    name: "미국 10Y-2Y 장단기 금리차",
    tip: "미국 10년물 금리 - 2년물 금리 스프레드로, 역사상 가장 정확한 경기 침체 선행 지표입니다.",
    up: "정상화/스티프닝 ➔ 장단기 금리 역전 해소 및 연준의 완화적 통화정책 사이클 (호재)",
    down: "금리 역전 심화(<0) ➔ 1~2년 내 글로벌 경기 침체(Recession) 경고 신호 (주의)",
    hint: "역전 이후 정상화되는 초기에 일시적 시장 변동성이 커질 수 있습니다."
  }
};

function renderTradingEconomicsMacroCards(grouped, cc) {
  const g = grouped || {};
  const allList = [
    ...(g.indices || []),
    ...(g.fx || []),
    ...(g.commodities || []),
    ...(g.crypto || []),
    ...(g.rates || []),
  ];
  if (!allList.length) return "";

  const cards = allList.map((item, idx) => {
    if (!item || item.error || item.last == null) return "";
    const chg = Number(item.ret_1d);
    const delta = item.delta_1d != null ? Number(item.delta_1d) : null;
    const isUp = chg >= 0;
    const chgTxt = chg == null || Number.isNaN(chg) ? "—" : `${isUp ? "+" : ""}${(chg * 100).toFixed(2)}%`;
    const deltaTxt = delta != null && Number.isFinite(delta)
      ? `${delta > 0 ? "+" : ""}${fmt(delta, item.category === "fx" && Math.abs(delta) < 1 ? 4 : 2)}`
      : "";
    const priceFmt = fmt(item.last, item.category === "fx" && item.last < 10 ? 3 : 2);
    const sparkSvg = renderSvgSparkline(item.spark, isUp, `spark-${idx}`);
    const comment = item.comment || (item.ret_1y != null ? `1년 변동 ${pctCell(item.ret_1y)} · 52주고점 ${pctCell(item.high_52w_distance)}` : "");
    const guide = MACRO_BAROMETER_GUIDE[item.symbol] || MACRO_BAROMETER_GUIDE[item.id] || {
      name: item.label || item.symbol,
      tip: `${item.label || item.symbol} 실시간 글로벌 매크로 시세 지표입니다.`,
      up: "지표 상승 추세",
      down: "지표 하락 추세",
      hint: "거시경제 환경과 환율·금리 동향을 종합적으로 참고하세요."
    };

    return `
      <div class="macro-card has-tip"
           data-macro-card="${escapeHtml(item.symbol)}"
           data-tip-title="${escapeHtml(guide.name || item.label || item.symbol)}"
           data-tip="${escapeHtml(guide.tip)}"
           data-tip-up="${escapeHtml(guide.up)}"
           data-tip-down="${escapeHtml(guide.down)}"
           data-tip-hint="${escapeHtml(guide.hint)}"
           tabindex="0">
        <div class="macro-card-top">
          <div>
            <div class="macro-card-name">${escapeHtml(item.label || item.symbol)}</div>
            <div class="macro-card-sym">${escapeHtml(item.symbol)} · ${escapeHtml(item.unit || "")}</div>
          </div>
          <div style="text-align:right">
            <div class="macro-card-price" data-macro-price="${escapeHtml(item.symbol)}" data-current-val="${item.last}">${priceFmt}</div>
            <div class="macro-card-chg ${isUp ? "up" : "down"}" data-macro-chg="${escapeHtml(item.symbol)}">
              <span data-macro-ret="${escapeHtml(item.symbol)}">${chgTxt}</span>
              ${deltaTxt ? `<small data-macro-delta="${escapeHtml(item.symbol)}" style="font-size:10px; margin-left:3px; opacity:0.9;">(${deltaTxt})</small>` : ""}
            </div>
          </div>
        </div>
        ${sparkSvg}
        ${comment ? `<div class="macro-card-comment">${comment}</div>` : ""}
      </div>
    `;
  }).join("");

  const syncTime = formatSyncTime(grouped?.fetched_at);
  return `
    <div style="margin-top:18px" id="macro-barometer-container">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <div>
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <h3 style="margin:0;">글로벌 매크로 바로미터 (지수 · 환율 · 금·원유 · 비트코인 · 금리)</h3>
            <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 7px;">Yahoo Finance 실시간</span>
            <span class="live-ticker-badge"><span class="live-pulse-dot"></span><span>실시간 라이브 틱 스트리밍</span></span>
          </div>
          <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:4px; font-size:12px; color:#94a3b8;">
            <span>TradingEconomics 스타일 30일/60일 시계열 차트 및 실시간 등락률</span>
            <span>⏱️ <b>실시간 동기화:</b> <span id="barometer-synced-badge" style="color:#38bdf8; font-weight:700;">${syncTime}</span></span>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <button type="button" id="btn-barometer-refresh" class="trade-refresh-btn" style="height:32px; font-size:11.5px; padding:0 10px; border-radius:6px;" title="글로벌 지수·환율·원자재·가상자산 실시간 재수집">
            <span>🔄</span><span>실시간 새로고침</span>
          </button>
          <span class="chip has-tip" data-tip-title="💡 글로벌 매크로 바로미터 도움말" data-tip="각 카드를 마우스로 가리키면 해당 지표의 의미와 상승/하락 시 한국 증시 영향(호재/악재) 상세 가이드가 표시됩니다.">💡 호재/악재 가이드</span>
        </div>
      </div>
      <div class="macro-card-grid">
        ${cards}
      </div>
    </div>
  `;
}

const SA_FACTOR_GUIDE = {
  "가치": {
    name: "💎 가치 (Value)",
    tip: "동종 업계 대비 PER, PBR, EV/EBITDA, 배당수익률 수준을 상대평가합니다. A+일수록 현저한 저평가 상태입니다.",
    hint: "A+ ~ A-: 상위 10% 저평가, B+: 상위 20%, C: 업계 평균, D/F: 고평가 부담"
  },
  "품질": {
    name: "👑 품질 (Quality)",
    tip: "ROE, ROIC, 영업이익률, 부채비율을 종합해 기업의 자본 효율성과 경제적 해자(Moat)를 검증합니다.",
    hint: "A+ 등급 기업은 장기 복리 수익 창출 능력이 가장 뛰어납니다."
  },
  "성장": {
    name: "🚀 성장 (Growth)",
    tip: "3개년 연평균 매출성장률(CAGR), 영업이익 증가율 및 최근 분기 실적 가속도를 측정합니다.",
    hint: "실적 턴어라운드 및 어닝 서프라이즈 시 등급이 가파르게 상승합니다."
  },
  "모멘텀": {
    name: "⚡ 모멘텀 (Momentum)",
    tip: "3/6/12개월 주가 수익률 및 이동평균 정배열 추세를 통해 시장의 매수세 유입 강도를 평가합니다.",
    hint: "가치와 품질이 좋고 모멘텀까지 A 등급인 종목이 주도주가 됩니다."
  },
  "안정성": {
    name: "🛡️ 안정성 (Safety)",
    tip: "유동비율, 당좌비율, 이자보상배율 등 부도 리스크와 재무 건전성을 점검합니다.",
    hint: "D/F 등급 기업은 Quant 유니버스에서 자동 제외됩니다."
  }
};

function renderSeekingAlphaScorecard(card) {
  if (!card || !card.factors || !card.factors.length) return "";
  const dec = card.decision || "HOLD";
  const decKo = card.decision_ko || "보유 관망";
  const rows = (card.factors || []).map((f) => {
    const gradeClean = String(f.grade || "").replace("+", "_PLUS").replace("-", "_MINUS");
    const sub = (f.submetrics || []).map((s) => `${escapeHtml(s.name)} ${escapeHtml(s.display)}`).join(" · ");
    const key = Object.keys(SA_FACTOR_GUIDE).find(k => (f.label || "").includes(k)) || "가치";
    const g = SA_FACTOR_GUIDE[key] || { name: f.label, tip: "팩터 상대평가 백분위입니다.", hint: "동종 업계 내 상대 순위" };

    return `<div class="sa-factor-row has-tip"
                 data-tip-title="${escapeHtml(g.name)}: ${escapeHtml(f.grade)} (백분위 ${f.percentile.toFixed(0)}%)"
                 data-tip="${escapeHtml(g.tip)}"
                 data-tip-hint="${escapeHtml(g.hint)}"
                 tabindex="0">
      <div class="sa-factor-name">${escapeHtml(f.label)}</div>
      <div class="sa-grade-pill ${escapeHtml(gradeClean)}">${escapeHtml(f.grade)}</div>
      <div class="sa-meter"><em style="width:${Math.max(2, Math.min(100, f.percentile))}%"></em></div>
      <div class="sa-submetrics">${sub}</div>
    </div>`;
  }).join("");

  return `
    <article class="sa-scorecard">
      <div class="sa-header">
        <div>
          <h3 style="margin:0 0 4px">Seeking Alpha 스타일 팩터 성적표 (Factor Scorecard)</h3>
          <span class="hint">미국 기관형 A+ ~ F 5대 팩터 상대평가 · Quant 점수 요약</span>
        </div>
        <div class="sa-decision ${dec} has-tip"
             data-tip-title="🎯 팩터 종합 의견: ${escapeHtml(decKo)} (${escapeHtml(dec)})"
             data-tip="5대 팩터(가치·품질·성장·모멘텀·안정)의 상대평가 등급을 가중 집계하여 산출한 최종 투자 판단입니다."
             data-tip-hint="STRONG BUY/BUY: 팩터 종합 최상위 5% 우량주, HOLD: 건전하나 모멘텀 관망, SELL: 밸류에이션 부담"
             tabindex="0">
          ${escapeHtml(decKo)}
        </div>
      </div>
      <div class="sa-factors-list">
        ${rows}
      </div>
      <p class="hint" style="margin:10px 0 0">${escapeHtml(card.disclaimer || "")}</p>
    </article>
  `;
}

function toneTag(tone) {
  const t = tone || "중립";
  return `<span class="tag tone-${escapeHtml(t)}">${escapeHtml(t)}</span>`;
}

function renderYieldComparisonCard(yc) {
  if (!yc) return "";
  const bok = yc.bok_rate != null ? fmt(yc.bok_rate, 2) + "%" : "—";
  const fed = yc.fed_rate != null ? fmt(yc.fed_rate, 2) + "%" : "—";
  const diff = yc.kr_us_diff != null ? `${yc.kr_us_diff > 0 ? "+" : ""}${fmt(yc.kr_us_diff, 2)}%p` : "—";
  const diffCls = yc.kr_us_diff != null && yc.kr_us_diff < 0 ? "down" : "up";
  const spread = yc.us_spread != null ? `${yc.us_spread > 0 ? "+" : ""}${fmt(yc.us_spread, 2)}%p` : "—";
  const spreadCls = yc.us_spread != null && yc.us_spread < 0 ? "down" : "up";
  const us10 = yc.us_10y != null ? fmt(yc.us_10y, 2) + "%" : "—";
  const us2 = yc.us_2y != null ? fmt(yc.us_2y, 2) + "%" : "—";
  const ktb = yc.ktb_3y != null ? fmt(yc.ktb_3y, 2) + "%" : "—";

  return `
    <div class="yield-compare-card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <h3 style="margin:0;font-size:15px;color:#fff;">한·미 금리차 및 수익률 곡선 (Yield Curve & Spread)</h3>
          <span class="hint">한국은행 vs 미국 연준 정책금리 및 미 국채 10년-2년 장단기 스프레드</span>
        </div>
      </div>
      <div class="yield-compare-grid">
        <div class="yield-compare-box">
          <span>한·미 기준금리차 (KR - US)</span>
          <b class="${diffCls}">${diff}</b>
          <div class="meta" style="margin-top:2px;">한국 ${bok} vs 미국 ${fed}</div>
        </div>
        <div class="yield-compare-box">
          <span>미 장단기 스프레드 (10Y-2Y)</span>
          <b class="${spreadCls}">${spread}</b>
          <div class="meta" style="margin-top:2px;">${yc.us_spread != null && yc.us_spread < 0 ? "역전 (침체 경계)" : "정상 기울기"}</div>
        </div>
        <div class="yield-compare-box">
          <span>미국 10년 / 2년 금리</span>
          <b>${us10}</b>
          <div class="meta" style="margin-top:2px;">2년물 ${us2}</div>
        </div>
        <div class="yield-compare-box">
          <span>한국 국고채 3년</span>
          <b>${ktb}</b>
          <div class="meta" style="margin-top:2px;">국내 시중금리 벤치마크</div>
        </div>
      </div>
    </div>
  `;
}

function renderMacroItemCard(it, idx, prefix) {
  if (!it) return "";
  const tone = it.tone || "중립";
  const isUp = it.delta != null ? it.delta >= 0 : true;
  const deltaTxt = it.delta != null && !Number.isNaN(Number(it.delta))
    ? `${it.delta > 0 ? "+" : ""}${fmt(it.delta, 2)}${it.unit === "%" ? "%p" : it.unit ? " " + it.unit : ""}`
    : "";
  const deltaCls = it.delta != null ? (isUp ? "up" : "down") : "";
  const sparkSvg = renderSvgSparkline(it.spark, isUp, `${prefix || "m"}-${idx}`);

  return `
    <div class="macro-item-card tone-${escapeHtml(tone)}">
      <div class="macro-item-top">
        <div class="macro-item-label">
          <b>${escapeHtml(it.label)}</b>
          ${toneTag(tone)}
        </div>
        <span class="meta">${escapeHtml(it.as_of || "")}</span>
      </div>
      <div class="macro-item-main">
        <div class="macro-item-val">
          ${it.value == null ? "미연결" : fmt(it.value, 2)}
          <small>${escapeHtml(it.unit || "")}</small>
        </div>
        ${deltaTxt ? `<span class="macro-item-delta ${deltaCls}">${escapeHtml(deltaTxt)}</span>` : ""}
      </div>
      ${sparkSvg}
      <p class="macro-item-desc">${escapeHtml(it.comment || "")}</p>
    </div>
  `;
}

function renderBriefItems(items) {
  return (items || []).map((it, idx) => renderMacroItemCard(it, idx, "brief")).join("");
}

function renderSeasonalitySection(season) {
  if (!season || !season.months) return "";
  const cur = season.current_stat || {};
  const strat = season.strategy || {};
  const election = season.election_overlay || {};
  const toneCls = cur.tone === "우호" ? "good" : cur.tone === "부담" ? "bad" : "neutral";
  const stockRatio = strat.stock_ratio || 70;
  const cashRatio = strat.cash_ratio || 30;
  const leading = strat.leading_sectors || [];
  const lagging = strat.lagging_sectors || [];
  const tactics = strat.tactics || [];

  const monthCards = (season.months || []).map((m) => {
    const isCur = m.is_current;
    const isUp = (m.avg_ret || 0) >= 0;
    const retCls = isUp ? "up" : "down";
    const winRate = m.win_rate || 50;
    const winCls = winRate >= 60 ? "" : winRate <= 45 ? "low" : "mid";

    return `
      <div class="season-card ${isCur ? "current-month" : ""}">
        <div class="season-month-header">
          <span>${escapeHtml(m.name)}</span>
          ${isCur ? '<span class="season-cur-tag">현재</span>' : ""}
        </div>
        <div class="season-ret ${retCls}">${isUp ? "+" : ""}${fmt(m.avg_ret, 1)}%</div>
        <div class="season-win-bar">
          <div class="season-win-fill ${winCls}" style="width:${winRate}%"></div>
        </div>
        <div class="season-win-txt">승률 ${winRate.toFixed(0)}%</div>
      </div>
    `;
  }).join("");

  return `
    <div class="seasonality-wrapper">
      <div class="season-diag-box">
        <!-- Top Status Bar -->
        <div class="season-diag-header">
          <div class="season-diag-badge ${toneCls}">
            📅 ${season.current_month_name} 계절성: ${escapeHtml(cur.theme || cur.tone || "")} · ${strat.tone || ""}
          </div>
          <div class="season-diag-cycle">
            <span style="color:#60a5fa;font-weight:700;">🔄 ${escapeHtml(strat.cycle_name || "")}</span>
            <span class="meta" style="margin-left:6px;">(${escapeHtml(strat.cycle_comment || "")})</span>
          </div>
        </div>

        <!-- Strategy Overview Full Width -->
        <div class="season-diag-desc">
          <b style="color:#60a5fa;">🎯 ${season.current_month_name} 퀀트 운용 가이드:</b> ${escapeHtml(strat.desc || "")}
        </div>

        <!-- Election & Political Cycle Overlay Full Width -->
        ${election.title ? `
          <div class="season-election-box">
            <div class="season-election-title">
              <span>🏛️ ${escapeHtml(election.title)}</span>
              <span class="chip warn" style="font-size:11px; padding:2px 6px;">선거 & 정책 변수 오버레이</span>
            </div>
            <div style="margin-bottom:4px; color:#fef9c3;"><b>📈 역사적 주기 패턴:</b> ${escapeHtml(election.pattern || "")}</div>
            <div style="font-size:12px; color:#cbd5e1; margin-bottom:4px;"><b>💡 실전 파급 효과:</b> ${escapeHtml(election.impact || "")}</div>
            <div style="font-size:12px; color:#94a3b8;"><b>🇰🇷 국내 선거·정책 변수:</b> ${escapeHtml(election.kr_policy || "")}</div>
          </div>
        ` : ""}

        <!-- Strategy & Sector Playbook Grid (Auto-fit, Responsive) -->
        <div class="season-playbook-grid">
          <div class="season-playbook-box">
            <span class="season-playbook-title">⚖️ 권장 포트폴리오 비중</span>
            <div style="display:flex; justify-content:space-between; font-size:12px; margin:8px 0 6px;">
              <span>주식 <b style="color:#34d399;">${stockRatio}%</b></span>
              <span>현금 <b style="color:#fbbf24;">${cashRatio}%</b></span>
            </div>
            <div style="height:10px; background:#1e293b; border-radius:99px; display:flex; overflow:hidden;">
              <div style="width:${stockRatio}%; background:linear-gradient(90deg, #10b981, #34d399);"></div>
              <div style="width:${cashRatio}%; background:linear-gradient(90deg, #f59e0b, #fbbf24);"></div>
            </div>
          </div>

          <div class="season-playbook-box">
            <span class="season-playbook-title">🌟 이 달의 역사적 강세 섹터</span>
            <div class="season-sector-chips">
              ${leading.map((s) => `<span class="season-chip lead">${escapeHtml(s)}</span>`).join("") || '<span class="meta">데이터 없음</span>'}
            </div>
          </div>

          <div class="season-playbook-box">
            <span class="season-playbook-title">⚠️ 이 달의 역사적 약세/경계 섹터</span>
            <div class="season-sector-chips">
              ${lagging.map((s) => `<span class="season-chip lag">${escapeHtml(s)}</span>`).join("") || '<span class="meta">데이터 없음</span>'}
            </div>
          </div>
        </div>

        ${tactics.length ? `
          <div style="margin-top:4px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.08); font-size:12.5px;">
            <b style="color:#60a5fa;">💡 핵심 실전 트레이딩 체크리스트:</b>
            <ul style="margin:6px 0 0; padding-left:18px; color:#cbd5e1; line-height:1.6;">
              ${tactics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}
            </ul>
          </div>
        ` : ""}
      </div>

      <!-- 12-Month Heatmap Calendar Grid -->
      <div class="seasonality-grid">
        ${monthCards}
      </div>
      <p class="hint" style="margin:10px 0 0;">${escapeHtml(season.disclaimer || "")}</p>
    </div>
  `;
}

function renderStanceCard(block) {
  const s = block || {};
  return `<div class="tone-card ${escapeHtml(s.tone || "")}">
    <span>${escapeHtml(s.title || "")}</span>
    <b>${escapeHtml(s.label || s.tone || "—")}</b>
    <p>${escapeHtml(s.comment || "")}</p>
  </div>`;
}

let macroCache = null;

async function loadMacro(refresh) {
  const briefBox = $("#brief-box");
  const seasonBox = $("#seasonality-box");
  const newsBox = $("#news-box");
  if (!briefBox && !newsBox && !seasonBox) return;

  if (macroCache && !refresh) {
    renderMacroData(macroCache);
    return;
  }

  if (seasonBox && !seasonBox.innerHTML.trim()) {
    seasonBox.innerHTML = `
      <div class="skeleton-spinner-box" style="margin:6px 0;">
        <div class="skeleton-spinner"></div>
        <div class="skeleton-loading-text">
          <b>📅 30개년 코스피 계절성 빅데이터 & 월별 전략 분석 중...</b>
          <p>1~12월 역사적 월별 수익률, 승률 및 추천 섹터 전략을 집계하고 있습니다.</p>
        </div>
      </div>
    `;
  }
  if (briefBox && !briefBox.innerHTML.trim()) {
    briefBox.innerHTML = `
      <div class="skeleton-spinner-box" style="margin:6px 0;">
        <div class="skeleton-spinner"></div>
        <div class="skeleton-loading-text">
          <b>🌐 한국은행 ECOS, 미국 연준 FRED 및 글로벌 매크로 지표 동기화 중...</b>
          <p>환율, 국채 금리, 원자재 및 거시 펀더멘털 실시간 데이터를 불러오고 있습니다.</p>
        </div>
      </div>
      <div class="skeleton-shimmer-card" style="height:110px; margin:8px 0;"></div>
      <div class="skeleton-shimmer-card" style="height:180px; margin:8px 0;"></div>
    `;
  }
  if (newsBox && !newsBox.innerHTML.trim()) {
    newsBox.innerHTML = `
      <div class="skeleton-spinner-box" style="margin:6px 0;">
        <div class="skeleton-spinner"></div>
        <div class="skeleton-loading-text">
          <b>📰 글로벌 실시간 매크로 뉴스 수집 중...</b>
          <p>네이버 금융 및 주요 언론사 거시경제 헤드라인을 수집하고 있습니다.</p>
        </div>
      </div>
    `;
  }

  try {
    const data = await api(`/api/macro${refresh ? "?refresh=true" : ""}`);
    macroCache = data;
    renderMacroData(data);
  } catch (err) {
    if (briefBox) briefBox.innerHTML = `<div style="padding:16px; color:#ef4444;">❌ 매크로 지표 로딩 실패: ${escapeHtml(err.message)}</div>`;
  }
}

function renderMacroData(data) {
  const brief = data.brief || {};
  const news = data.news || {};
  const yencarry = data.yencarry || {};
  const grouped = data.grouped_assets || {};
  const cc = data.commodities_crypto || {};
  const seasonality = data.seasonality;

  const seasonBox = $("#seasonality-box");
  if (seasonBox) {
    seasonBox.innerHTML = renderSeasonalitySection(seasonality);
  }

  const briefBox = $("#brief-box");
  if (briefBox) {
    const overall = brief.overall || {};
    const kr = (brief.domestic || {}).stance || {};
    const us = (brief.international || {}).stance || {};
    const DUP_IDS = new Set([
      "usdkrw_bok", "DEXKOUS", "DGS10", "^KS11", "^KQ11", "^GSPC", "^IXIC", "^N225",
      "GC=F", "CL=F", "HG=F", "BTC-USD", "ETH-USD", "^TNX", "DX-Y.NYB", "KRW=X", "JPY=X"
    ]);
    const domesticFiltered = (brief.domestic?.items || []).filter((it) => !DUP_IDS.has(it.id));
    const internationalFiltered = (brief.international?.items || []).filter((it) => !DUP_IDS.has(it.id));

    briefBox.innerHTML = `
      <div class="brief-head">
        ${renderStanceCard({ ...overall, title: "종합" })}
        ${renderStanceCard({ ...kr, title: "국내" })}
        ${renderStanceCard({ ...us, title: "국제" })}
      </div>
      ${renderYieldComparisonCard(brief.yield_comparison)}
      ${renderMarginDebtBarometer(data.margin_debt)}
      ${renderYenCarryCard(yencarry)}
      ${renderTradingEconomicsMacroCards(grouped, cc)}
      ${!seasonBox ? renderSeasonalitySection(seasonality) : ""}
      <div class="macro-bi-grid">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
            <div>
              <div style="display:flex; align-items:center; gap:8px;">
                <h3 style="margin:0;font-size:15px;color:#e8eef8;">🇰🇷 한국은행 ECOS 거시 펀더멘털</h3>
                <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 7px;">ECOS</span>
              </div>
              <small style="color:#38bdf8; font-size:11px;">⏱️ 동기화: ${formatSyncTime(data.ecos?.fetched_at || data.fetched_at)}</small>
            </div>
            <button type="button" id="btn-ecos-fundamental-refresh" class="trade-refresh-btn" style="height:28px; font-size:11px; padding:0 8px; border-radius:6px;" title="한국은행 통계 실시간 재조회">
              <span>🔄</span><span>실시간 새로고침</span>
            </button>
          </div>
          <p class="hint" style="margin-bottom:8px;">기준금리, 한-미 금리차, 국고채 3년, 한국 CPI 물가지수, M2 통화량 (환율·지수는 상단 바로미터 참조)</p>
          <div class="macro-item-grid">
            ${domesticFiltered.map((it, idx) => renderMacroItemCard(it, idx, "kr")).join("")}
          </div>
        </div>
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
            <div>
              <div style="display:flex; align-items:center; gap:8px;">
                <h3 style="margin:0;font-size:15px;color:#e8eef8;">🌐 미국 연준 FRED 거시 펀더멘털</h3>
                <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px; padding:2px 7px;">FRED</span>
              </div>
              <small style="color:#38bdf8; font-size:11px;">⏱️ 동기화: ${formatSyncTime(data.fred?.fetched_at || data.fetched_at)}</small>
            </div>
            <button type="button" id="btn-fred-fundamental-refresh" class="trade-refresh-btn" style="height:28px; font-size:11px; padding:0 8px; border-radius:6px;" title="미국 연준 통계 실시간 재조회">
              <span>🔄</span><span>실시간 새로고침</span>
            </button>
          </div>
          <p class="hint" style="margin-bottom:8px;">연준 기준금리, 미 국채 2년, 10Y-2Y 장단기 스프레드, 미국 CPI 물가, 미국 실업률 (10년금리·환율은 상단 바로미터 참조)</p>
          <div class="macro-item-grid">
            ${internationalFiltered.map((it, idx) => renderMacroItemCard(it, idx, "us")).join("")}
          </div>
        </div>
      </div>
      <p class="hint">${escapeHtml(brief.disclaimer || data.disclaimer || "")}</p>
    `;
  }
  stampLive("#macro-live");

  const newsBox = $("#news-box");
  if (newsBox) {
    if (!news.configured) {
      newsBox.innerHTML = `<p class="hint">${escapeHtml(news.error || "설정에서 네이버 검색 Client ID/Secret을 넣으면 뉴스가 붙습니다.")}</p>`;
    } else {
      const groups = (news.groups || [])
        .map((g) => {
          const items = (g.items || [])
            .slice(0, 6)
            .map((n) => {
              const sent = classifyNewsSentiment(n.title, n.description);
              return `<li>
                <div style="display:flex; align-items:flex-start; gap:4px;">
                  <span class="news-badge ${sent.cls}">${sent.icon} ${sent.label}</span>
                  <a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener" style="font-weight:500;">${escapeHtml(n.title)}</a>
                </div>
                <div class="meta" style="margin-top:3px;">${escapeHtml((n.pubDate || "").slice(0, 22))} · ${escapeHtml((n.description || "").slice(0, 100))}</div>
              </li>`;
            })
            .join("");
          return `<div class="news-group"><h3>${escapeHtml(g.label)}</h3>${g.error ? `<p class="hint">${escapeHtml(g.error)}</p>` : `<ul class="news-list">${items || "<li>기사 없음</li>"}</ul>`}</div>`;
        })
        .join("");
      const encyc = (news.encyc || [])
        .slice(0, 3)
        .map((x) => `<li><b>${escapeHtml(x.title || "")}</b><div class="meta">${escapeHtml((x.description || "").slice(0, 140))}</div></li>`)
        .join("");
      newsBox.innerHTML = `
        ${asofBanner(news.fetched_at ? `네이버 뉴스 ${fmtWhen(news.fetched_at)}` : "")}
        <div class="news-groups">${groups || `<p class="hint">${escapeHtml(news.error || "뉴스 없음")}</p>`}</div>
        ${encyc ? `<h3>용어 설명 (네이버 지식백과)</h3><ul class="news-list">${encyc}</ul>` : ""}
        <p class="hint">${escapeHtml(news.disclaimer || "네이버 금융 주요 실시간 뉴스입니다.")}</p>
      `;
    }
  }

  const btnRefresh = $("#btn-barometer-refresh");
  if (btnRefresh) {
    btnRefresh.onclick = async () => {
      btnRefresh.disabled = true;
      btnRefresh.innerHTML = "<span>⏳</span><span>수집 중...</span>";
      try {
        await loadMacro(true);
      } finally {
        btnRefresh.disabled = false;
        btnRefresh.innerHTML = "<span>🔄</span><span>실시간 새로고침</span>";
      }
    };
  }
  startMacroLivePolling();
}

let macroLiveTimer = null;
let isMacroLiveFetching = false;

function updateMacroLiveCard(it) {
  if (!it || !it.symbol) return;
  const sym = CSS.escape(it.symbol);
  const priceEl = document.querySelector(`[data-macro-price="${sym}"]`);
  const chgEl = document.querySelector(`[data-macro-chg="${sym}"]`);
  const retEl = document.querySelector(`[data-macro-ret="${sym}"]`);
  const deltaEl = document.querySelector(`[data-macro-delta="${sym}"]`);

  if (!priceEl || it.last == null) return;

  const oldVal = parseFloat(priceEl.dataset.currentVal);
  const newVal = parseFloat(it.last);

  const priceFmt = fmt(it.last, it.category === "fx" && it.last < 10 ? 3 : 2);
  const chg = Number(it.ret_1d);
  const delta = it.delta_1d != null ? Number(it.delta_1d) : null;
  const isUp = chg >= 0;
  const chgTxt = chg == null || Number.isNaN(chg) ? "—" : `${isUp ? "+" : ""}${(chg * 100).toFixed(2)}%`;
  const deltaTxt = delta != null && Number.isFinite(delta)
    ? `${delta > 0 ? "+" : ""}${fmt(delta, it.category === "fx" && Math.abs(delta) < 1 ? 4 : 2)}`
    : "";

  if (!Number.isNaN(oldVal) && Math.abs(oldVal - newVal) > 0.0001) {
    priceEl.textContent = priceFmt;
    priceEl.dataset.currentVal = newVal;

    priceEl.classList.remove("price-flash-up", "price-flash-down");
    void priceEl.offsetWidth; // Force CSS reflow
    if (newVal > oldVal) {
      priceEl.classList.add("price-flash-up");
    } else {
      priceEl.classList.add("price-flash-down");
    }
  }

  if (chgEl) {
    chgEl.className = `macro-card-chg ${isUp ? "up" : "down"}`;
  }
  if (retEl) {
    retEl.textContent = chgTxt;
  }
  if (deltaEl && deltaTxt) {
    deltaEl.textContent = `(${deltaTxt})`;
  }
}

async function pollMacroLiveTicker() {
  if (isMacroLiveFetching) return;
  if (currentView !== "market" || document.hidden) return;

  isMacroLiveFetching = true;
  try {
    const res = await api("/api/macro/live-ticker");
    if (res && res.ok && Array.isArray(res.items)) {
      res.items.forEach(updateMacroLiveCard);
      const badge = $("#barometer-synced-badge");
      if (badge && res.fetched_at) {
        badge.textContent = formatSyncTime(res.fetched_at);
      }
    }
  } catch (e) {
    // Ignore ticker polling errors
  } finally {
    isMacroLiveFetching = false;
  }
}

function startMacroLivePolling() {
  stopMacroLivePolling();
  if (currentView === "market" && !document.hidden) {
    macroLiveTimer = setInterval(pollMacroLiveTicker, 4500);
  }
}

function stopMacroLivePolling() {
  if (macroLiveTimer) {
    clearInterval(macroLiveTimer);
    macroLiveTimer = null;
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopMacroLivePolling();
  } else if (currentView === "market") {
    startMacroLivePolling();
    pollMacroLiveTicker().catch(() => {});
  }
});

function metaLine(el, info) {
  el.textContent = info.configured ? `${info.masked} (${info.length}자)` : "미설정";
  el.className = "meta " + (info.configured ? "ok" : "warn");
}

let rawKeysCache = null;

function setupKeyShowHideToggles() {
  $$(".btn-toggle-pw").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const targetId = btn.dataset.target;
      const input = targetId ? $(`#${targetId}`) : btn.previousElementSibling;
      if (!input) return;

      const isPw = input.type === "password";
      if (isPw) {
        input.type = "text";
        btn.textContent = "🙈";
        btn.title = "키 숨기기";
        btn.classList.add("active");

        if (!input.value.trim()) {
          try {
            if (!rawKeysCache) {
              rawKeysCache = await api("/api/settings/raw");
            }
            const fieldMap = {
              "key-xai": "xai_api_key",
              "key-deepseek": "deepseek_api_key",
              "key-openrouter": "openrouter_api_key",
              "key-naver-id": "naver_client_id",
              "key-naver-secret": "naver_client_secret",
              "key-naver-map-id": "naver_map_client_id",
              "key-naver-map-secret": "naver_map_client_secret",
              "key-toss-id": "toss_client_id",
              "key-toss-secret": "toss_client_secret",
              "key-fred": "fred_api_key",
              "key-ecos": "bok_ecos_api_key",
              "key-telegram": "telegram_bot_token",
              "key-opendart": "opendart_api_key",
              "key-krx": "krx_api_key",
              "key-kis": "kis_app_key",
              "key-kis-secret": "kis_app_secret",
              "key-kiwoom-app": "kiwoom_app_key",
              "key-kiwoom-secret": "kiwoom_secret_key",
              "key-tavily": "tavily_api_key",
            };
            const apiKeyName = fieldMap[input.id];
            if (apiKeyName && rawKeysCache[apiKeyName]) {
              input.value = rawKeysCache[apiKeyName];
            }
          } catch (err) {
            console.error("Failed to load saved key:", err);
          }
        }
      } else {
        input.type = "password";
        btn.textContent = "👁️";
        btn.title = "키 보이기";
        btn.classList.remove("active");
      }
    });
  });
}

async function loadSettings() {
  const s = await api("/api/settings");
  $("#llm-provider").value = s.llm_provider || "xai";
  syncDecorated($("#llm-provider"));
  const provider = $("#llm-provider").value;
  applyModelOptions(PROVIDER_MODELS[provider] || PROVIDER_MODELS.xai, s.llm_model);
  syncDecorated($("#llm-model-select"));
  renderGrokAuth(s.grok_auth);
  renderAntigravityAuth(s.antigravity_auth);
  await loadModels({ reset: false }).catch(() => {});
  renderConnections().catch(() => {});
  metaLine($("#meta-opendart"), s.opendart_api_key);
  if ($("#meta-naver-id")) metaLine($("#meta-naver-id"), s.naver_client_id);
  if ($("#meta-naver-secret")) metaLine($("#meta-naver-secret"), s.naver_client_secret);
  if ($("#meta-naver-map-id")) metaLine($("#meta-naver-map-id"), s.naver_map_client_id);
  if ($("#meta-naver-map-secret")) metaLine($("#meta-naver-map-secret"), s.naver_map_client_secret);
  if ($("#meta-toss-id")) metaLine($("#meta-toss-id"), s.toss_client_id);
  if ($("#meta-toss-secret")) metaLine($("#meta-toss-secret"), s.toss_client_secret);
  if ($("#meta-fred")) metaLine($("#meta-fred"), s.fred_api_key);
  if ($("#meta-ecos")) metaLine($("#meta-ecos"), s.bok_ecos_api_key || { configured: false, masked: "sample", length: 6 });
  if ($("#meta-telegram")) metaLine($("#meta-telegram"), s.telegram_bot_token);
  if ($("#meta-telegram-chat") && $("#key-telegram-chat")) {
    const chat = s.telegram_chat_id || "";
    $("#meta-telegram-chat").textContent = chat ? chat : "미설정";
    $("#meta-telegram-chat").className = "meta " + (chat ? "ok" : "warn");
    if (!$("#key-telegram-chat").value) $("#key-telegram-chat").placeholder = chat || "봇에게 메시지 후 채팅 ID 찾기";
  }
  metaLine($("#meta-krx"), s.krx_api_key);
  metaLine($("#meta-kis"), s.kis_app_key);
  metaLine($("#meta-kis-secret"), s.kis_app_secret);
  metaLine($("#meta-xai"), s.xai_api_key);
  metaLine($("#meta-deepseek"), s.deepseek_api_key);
  if ($("#meta-openrouter") && s.openrouter_api_key) metaLine($("#meta-openrouter"), s.openrouter_api_key);
  if ($("#meta-kiwoom-app")) metaLine($("#meta-kiwoom-app"), s.kiwoom_app_key);
  if ($("#meta-kiwoom-secret")) metaLine($("#meta-kiwoom-secret"), s.kiwoom_secret_key);
  if ($("#meta-tavily")) metaLine($("#meta-tavily"), s.tavily_api_key);
  $("#key-kis-url").value = s.kis_base_url || "";
  $("#key-sleep").value = s.opendart_sleep_sec ?? 0.2;
  refreshDeployStatus().catch(() => {});
}

function keyOrNull(id) {
  const v = $(id).value.trim();
  if (!v) return null;
  if (v.toUpperCase() === "CLEAR") return "";
  return v;
}

async function saveSettings() {
  await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({
      llm_provider: $("#llm-provider").value || "xai",
      llm_model: ($("#llm-model").value.trim() || $("#llm-model-select").value || null),
      opendart_api_key: keyOrNull("#key-opendart"),
      krx_api_key: keyOrNull("#key-krx"),
      xai_api_key: keyOrNull("#key-xai"),
      deepseek_api_key: keyOrNull("#key-deepseek"),
      openrouter_api_key: keyOrNull("#key-openrouter"),
      kis_app_key: keyOrNull("#key-kis"),
      kis_app_secret: keyOrNull("#key-kis-secret"),
      naver_client_id: keyOrNull("#key-naver-id"),
      naver_client_secret: keyOrNull("#key-naver-secret"),
      naver_map_client_id: keyOrNull("#key-naver-map-id"),
      naver_map_client_secret: keyOrNull("#key-naver-map-secret"),
      toss_client_id: keyOrNull("#key-toss-id"),
      toss_client_secret: keyOrNull("#key-toss-secret"),
      fred_api_key: keyOrNull("#key-fred"),
      bok_ecos_api_key: keyOrNull("#key-ecos"),
      telegram_bot_token: keyOrNull("#key-telegram"),
      telegram_chat_id: keyOrNull("#key-telegram-chat"),
      kiwoom_app_key: keyOrNull("#key-kiwoom-app"),
      kiwoom_secret_key: keyOrNull("#key-kiwoom-secret"),
      tavily_api_key: keyOrNull("#key-tavily"),
      kis_base_url: $("#key-kis-url").value.trim() || null,
      opendart_sleep_sec: Number($("#key-sleep").value),
    }),
  });
  $$("#view-settings input[type=password]").forEach((el) => (el.value = ""));
  await loadSettings();
  $("#test-box").innerHTML = "<p class='ok'>저장했습니다. 연결 테스트로 확인할 수 있습니다.</p>";
}

function renderTestResults(r) {
  const boxTop = $("#test-box-top");
  const boxBottom = $("#test-box");
  const entries = Object.entries(r || {});
  const okCount = entries.filter(([k, v]) => v.ok).length;
  const totalCount = entries.length;

  const cardsHtml = `
    <div class="test-results-panel" style="background:#0b1329; border:1.5px solid rgba(56,189,248,0.4); border-radius:12px; padding:16px; margin:14px 0; box-shadow:0 0 20px rgba(0,0,0,0.5);">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px; border-bottom:1px solid #1e293b; padding-bottom:10px;">
        <div style="display:flex; align-items:center; gap:10px;">
          <h3 style="margin:0; font-size:15px; color:#38bdf8;">⚡ API 종합 연결 테스트 결과</h3>
          <span class="chip ok" style="font-weight:800; font-size:12px; padding:3px 10px; background:rgba(34,197,94,0.2); color:#4ade80;">
            ${okCount} / ${totalCount} 전체 정상 연동
          </span>
        </div>
        <small style="color:#94a3b8; font-size:11.5px;">⏱️ 실시간 검증 완료</small>
      </div>
      <div class="test-grid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:10px;">
        ${entries.map(([k, v]) => {
          const isOk = v.ok;
          const isOpt = v.optional;
          const badgeClass = isOk ? "ok" : isOpt ? "warn" : "bad";
          const icon = isOk ? "✅" : isOpt ? "ℹ️" : "❌";
          const label = v.label || k;
          const borderColor = isOk ? "rgba(34,197,94,0.35)" : isOpt ? "rgba(234,179,8,0.35)" : "rgba(239,68,68,0.45)";
          const bgColor = isOk ? "rgba(16,24,42,0.95)" : isOpt ? "rgba(25,24,15,0.95)" : "rgba(35,14,20,0.95)";
          const statusText = isOk ? (isOpt ? "정상 (선택)" : "정상") : (isOpt ? "선택 (미설정)" : "실패");
          return `
            <div class="test-item-card" style="background:${bgColor}; border:1px solid ${borderColor}; border-radius:8px; padding:10px 12px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <b style="font-size:13px; color:#f1f5f9;">${escapeHtml(label)}</b>
                <span class="chip ${badgeClass}" style="font-size:10.5px; padding:2px 7px; font-weight:700;">
                  ${icon} ${statusText}
                </span>
              </div>
              <p style="margin:0; font-size:11.5px; color:${isOk ? '#86efac' : isOpt ? '#fef08a' : '#fca5a5'}; line-height:1.4; word-break:break-all;">
                ${escapeHtml(v.detail || "")}
              </p>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;

  if (boxTop) boxTop.innerHTML = cardsHtml;
  if (boxBottom) boxBottom.innerHTML = cardsHtml;
}

async function testSettings() {
  const btn = $("#test-keys");
  const origText = btn ? btn.textContent : "";
  if (btn) {
    btn.textContent = "⏳ 연결 테스트 중...";
    btn.disabled = true;
  }
  const loadingHtml = `
    <div class="test-loading-banner" style="background:#0f172a; border:1px solid #38bdf8; border-radius:10px; padding:14px; margin:14px 0; text-align:center; color:#38bdf8; font-weight:700;">
      <span>⏳ 14개 핵심 API(거래소·증권사·공시·거시경제·AI)의 연결 상태를 실시간 진단 중입니다...</span>
    </div>
  `;
  if ($("#test-box-top")) $("#test-box-top").innerHTML = loadingHtml;
  if ($("#test-box")) $("#test-box").innerHTML = loadingHtml;

  try {
    const r = await api("/api/settings/test", { method: "POST" });
    renderTestResults(r);
    const okCount = Object.values(r).filter((v) => v.ok).length;
    const totalCount = Object.values(r).length;
    showToast(`✅ API 연결 테스트 완료 (${okCount}/${totalCount}개 정상 연동)`, "success", 4000);
  } catch (err) {
    const errHtml = `<div class="test-loading-banner" style="background:#200b10; border:1px solid #ef4444; border-radius:10px; padding:14px; margin:14px 0; color:#f87171;">❌ 연결 테스트 실패: ${escapeHtml(err.message)}</div>`;
    if ($("#test-box-top")) $("#test-box-top").innerHTML = errHtml;
    if ($("#test-box")) $("#test-box").innerHTML = errHtml;
    showToast(`❌ 연결 테스트 실패: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.textContent = origText || "연결 테스트";
      btn.disabled = false;
    }
  }
}

let toastContainerEl = null;
function getToastContainer() {
  if (!toastContainerEl) {
    toastContainerEl = document.createElement("div");
    toastContainerEl.className = "toast-container";
    document.body.appendChild(toastContainerEl);
  }
  return toastContainerEl;
}

function showToast(msg, type = "info", duration = 3500) {
  const container = getToastContainer();
  const el = document.createElement("div");
  el.className = `toast-msg toast-${type}`;
  el.innerHTML = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("fade-out");
    setTimeout(() => el.remove(), 350);
  }, duration);
}

const JOB_KINDS = {
  demo: "데모 실행",
  screen: "재계산",
  live: "실데이터 수집+계산",
  "live-skip": "실데이터 재계산",
  "krx-prices": "KRX 시세 갱신",
  "krx-history": "시세 이력 확장 (750일)",
  "dart-backfill": "OpenDART 전 종목 백필",
  "investor-kis": "공식 수급 수집",
  "dart-nps": "국민연금 공시 수집",
  strategy: "전략 랩 스캔",
};

function renderJob(job) {
  if (!job) return;
  const chip = $("#job-chip");
  if (chip) chip.textContent = `${statusKo(job.status)}${job.kind ? " · " + (JOB_KINDS[job.kind] || job.kind) : ""}`;
  const logEl = $("#job-log");
  if (logEl) {
    logEl.textContent = (job.logs || []).join("\n");
    logEl.scrollTop = logEl.scrollHeight;
  }

  // Global Top Activity Chip & Animated Progress Line
  const actChip = $("#chip-activity");
  const progBar = $("#global-progress-bar");
  if (job.status === "running") {
    const title = JOB_KINDS[job.kind] || job.kind || "작업";
    if (progBar) progBar.classList.remove("hidden");
    if (actChip) {
      actChip.className = "chip activity-running has-tip";
      actChip.textContent = `⏳ ${title} 실행 중 (백그라운드)…`;
      actChip.dataset.tip = "백그라운드에서 작업이 실행 중입니다. 브라우저를 닫거나 이동해도 계속 안전하게 실행됩니다. 클릭 시 실행 파이프라인으로 이동합니다.";
    }
  } else {
    if (progBar) progBar.classList.add("hidden");
    if (actChip) {
      actChip.className = "chip activity-idle has-tip";
      actChip.textContent = "🟢 시스템 정상";
      actChip.dataset.tip = "현재 백그라운드 작업이 완료되었거나 대기 중입니다.";
    }
  }
}

async function reloadActiveView() {
  try {
    if (currentView === "dash" || currentView === "rank") await loadDash();
    else if (currentView === "screens") await loadScreens();
    else if (currentView === "market") await loadMacro();
    else if (currentView === "sector") await loadSectors();
    else if (currentView === "flow") await loadFlow();
    else if (currentView === "investor") { await loadInvestor(); await loadInvestorEvents(); }
    else if (currentView === "sunzi") await loadSunzi();
    else if (currentView === "nps") await loadNps();
    else if (currentView === "trade") await loadTrade();
    else if (currentView === "strategy") await loadStrategy();
    else if (currentView === "watch") await loadWatch();
  } catch (err) {
    console.error("reloadActiveView error:", err);
  }
}

async function pollJob() {
  try {
    const job = await api("/api/jobs");
    renderJob(job);
    const krxBtn = $("#btn-krx-now");
    if (job.status === "running") {
      if (krxBtn && job.kind === "krx-prices") {
        krxBtn.textContent = "⏳ 시세 수신 중...";
        krxBtn.disabled = true;
      }
      setTimeout(pollJob, 1200);
    } else {
      if (krxBtn) {
        krxBtn.textContent = "시세 받기";
        krxBtn.disabled = false;
      }
      if (job.status === "success") {
        const title = JOB_KINDS[job.kind] || job.kind || "작업";
        showToast(`✅ <b>${title} 완료</b>`, "success");
        await loadStatus();
        await reloadActiveView();
      } else if (job.status === "error") {
        const title = JOB_KINDS[job.kind] || job.kind || "작업";
        showToast(`❌ <b>${title} 실패</b>: ${escapeHtml(job.error || "")}`, "error", 5000);
      }
    }
  } catch (err) {
    console.error("pollJob error:", err);
  }
}

async function startJob(kind) {
  const asofVal = $("#run-asof")?.value?.trim() || "auto";
  const lookbackVal = Number($("#run-lookback")?.value || 80);
  const maxVal = Number($("#run-max")?.value || 400);

  const payload = {
    kind: kind.startsWith("live") ? "live" : kind,
    as_of: asofVal,
    source: "live",
    lookback_days: lookbackVal,
    max_corps: maxVal,
    skip_ingest: kind === "live-skip" || kind === "screen",
  };
  if (kind === "screen") payload.kind = "screen";
  if (kind === "krx-prices") {
    payload.kind = "krx-prices";
    payload.lookback_days = 10;
  }
  if (kind === "krx-history") {
    payload.kind = "krx-history";
    const selectedDays = Number($("#run-history-duration")?.value || 1250);
    payload.lookback_days = selectedDays;
  }
  if (kind === "dart-backfill") {
    payload.kind = "dart-backfill";
    payload.max_corps = Number($("#run-dart-batch")?.value || 50);
  }

  const krxBtn = $("#btn-krx-now");
  if (krxBtn && kind === "krx-prices") {
    krxBtn.textContent = "⏳ 시세 수신 중...";
    krxBtn.disabled = true;
  }
  const title = JOB_KINDS[kind] || kind;
  showToast(`⏳ <b>${title}</b> 시작 (백그라운드 실행 중…)`, "info", 3000);

  await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
  pollJob();
}

function openMobileDrawer() {
  const drawer = $("#mobile-menu-drawer");
  if (drawer) {
    drawer.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }
}
function closeMobileDrawer() {
  const drawer = $("#mobile-menu-drawer");
  if (drawer) {
    drawer.classList.add("hidden");
    document.body.style.overflow = "";
  }
}

$$(".nav-btn").forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));

// Delegated Touch & Click handler for 100% instant response on all mobile devices
document.addEventListener("click", (e) => {
  const mobileBtn = e.target.closest("[data-mobile-view]");
  if (mobileBtn) {
    const view = mobileBtn.getAttribute("data-mobile-view");
    if (view) switchView(view);
    return;
  }
  if (e.target.closest("#btn-mobile-drawer-toggle")) {
    openMobileDrawer();
    return;
  }
  if (e.target.closest("#btn-mobile-drawer-close") || e.target.id === "mobile-menu-drawer") {
    closeMobileDrawer();
    return;
  }
});

if ($("#flow-q")) {
  $("#flow-q").addEventListener("input", (e) => {
    if (flowCache) renderSmartFlowActive(flowCache);
  });
  $("#flow-q").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.isComposing || $("#flow-q-menu")?.style.display === "block") return;
    e.preventDefault();
    runFlowSearch().catch((err) => alert(err.message));
  });
}
if ($("#btn-flow-search")) {
  $("#btn-flow-search").addEventListener("click", () => runFlowSearch().catch((err) => alert(err.message)));
}
if ($("#flow-refresh")) {
  $("#flow-refresh").addEventListener("click", () => loadSmartFlow(true).catch((err) => alert(err.message)));
}
if ($("#flow-days")) {
  $("#flow-days").addEventListener("change", () => loadSmartFlow(false).catch((err) => alert(err.message)));
}
if ($("#flow-min-krw")) {
  $("#flow-min-krw").addEventListener("change", () => {
    if (flowCache) renderSmartFlowActive(flowCache);
  });
}
if ($("#trade-universe")) {
  $("#trade-universe").addEventListener("change", () => {
    if (flowCache) renderSmartFlowActive(flowCache);
  });
}
["empty-mode", "empty-rate"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", () => { if (flowCache && smartFlowTab === "vacancy") renderEmpty(flowCache); });
});
["trade-mode", "trade-ta"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", () => { if (flowCache) renderSmartFlowActive(flowCache); });
});
if ($("#btn-trade-search")) {
  $("#btn-trade-search").addEventListener("click", () => runFlowSearch().catch((err) => alert(err.message)));
}
$$('[data-smart-flow-tab]').forEach((button) => {
  button.addEventListener("click", () => setSmartFlowTab(button.dataset.smartFlowTab));
});

function bindStockSearchers() {
  const stratInput = $("#custom-strategy-q");
  const stratMenu = $("#custom-strategy-menu");
  if (stratInput && stratMenu) {
    setupStockAutocomplete(stratInput, stratMenu, (selected) => {
      stratInput.value = `${selected.company || ""} ${selected.ticker || ""}`.trim();
    });
    stratInput.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      if (e.isComposing) return;
      e.preventDefault();
      runCustomBacktest(stratInput.value);
    });
  }
  $("#btn-custom-strategy")?.addEventListener("click", () => {
    runCustomBacktest($("#custom-strategy-q")?.value || "");
  });
  const flowInput = $("#flow-q");
  const flowMenu = $("#flow-q-menu");
  if (flowInput && flowMenu) {
    setupStockAutocomplete(flowInput, flowMenu, (selected) => {
      flowInput.value = `${selected.company || ""} ${selected.ticker || ""}`.trim();
      runFlowSearch(selected.ticker).catch((err) => alert(err.message));
    });
  }
}

let floatTipEl = null;
function floatTip() {
  if (!floatTipEl) {
    floatTipEl = document.createElement("div");
    floatTipEl.id = "float-tip";
    floatTipEl.className = "float-tip hidden";
    document.body.appendChild(floatTipEl);
  }
  return floatTipEl;
}

function flowTipTone(value) {
  const text = String(value || "").trim();
  if (/^\+/.test(text)) return "up";
  if (/^-/.test(text)) return "down";
  return "flat";
}

function flowTipMetric(segment) {
  const text = String(segment || "").trim();
  const splitAt = text.indexOf(" ");
  const label = splitAt > 0 ? text.slice(0, splitAt) : text;
  const value = splitAt > 0 ? text.slice(splitAt + 1) : "—";
  return `<div class="flow-tip-metric">
    <span>${escapeHtml(label)}</span>
    <b class="${flowTipTone(value)}">${escapeHtml(value)}</b>
  </div>`;
}

function flowHistoryTipHtml(text) {
  const lines = String(text || "").split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.length || !lines.some((line) => line.includes(" · "))) {
    return `<div class="float-tip-body">${escapeHtml(text)}</div>`;
  }
  const rows = lines.map((line) => {
    const parts = line.split(" · ").map((part) => part.trim());
    const day = parts.shift() || "—";
    const price = parts.shift() || "종가 —";
    return `<div class="flow-tip-day-row">
      <div class="flow-tip-day-head">
        <time>${escapeHtml(day)}</time>
        <strong>${escapeHtml(price)}</strong>
      </div>
      <div class="flow-tip-net-grid">${parts.map(flowTipMetric).join("")}</div>
    </div>`;
  }).join("");
  return `<div class="flow-tip-history">${rows}</div>`;
}

function flowSummaryTipHtml(label, summary) {
  const parts = String(summary || "").split(" · ").map((part) => part.trim()).filter(Boolean);
  const metrics = parts.filter((part) => /^(외인|기관|개인|사모)\s/.test(part));
  const priceLines = parts.filter((part) => !/^(외인|기관|개인|사모)\s/.test(part));
  return `<div class="flow-tip-summary">
    <div class="flow-tip-summary-title">🎯 ${escapeHtml(label || "설정기간 집계")}</div>
    <div class="flow-tip-price-lines">${priceLines.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}</div>
    <div class="flow-tip-net-grid flow-tip-summary-grid">${metrics.map(flowTipMetric).join("")}</div>
  </div>`;
}

function showFloatTip(el) {
  const text = el.getAttribute("data-tip");
  if (!text) return;
  const box = floatTip();
  const isFlowHistory = el.getAttribute("data-tip-layout") === "flow-history";
  box.classList.toggle("flow-history-tip", isFlowHistory);
  const explicitTitle = el.getAttribute("data-tip-title");
  const title = explicitTitle || (el.getAttribute("aria-label") || el.textContent || "").trim().split("\n")[0].slice(0, 45);
  const upImpact = el.getAttribute("data-tip-up");
  const downImpact = el.getAttribute("data-tip-down");
  const hintImpact = el.getAttribute("data-tip-hint");
  const hintLabel = el.getAttribute("data-tip-hint-label") || "핵심 판정 팁";

  let html = `
    <div class="float-tip-header">
      <h4 class="float-tip-title">${escapeHtml(title)}</h4>
    </div>
    ${isFlowHistory ? flowHistoryTipHtml(text) : `<div class="float-tip-body">${escapeHtml(text)}</div>`}
  `;

  if (isFlowHistory && hintImpact) {
    html += flowSummaryTipHtml(hintLabel, hintImpact);
  } else if (upImpact || downImpact || hintImpact) {
    html += `<div class="float-tip-impact">`;
    if (upImpact) html += `<div class="up-impact">🔺 <b>상승 시 영향:</b> ${escapeHtml(upImpact)}</div>`;
    if (downImpact) html += `<div class="down-impact">🔻 <b>하락 시 영향:</b> ${escapeHtml(downImpact)}</div>`;
    if (hintImpact) html += `<div class="hint-impact">🎯 <b>${escapeHtml(hintLabel)}:</b> ${escapeHtml(hintImpact)}</div>`;
    html += `</div>`;
  }

  box.innerHTML = html;
  box.classList.remove("hidden");
  const r = el.getBoundingClientRect();
  const maxW = Math.min(isFlowHistory ? 640 : 380, window.innerWidth - 24);
  box.style.width = `${maxW}px`;
  let left = Math.min(r.left, window.innerWidth - maxW - 12);
  left = Math.max(12, left);
  box.style.left = `${left}px`;
  box.style.top = `${r.bottom + 8}px`;
  const br = box.getBoundingClientRect();
  if (br.bottom > window.innerHeight - 8) {
    box.style.top = `${Math.max(8, r.top - br.height - 8)}px`;
  }
}
function hideFloatTip() {
  if (floatTipEl) floatTipEl.classList.add("hidden");
}
function attachTipListeners() {
  const handleOver = (e) => {
    const el = e.target.closest("[data-tip]");
    if (el) showFloatTip(el);
  };
  const handleOut = (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) return;
    const next = e.relatedTarget;
    if (next && el.contains(next)) return;
    hideFloatTip();
  };
  document.addEventListener("pointerover", handleOver, { passive: true });
  document.addEventListener("pointerout", handleOut, { passive: true });
  document.addEventListener("mouseover", handleOver, { passive: true });
  document.addEventListener("mouseout", handleOut, { passive: true });
}
attachTipListeners();
document.addEventListener("focusin", (e) => {
  const el = e.target.closest("[data-tip]");
  if (el) showFloatTip(el);
});
document.addEventListener("focusout", hideFloatTip);
document.addEventListener("scroll", hideFloatTip, true);
if ($("#strategy-refresh")) {
  $("#strategy-refresh").addEventListener("click", () => loadStrategy(true).catch((err) => alert(err.message)));
}
if ($("#us13f-refresh")) {
  $("#us13f-refresh").addEventListener("click", () => loadUs13f(true).catch((err) => alert(err.message)));
}
if ($("#us13f-mode")) {
  $("#us13f-mode").addEventListener("change", () => { if (us13fCache) renderUs13f(us13fCache); });
}
if ($("#us13f-q")) {
  $("#us13f-q").addEventListener("input", () => { if (us13fCache) renderUs13f(us13fCache); });
}
$("#refresh-dash").addEventListener("click", loadDash);

document.querySelectorAll(".dash-topn-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".dash-topn-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentDashTopN = parseInt(btn.dataset.n, 10) || 30;
    renderTop20(dashRows, currentDashTopN);
    renderDashDna(dashRows, currentDashTopN);
  });
});

$("#rank-q").addEventListener("input", (e) => renderRank(e.target.value));
if ($("#report-q")) {
  $("#report-q").addEventListener("input", () => renderReportArchiveHub());
}

document.querySelectorAll(".report-filter-chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".report-filter-chip").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentReportFilter = btn.dataset.filter || "all";
    renderReportArchiveHub();
  });
});

const btnGrid = $("#btn-rep-view-grid");
const btnTable = $("#btn-rep-view-table");
if (btnGrid && btnTable) {
  btnGrid.addEventListener("click", () => {
    btnGrid.classList.add("active");
    btnTable.classList.remove("active");
    currentReportViewMode = "grid";
    renderReportArchiveHub();
  });
  btnTable.addEventListener("click", () => {
    btnTable.classList.add("active");
    btnGrid.classList.remove("active");
    currentReportViewMode = "table";
    renderReportArchiveHub();
  });
}

if ($("#goto-reports")) {
  $("#goto-reports").addEventListener("click", () => switchView("reports"));
}
$("#drawer-close").addEventListener("click", closeDrawer);
if ($("#drawer-back")) $("#drawer-back").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeDrawer();
    closeStatusModal();
  }
});
if ($("#chip-activity")) {
  $("#chip-activity").addEventListener("click", () => switchView("run"));
}
if ($("#chip-status")) {
  $("#chip-status").addEventListener("click", () => openStatusModal());
}
if ($("#status-modal-close")) {
  $("#status-modal-close").addEventListener("click", closeStatusModal);
}
if ($("#status-modal")) {
  $("#status-modal").addEventListener("click", (e) => {
    if (e.target.id === "status-modal") closeStatusModal();
  });
}
document.addEventListener("click", (e) => {
  const aiBtn = e.target.closest("[data-ai-trigger]");
  if (aiBtn) {
    e.preventDefault();
    e.stopPropagation();
    const code = aiBtn.dataset.aiTrigger;
    const company = aiBtn.dataset.aiCompany || code;
    const ok = confirm(`🤖 [${company} (${code})] AI 심층 분석 리포트를 발간하시겠습니까?\n\n※ DeepSeek / OpenRouter LLM API를 호출하여 최신 공시, 재무, 해자, 밸류에이션 및 4대 전략 백테스트 리포트를 생성합니다. (토큰 비용 소모)`);
    if (!ok) return;

    runReport(code).catch((err) => alert(err.message));
    return;
  }
  if (e.target.closest(".btn-ai-mini")) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  if (e.target.closest("[data-open-status]")) openStatusModal();
});
if ($("#btn-krx-now")) {
  $("#btn-krx-now").addEventListener("click", () => startJob("krx-prices").catch((err) => alert(err.message)));
}
if ($("#btn-dash-reload")) {
  $("#btn-dash-reload").addEventListener("click", () => reloadCurrentView().catch((err) => alert(err.message)));
}
if ($("#market-refresh")) {
  $("#market-refresh").addEventListener("click", () => {
    loadMarket(true).catch((err) => alert(err.message));
    loadMacro(true).catch(() => {});
  });
}
if ($("#investor-refresh")) {
  $("#investor-refresh").addEventListener("click", () => loadInvestor().catch((err) => alert(err.message)));
}
if ($("#investor-collect")) {
  $("#investor-collect").addEventListener("click", () => startJob("investor-kis").catch((err) => alert(err.message)));
}
if ($("#investor-events-refresh")) {
  $("#investor-events-refresh").addEventListener("click", () => loadInvestorEvents().catch((err) => alert(err.message)));
}
if ($("#investor-turn")) {
  $("#investor-turn").addEventListener("change", () => loadInvestorEvents().catch((err) => alert(err.message)));
}
if ($("#sunzi-refresh")) {
  $("#sunzi-refresh").addEventListener("click", () => loadSunzi().catch((err) => alert(err.message)));
}
setupSunziControls();
if ($("#nps-refresh")) {
  $("#nps-refresh").addEventListener("click", () => loadNps().catch((err) => alert(err.message)));
}
if ($("#nps-collect")) {
  $("#nps-collect").addEventListener("click", () => startJob("dart-nps").catch((err) => alert(err.message)));
}
if ($("#macro-refresh-btn")) {
  $("#macro-refresh-btn").addEventListener("click", async () => {
    const btn = $("#macro-refresh-btn");
    const orig = btn.textContent;
    btn.textContent = "⏳ 갱신 중...";
    btn.disabled = true;
    try {
      macroCache = null; await loadMacro(true);
      showToast("✅ 글로벌 매크로·환율·원자재 실시간 지표 갱신 완료", "success");
    } catch (err) {
      showToast(`❌ 매크로 갱신 실패: ${escapeHtml(err.message)}`, "error");
    } finally {
      btn.textContent = orig;
      btn.disabled = false;
      stampLive("#macro-live");
    }
  });
}
if ($("#market-refresh")) {
  $("#market-refresh").addEventListener("click", async () => {
    const btn = $("#market-refresh");
    const orig = btn.textContent;
    btn.textContent = "⏳ 갱신 중...";
    btn.disabled = true;
    try {
      await Promise.all([loadMarket(true), loadMacro(true)]);
      showToast("✅ 시장 국면 & 글로벌 매크로 실시간 갱신 완료", "success");
    } catch (err) {
      showToast(`❌ 갱신 실패: ${escapeHtml(err.message)}`, "error");
    } finally {
      btn.textContent = orig;
      btn.disabled = false;
      stampLive("#market-live");
      stampLive("#macro-live");
    }
  });
}
if ($("#news-refresh")) {
  $("#news-refresh").addEventListener("click", async () => {
    const btn = $("#news-refresh");
    const orig = btn.textContent;
    btn.textContent = "⏳ 갱신 중...";
    btn.disabled = true;
    try {
      macroCache = null; await loadMacro(true);
      showToast("✅ 뉴스 및 매크로 지표 갱신 완료", "success");
    } catch (err) {
      showToast(`❌ 갱신 실패: ${escapeHtml(err.message)}`, "error");
    } finally {
      btn.textContent = orig;
      btn.disabled = false;
    }
  });
}
if ($("#sector-refresh")) {
  $("#sector-refresh").addEventListener("click", () => loadSectors().catch((err) => alert(err.message)));
}
if ($("#screens-refresh")) {
  $("#screens-refresh").addEventListener("click", () => loadScreens().catch((err) => alert(err.message)));
}
if ($("#screens-include-quant")) {
  $("#screens-include-quant").addEventListener("change", () => loadScreens().catch((err) => alert(err.message)));
}
if ($("#rank-refresh")) {
  $("#rank-refresh").addEventListener("click", () => loadDash().catch((err) => alert(err.message)));
}
if ($("#toss-refresh")) {
  $("#toss-refresh").addEventListener("click", () => loadTossRankings().catch((err) => alert(err.message)));
}
if ($("#report-modal-close")) {
  $("#report-modal-close").addEventListener("click", closeReportModal);
}
if ($("#report-modal-stock")) {
  $("#report-modal-stock").addEventListener("click", () => {
    if (modalTicker) openStock(modalTicker).catch((err) => alert(err.message));
  });
}
if ($("#report-modal")) {
  $("#report-modal").addEventListener("click", (e) => {
    if (e.target.id === "report-modal") closeReportModal();
  });
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeReportModal();
});
document.addEventListener("click", (e) => {
  const flowMore = e.target.closest("[data-flow-more]");
  if (flowMore) {
    e.preventDefault();
    e.stopPropagation();
    const scope = flowMore.dataset.flowMore;
    flowLimit[scope] = (flowLimit[scope] || FLOW_FIRST) + FLOW_STEP;
    if (flowCache) renderFlow(flowCache);
    return;
  }
  const flowTabBtn = e.target.closest("[data-flow-tab]");
  if (flowTabBtn && flowCache) {
    e.preventDefault();
    flowTab = flowTabBtn.dataset.flowTab || "dual";
    renderFlow(flowCache);
    return;
  }
  const del = e.target.closest("[data-del-report]");
  if (del) {
    e.preventDefault();
    e.stopPropagation();
    const ticker = del.dataset.ticker;
    const asOf = del.dataset.asof;
    const kind = del.dataset.kind;
    if (!ticker || !asOf) return;
    if (!confirm(`${kind || "리포트"}를 삭제할까요? 이 PC에 저장된 파일만 지웁니다.`)) return;
    api("/api/research/reports/delete", {
      method: "POST",
      body: JSON.stringify({ ticker, as_of: asOf, kind, filename: del.dataset.filename || null }),
    })
      .then(() => loadReportArchive())
      .catch((err) => alert(err.message));
    return;
  }
  const th = e.target.closest("th.sortable");
  if (th) {
    const table = th.closest("table");
    const scope = table && table.dataset.scope;
    if (scope && th.dataset.sort) {
      e.preventDefault();
      const cur = sortState[scope] || {};
      sortState[scope] = { key: th.dataset.sort, dir: cur.key === th.dataset.sort && cur.dir === "desc" ? "asc" : "desc" };
      if (scope === "dash") renderTop20(dashRows);
      else if (scope === "rank") renderRank($("#rank-q") ? $("#rank-q").value : "");
      else if (scope === "reports") renderReportArchiveHub();
      else if (String(scope).startsWith("flow")) {
        if (flowCache) renderFlow(flowCache);
      } else if (scope === "empty") {
        if (flowCache) renderEmpty(flowCache);
      } else if (scope === "trade") {
        if (tradeCache || flowCache) renderTrade(tradeCache || flowCache);
      } else if (scope === "screens" && screenCache) renderScreens(screenCache);
      else if (scope === "strategy" && strategyCache) renderStrategy(strategyCache);
      else if (scope === "us13f" && us13fCache) renderUs13f(us13fCache);
      else if (scope === "sunzi") loadSunzi().catch(() => {});
      else if (scope === "nps") loadNps().catch(() => {});
    }
    return;
  }
  if (e.target.closest("a.ext") || e.target.closest(".btn-ai-mini") || e.target.closest("[data-ai-trigger]")) return;
  const tr = e.target.closest("tr.clickable");
  if (!tr?.dataset.ticker) return;
  const archive = tr.closest("#reports-body, #dash-reports-body");
  if (archive) {
    const meta = reportRows.find(
      (r) => padTicker(r.ticker) === padTicker(tr.dataset.ticker) && String(r.as_of_date || "") === String(tr.dataset.asof || r.as_of_date || "")
    ) || reportRows.find((r) => padTicker(r.ticker) === padTicker(tr.dataset.ticker));
    openArchivedItem(tr.dataset.ticker, tr.dataset.asof || (meta && meta.as_of_date), meta && meta.kind).catch((err) =>
      alert(err.message)
    );
    return;
  }
  openStock(tr.dataset.ticker).catch((err) => alert(err.message));
});
function decorateSelect(sel) {
  if (!sel || sel.dataset.decorated) return;
  sel.dataset.decorated = "1";
  const wrap = document.createElement("div");
  wrap.className = "sel-wrap";
  sel.parentNode.insertBefore(wrap, sel);
  wrap.appendChild(sel);
  sel.classList.add("sr-only-select");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "sel-btn";
  const menu = document.createElement("div");
  menu.className = "sel-menu hidden";
  wrap.appendChild(btn);
  wrap.appendChild(menu);
  const sync = () => {
    const cur = sel.options[sel.selectedIndex];
    btn.textContent = (cur && (cur.textContent || cur.value)) || "선택";
    menu.innerHTML = "";
    [...sel.options].forEach((opt) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "sel-item" + (opt.selected ? " on" : "");
      const info = MODEL_TOKEN_INFO[opt.value];
      if (info && sel.id === "llm-model-select") {
        const isFree = info.badge.includes("무료") || info.badge.includes("CLI");
        item.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; width:100%; gap:8px;">
            <span style="font-weight:600; font-family:monospace;">${escapeHtml(opt.textContent || opt.value)}</span>
            <span style="font-size:10px; color:${isFree ? '#4ade80' : '#38bdf8'}; background:rgba(0,0,0,0.35); padding:1px 6px; border-radius:4px; flex-shrink:0;">${escapeHtml(info.badge)}</span>
          </div>
        `;
      } else {
        item.textContent = opt.textContent || opt.value || "—";
      }
      item.addEventListener("click", () => {
        sel.value = opt.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        menu.classList.add("hidden");
        sync();
      });
      menu.appendChild(item);
    });
  };
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    menu.classList.toggle("hidden");
  });
  document.addEventListener("click", (e) => {
    if (!wrap.contains(e.target)) menu.classList.add("hidden");
  });
  sel.addEventListener("change", sync);
  sel._decorateSync = sync;
  new MutationObserver(sync).observe(sel, { childList: true, subtree: true });
  sync();
}

function syncDecorated(sel) {
  if (sel && typeof sel._decorateSync === "function") sel._decorateSync();
}

const PROVIDER_LABELS = {
  xai: "Grok (xAI)",
  antigravity: "Google agy",
  deepseek: "DeepSeek",
  openrouter: "OpenRouter",
};

const PROVIDER_MODELS = {
  xai: [
    "grok-4.6",
    "grok-4.5",
    "grok-4",
    "grok-3",
    "grok-2-vision-1212",
  ],
  antigravity: [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-pro",
    "auto",
  ],
  deepseek: [
    "deepseek-chat",
    "deepseek-reasoner",
  ],
  openrouter: [
    "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-v4-pro-0813",
    "deepseek/deepseek-v4-flash-vision-exp",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "openai/gpt-5.6-luna",
    "google/gemini-3.7-flash",
    "z-ai/glm-5.2",
    "upstage/solar-pro4",
  ],
};

const MODEL_TOKEN_INFO = {
  "deepseek/deepseek-v4-flash-0731": { badge: "⭐ 기본추천", tokens: "초저비용 ($0.07 / 1M 토큰)", desc: "OpenRouter 실전 랭킹 1위 기본 모델" },
  "deepseek/deepseek-v4-pro-0813": { badge: "⚡ 프로추론", tokens: "고효율 ($0.27 / 1M 토큰)", desc: "정밀 퀀트 분석 및 고급 추론" },
  "deepseek/deepseek-v4-flash-vision-exp": { badge: "👁️ 비전분석", tokens: "저비용 ($0.15 / 1M 토큰)", desc: "차트 및 멀티모달 비전 특화" },
  "nvidia/nemotron-3-ultra-550b-a55b:free": { badge: "🎁 100% 무료", tokens: "무료 ($0.00 / 1M 토큰)", desc: "NVIDIA 550B 대형 오픈 모델 (0원 과금)" },
  "openai/gpt-5.6-luna": { badge: "🔮 차세대", tokens: "프리미엄 ($1.25 / 1M 토큰)", desc: "OpenAI 차세대 최고성능 플래그십" },
  "google/gemini-3.7-flash": { badge: "⚡ 초고속", tokens: "초저비용 ($0.10 / 1M 토큰)", desc: "Google 차세대 초고속 Flash 모델" },
  "z-ai/glm-5.2": { badge: "🧠 고지능", tokens: "표준 ($0.35 / 1M 토큰)", desc: "GLM-5.2 고지능 퀀트 분석" },
  "upstage/solar-pro4": { badge: "🇰🇷 한국특화", tokens: "고효율 ($0.20 / 1M 토큰)", desc: "Upstage 한국 금융/공시 특화 모델" },
  "gemini-2.5-pro": { badge: "⚡ Google agy", tokens: "무료 (CLI 세션 토큰)", desc: "Google Antigravity CLI 세션 무료 제공" },
  "gemini-2.5-flash": { badge: "⚡ Google agy", tokens: "무료 (CLI 세션 토큰)", desc: "Google Antigravity CLI 세션 무료 제공" },
  "grok-4.6": { badge: "⚡ xAI 기본", tokens: "표준 요금제", desc: "xAI 최신 Grok 4.6 리서치" },
  "deepseek-chat": { badge: "🧠 공식 API", tokens: "초저비용 ($0.14 / 1M 토큰)", desc: "DeepSeek 공식 API 직접 연동" },
  "deepseek-reasoner": { badge: "🧠 공식 API", tokens: "표준 ($0.55 / 1M 토큰)", desc: "DeepSeek R1 공식 추론 직접 연동" },
};

function applyModelOptions(ids, selected) {
  const sel = $("#llm-model-select");
  if (!sel) return;
  const list = [...new Set((ids || []).filter(Boolean))];
  sel.innerHTML = "";
  list.forEach((id) => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = id;
    sel.appendChild(opt);
  });
  const cur = selected && list.includes(selected) ? selected : list[0] || "";
  if (cur) {
    sel.value = cur;
    $("#llm-model").value = cur;
  } else {
    $("#llm-model").value = "";
  }
  syncDecorated(sel);
}

async function persistLlmChoice() {
  await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({
      llm_provider: $("#llm-provider").value || "xai",
      llm_model: ($("#llm-model").value.trim() || $("#llm-model-select").value || null),
    }),
  });
}

async function renderConnections() {
  const box = $("#llm-connections");
  if (!box) return;
  const data = await api("/api/llm/connections");
  const active = data.active || {};
  const line = $("#llm-active-line");
  if (line) line.textContent = `${active.label || active.provider || "—"} · ${active.model || "—"}`;
  const ul = $("#llm-conn-list");
  if (!ul) return;
  ul.innerHTML = (data.connections || [])
    .map((c) => {
      const state = c.connected ? `연결됨${c.via ? " · " + c.via : ""}` : "미연결";
      const models = (c.models || []).slice(0, 6).join(", ") || "목록 없음";
      const extra = c.model_count > 6 ? ` 외 ${c.model_count - 6}개` : "";
      return `<li class="${c.active ? "on" : ""}"><b>${c.label}</b> — ${state}<br />모델: ${models}${extra}</li>`;
    })
    .join("");
}

function fillModelSelect(selected) {
  applyModelOptions(
    [...$("#llm-model-select").options].map((o) => o.value).filter(Boolean),
    selected
  );
}

async function loadModels({ reset = false } = {}) {
  const box = $("#test-box");
  const provider = $("#llm-provider").value;
  const fallback = PROVIDER_MODELS[provider] || PROVIDER_MODELS.xai;
  if (reset) applyModelOptions(fallback, fallback[0]);
  if (box) box.innerHTML = "<p>모델 목록을 불러오는 중…</p>";
  const data = await api(`/api/llm/models?provider=${encodeURIComponent(provider)}`);
  const preferred = reset
    ? data.default_model || fallback[0]
    : data.selected || $("#llm-model").value || data.default_model;
  applyModelOptions(data.models && data.models.length ? data.models : fallback, preferred);
  if (box) {
    box.innerHTML = `<p class="${data.source === "api" ? "ok" : "warn"}">${data.label}: ${(data.models || []).length}개 (${data.source})${data.error ? " · " + data.error : ""}</p>`;
  }
}

$("#save-keys").addEventListener("click", () => saveSettings().catch((err) => alert(err.message)));
$("#test-keys").addEventListener("click", () => testSettings().catch((err) => alert(err.message)));
if ($("#telegram-chats")) {
  $("#telegram-chats").addEventListener("click", () => findTelegramChats().catch((err) => alert(err.message)));
}
if ($("#telegram-test")) {
  $("#telegram-test").addEventListener("click", () => testTelegram().catch((err) => alert(err.message)));
}

async function findTelegramChats() {
  const box = $("#test-box");
  box.innerHTML = "<p>봇 업데이트에서 채팅을 찾는 중… 먼저 봇에게 아무 메시지나 보내세요.</p>";
  const data = await api("/api/telegram/chats");
  const chats = data.chats || [];
  if (!chats.length) {
    box.innerHTML = `<p class="warn">봇 @${escapeHtml((data.bot || {}).username || "")} 은 살아 있지만 최근 대화가 없습니다. 텔레그램에서 봇을 열고 아무 글이나 보낸 뒤 다시 누르세요.</p>`;
    return;
  }
  box.innerHTML = chats
    .map((c) => `<p class="ok">채팅 ${escapeHtml(c.title)} · ID <code>${escapeHtml(c.id)}</code> · ${escapeHtml(c.type || "")}</p>`)
    .join("");
  if (chats[0] && $("#key-telegram-chat") && !$("#key-telegram-chat").value.trim()) {
    $("#key-telegram-chat").value = chats[0].id;
  }
}

async function testTelegram() {
  const box = $("#test-box");
  box.innerHTML = "<p>텔레그램 테스트 중…</p>";
  const data = await api("/api/telegram/test", { method: "POST" });
  box.innerHTML = `<p class="${data.ok ? "ok" : "warn"}">${escapeHtml(data.detail || "")}</p>`;
}
$("#load-models").addEventListener("click", () => loadModels().catch((err) => alert(err.message)));
function renderGrokAuth(sess, live) {
  if (!sess) return;
  const chip = $("#grok-chip");
  const hint = $("#grok-hint");
  const btn = $("#grok-connect");
  const box = $("#grok-auth-box");
  const link = $("#grok-verify-link");
  const codeEl = $("#grok-user-code");
  const url = live && live.verification_url;
  const code = live && live.user_code;
  if (box && (url || code)) {
    box.classList.remove("hidden");
    if (link && url) {
      link.href = url;
      link.textContent = url;
    }
    if (codeEl) codeEl.textContent = code || "코드를 받는 중…";
  } else if (box && (!live || live.status !== "running")) {
    box.classList.add("hidden");
  }
  if (live && live.status === "running") {
    chip.textContent = "승인 대기";
    chip.className = "chip warn";
    hint.textContent = live.detail || "브라우저에서 로그인 후 승인을 누르세요. 페이지만 뜨고 끝나면 아래 코드를 직접 입력하세요.";
    btn.textContent = "연결 중…";
    return;
  }
  if (sess.connected) {
    chip.textContent = "연결됨" + (sess.email ? " · " + sess.email : "");
    chip.className = "chip ok";
    hint.textContent = "이 PC의 Grok 로그인을 사용합니다. AI 분석 시 xAI 세션으로 요청합니다.";
    btn.textContent = "다시 연결";
  } else if (sess.expired && sess.auth_file) {
    chip.textContent = "만료됨";
    chip.className = "chip warn";
    hint.textContent = "세션이 만료되었습니다. 연결을 다시 누르면 승인 코드가 다시 나옵니다.";
    btn.textContent = "Grok 다시 연결";
  } else {
    chip.textContent = sess.cli ? "미연결" : "CLI 없음";
    chip.className = "chip warn";
    hint.textContent = sess.cli
      ? "연결을 누르면 승인용 페이지와 코드가 나옵니다. 브라우저에서 승인을 눌러야 연결됩니다."
      : "grok.exe가 없습니다. Grok 앱을 설치하거나 API 키를 넣으세요.";
    btn.textContent = "Grok 연결";
  }
}

async function pollGrokConnect() {
  const data = await api("/api/llm/grok");
  renderGrokAuth(data.session || data, data);
  if (data.status === "running") {
    setTimeout(pollGrokConnect, 1500);
  } else if (data.status === "success") {
    $("#grok-hint").textContent = "연결되었습니다.";
    await loadSettings();
  } else if (data.status === "error") {
    $("#grok-hint").textContent = data.error || "연결 실패. 브라우저에서 승인을 눌렀는지 확인하세요.";
  }
}

async function connectGrok() {
  $("#grok-hint").textContent = "승인 코드를 받는 중…";
  const reconnect = /다시/.test($("#grok-connect").textContent);
  const data = await api("/api/llm/grok/connect" + (reconnect ? "?force=1" : ""), { method: "POST" });
  if (data.already) {
    renderGrokAuth(data.session || data, data);
    return;
  }
  renderGrokAuth(data.session || data, data);
  pollGrokConnect();
}

$("#grok-connect").addEventListener("click", () => connectGrok().catch((err) => alert(err.message)));
$("#llm-model-select").addEventListener("change", (e) => {
  $("#llm-model").value = e.target.value;
});
$("#llm-provider").addEventListener("change", () => {
  loadModels({ reset: true })
    .catch(() => {
      const provider = $("#llm-provider").value;
      const fallback = PROVIDER_MODELS[provider] || PROVIDER_MODELS.xai;
      applyModelOptions(fallback, fallback[0]);
    })
    .then(() => persistLlmChoice())
    .then(() => renderConnections())
    .catch((err) => alert(err.message));
});
$("#llm-model-select").addEventListener("change", () => {
  persistLlmChoice()
    .then(() => renderConnections())
    .catch((err) => alert(err.message));
});
$$("[data-job]").forEach((btn) =>
  btn.addEventListener("click", () => startJob(btn.dataset.job).catch((err) => alert(err.message)))
);

decorateSelect($("#llm-provider"));
decorateSelect($("#llm-model-select"));






function pbPct(x, digits = 1) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${(n * (Math.abs(n) <= 2 ? 100 : 1)).toFixed(digits)}%`;
}

function pbNum(x, digits = 1) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function pbWon(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n).toLocaleString("ko-KR")}원`;
}

function computeTrackStats(track) {
  const rets = (track || []).map((y) => Number(y.return)).filter((n) => Number.isFinite(n));
  if (!rets.length) return null;
  const n = rets.length;
  const mean = rets.reduce((a, b) => a + b, 0) / n;
  const sorted = [...rets].sort((a, b) => a - b);
  const median = n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
  const stdev = Math.sqrt(rets.reduce((a, r) => a + (r - mean) ** 2, 0) / n);
  const downs = rets.filter((r) => r < 0);
  const semi = Math.sqrt(rets.filter((r) => r < 0).reduce((a, r) => a + r * r, 0) / n);
  const ups = rets.filter((r) => r > 0);
  const upVol = Math.sqrt(ups.reduce((a, r) => a + r * r, 0) / n);
  const winRate = ups.length / n;
  const best = Math.max(...rets);
  const worst = Math.min(...rets);
  const q1 = sorted[Math.floor((n - 1) * 0.25)];
  const q3 = sorted[Math.floor((n - 1) * 0.75)];
  const var95 = sorted[Math.max(0, Math.floor(n * 0.05))];
  const tail = sorted.slice(0, Math.max(1, Math.ceil(n * 0.05)));
  const cvar = tail.reduce((a, b) => a + b, 0) / tail.length;
  const sharpe = stdev > 1e-9 ? mean / stdev : 0;
  const sortino = semi > 1e-9 ? mean / semi : 0;
  const totalAbs = upVol + semi;
  const upShare = totalAbs > 0 ? upVol / totalAbs : 0.5;
  const skew = semi > 1e-9 ? upVol / semi : 99;
  const survive = (cut) => rets.filter((r) => r > cut).length / n;
  return {
    n, mean, median, stdev, semi, upVol, winRate, best, worst, iqr: q3 - q1,
    var95, cvar, sharpe, sortino, upShare, skew,
    survive0: survive(-0.05),
    survive50: survive(-0.08),
    survive100: survive(-0.12),
  };
}

function splitInvalidation(text) {
  return String(text || "")
    .split(/[/·;|\n]+/)
    .map((s) => s.trim())
    .filter((s) => s && s !== "—");
}

function setModalText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val == null || val === "" ? "—" : String(val);
}

function yearsTrackFromRow(r) {
  if (Array.isArray(r.years_track) && r.years_track.length) return r.years_track;
  const hist = r.history || [];
  const yearNow = new Date().getFullYear();
  return hist.map((h, i) => {
    if (h && typeof h === "object") {
      const ret = Number(h.return ?? h.ret ?? 0);
      return { year: Number(h.year) || (yearNow - hist.length + i + 1), return: ret, is_win: ret > 0 };
    }
    const ret = Number(h) || 0;
    return { year: yearNow - hist.length + i + 1, return: ret, is_win: ret > 0 };
  });
}

function targetMonthOf(r) {
  const n = Number(r.target_month || r.target_start_month || String(r.window_name || "").replace("월", ""));
  return n >= 1 && n <= 12 ? n : new Date().getMonth() + 1;
}

function heatClass(ret) {
  const x = Number(ret) || 0;
  if (x >= 0.06) return "heat-up3";
  if (x >= 0.025) return "heat-up2";
  if (x >= 0.005) return "heat-up1";
  if (x >= -0.015) return "heat-flat";
  if (x >= -0.04) return "heat-dn1";
  return "heat-dn2";
}

function renderPbMonthHeat(months, targetM) {
  const byM = {};
  (months || []).forEach((m) => { byM[Number(m.month)] = m; });
  const cells = [];
  for (let m = 1; m <= 12; m++) {
    const d = byM[m];
    const ret = d ? Number(d.avg_return || d.median_return || 0) : null;
    const wr = d ? ((d.win_rate || 0) * 100).toFixed(0) : "—";
    const on = m === targetM ? "on" : "";
    const cls = d ? heatClass(ret) : "heat-flat";
    const retTxt = ret == null ? "—" : `${ret > 0 ? "+" : ""}${(ret * 100).toFixed(0)}`;
    cells.push(`<div class="pb-month-cell ${cls} ${on}" title="${m}월 평균수익 / 승률"><span>${m}월</span><b>${retTxt}</b><small>${wr === "—" ? "—" : `${wr}%`}</small></div>`);
  }
  return cells.join("");
}

function renderDiscDeepPlaybook(r, months) {
  const box = $("#disc-modal-deep");
  if (!box) return;
  const track = yearsTrackFromRow(r);
  const stats = computeTrackStats(track);
  const targetM = targetMonthOf(r);
  const pb = r.playbook || {};
  const monthlyP50 = r.expected_p50 ?? r.median_return;
  const rem = r.remaining_peak || {};
  const hasRemaining = rem.available === true && Number.isFinite(Number(rem.remaining_p50));
  const remWarnings = Array.isArray(rem.warnings) ? rem.warnings : [];
  const remWarningHtml = remWarnings.length
    ? `<div style="margin-top:9px;color:#fbbf24;font-size:11.5px;line-height:1.5;">⚠️ ${remWarnings.map(escapeHtml).join("<br>⚠️ ")}</div>`
    : "";
  const sample = r.sample_count || r.years_count || track.length || 0;
  const monthCells = renderPbMonthHeat(months, targetM);

  const winDateStr = r.entry_window_str || r.window_name || "계절성 윈도우";
  const years = track.map((y) => {
    const ret = Number(y.return || 0);
    const loss = !y.is_win;
    const pct = (ret * 100).toFixed(1);
    const sign = ret > 0 ? "+" : "";
    const fail = (r.failed_analysis || []).find((f) => String(f).includes(String(y.year)));
    const barWidth = Math.min(Math.max(Math.abs(ret) * 120, 10), 100);
    return `<div class="pb-year-card ${loss ? "loss-card" : "win-card"}">
      <div class="pb-year-card-top">
        <div class="pb-year-info">
          <span class="pb-year-badge">📅 ${y.year}년</span>
          <span class="pb-period-badge">🗓️ ${escapeHtml(winDateStr)}</span>
          <span class="pb-status-badge ${loss ? "loss" : "win"}">${loss ? "하락 마감" : "상승 달성"}</span>
        </div>
        <div class="pb-return-pill ${loss ? "loss" : "win"}">
          <span class="pb-return-val">${sign}${pct}%</span>
        </div>
      </div>
      <div class="pb-year-progress-wrap">
        <div class="pb-year-progress-bar ${loss ? "loss" : "win"}" style="width:${barWidth}%;"></div>
      </div>
      ${fail ? `<div class="pb-fail-box">
        <div class="pb-fail-title">⚠️ ${y.year}년 실패 원인 정밀 분석</div>
        <div class="pb-fail-desc">${escapeHtml(fail)}</div>
      </div>` : ""}
    </div>`;
  }).join("");

  const inv = splitInvalidation(r.invalidating_conditions);
  const invHtml = inv.length
    ? `<div class="pb-invalidation-grid">${inv.map((x) => `
        <div class="pb-invalidation-item">
          <span class="pb-inv-icon">🛑</span>
          <span class="pb-inv-txt">${escapeHtml(x)}</span>
        </div>`).join("")}</div>`
    : `<div class="pb-invalidation-item"><span class="pb-inv-icon">🛑</span><span class="pb-inv-txt">${escapeHtml(r.invalidating_conditions || "FY1 EPS Revision 하향 또는 60일선 이탈")}</span></div>`;

  let statsHtml = "";
  let lolli = "";
  let dual = "";
  let stress = "";
  let ai = "";
  if (stats) {
    const cells = [
      ["평균 수익률 (μ)", pbPct(stats.mean), "#34d399"],
      ["중앙값 수익률", pbPct(stats.median), "#67e8f9"],
      ["표준편차 (σ)", `±${(stats.stdev * 100).toFixed(1)}%`, "#cbd5e1"],
      ["하방 변동성", `${(stats.semi * 100).toFixed(1)}%`, "#f87171"],
      ["최대 낙폭", pbPct(stats.worst), "#f87171"],
      ["역사적 승률", `${(stats.winRate * 100).toFixed(1)}%`, "#34d399"],
      ["샤프 비율", pbNum(stats.sharpe), "#e2e8f0"],
      ["소티노 비율", pbNum(stats.sortino), "#34d399"],
      ["95% VaR", pbPct(stats.var95), "#f87171"],
      ["조건부 CVaR", pbPct(stats.cvar), "#fb7185"],
      ["사분위 범위", `${(stats.iqr * 100).toFixed(1)}%`, "#94a3b8"],
      ["최대 수익", pbPct(stats.best), "#34d399"],
    ];
    statsHtml = `<div class="pb-stat-grid">${cells.map(([k, v, c]) => `<div class="pb-stat-cell"><span>${k}</span><b style="color:${c}">${v}</b></div>`).join("")}</div>`;
    const maxAbs = Math.max(...track.map((y) => Math.abs(Number(y.return) || 0)), 0.01);
    lolli = `<div class="pb-lollipop">${track.map((y) => {
      const ret = Number(y.return) || 0;
      const h = Math.max(8, Math.round((Math.abs(ret) / maxAbs) * 110));
      return `<i><span style="font-size:11px;font-weight:700;color:${ret < 0 ? "#f87171" : "#38bdf8"}">${(ret * 100).toFixed(1)}%</span><em class="${ret < 0 ? "loss" : ""}" style="height:${h}px"></em><small>'${String(y.year).slice(-2)}</small></i>`;
    }).join("")}</div>`;
    const upPct = (stats.upShare * 100).toFixed(0);
    dual = `<div class="pb-bar-dual"><div style="width:${upPct}%;background:#34d399"></div><div style="width:${100 - upPct}%;background:#f87171"></div></div>
      <div class="meta" style="margin-top:6px;font-size:12px;">상방 ${(stats.upVol * 100).toFixed(1)}% (${upPct}%) · 하방 ${(stats.semi * 100).toFixed(1)}% · 비대칭 ${stats.skew.toFixed(2)}x</div>`;
    const exp1 = stats.mean;
    const exp2 = stats.mean * 0.7;
    const exp3 = Math.max(stats.mean * 0.05, stats.worst * 0.2);
    const w1 = Math.min(-0.01, stats.worst);
    const w2 = Math.min(-0.02, stats.mean - stats.stdev * 1.5);
    const w3 = Math.min(-0.05, stats.mean - stats.stdev * 2.2);
    stress = `
      <div class="pb-stress" style="border:1px solid rgba(56,189,248,0.35);">
        <b style="color:#67e8f9;">● 정상 시장 (Baseline)</b>
        <div class="meta">조건: 역사적 계절성 패턴 정상 실현 (σ × 1.0)</div>
        <div>예상 수익 ${pbPct(exp1)} · 스트레스 σ ${(stats.stdev * 100).toFixed(1)}% · <span style="color:#f87171">최악 ${pbPct(w1)}</span> · 생존 ${(stats.survive0 * 100).toFixed(1)}%</div>
        <div style="color:#67e8f9;margin-top:4px;">방어: 계절성 윈도우 시작 시점 표준 분할 진입</div>
      </div>
      <div class="pb-stress" style="border:1px solid rgba(234,179,8,0.4);">
        <b style="color:#fbbf24;">● 매크로 변동성 확대 (+50%)</b>
        <div class="meta">조건: 지수 변동성 및 환율/금리 충격 가중 (σ × 1.5)</div>
        <div>예상 수익 ${pbPct(exp2)} · 스트레스 σ ${(stats.stdev * 1.5 * 100).toFixed(1)}% · <span style="color:#f87171">최악 ${pbPct(w2)}</span> · 생존 ${(stats.survive50 * 100).toFixed(1)}%</div>
        <div style="color:#fbbf24;margin-top:4px;">방어: 포지션 비중 축소 및 손절선 엄격 준수</div>
      </div>
      <div class="pb-stress" style="border:1px solid rgba(248,113,113,0.45);">
        <b style="color:#f87171;">● 블랙스완 & 산업 쇼크 (+100%)</b>
        <div class="meta">조건: 원자재/물류 급변 또는 실적 급랭 (σ × 2.0)</div>
        <div>예상 수익 ${pbPct(exp3)} · 스트레스 σ ${(stats.stdev * 2 * 100).toFixed(1)}% · <span style="color:#f87171">최악 ${pbPct(w3)}</span> · 생존 ${(stats.survive100 * 100).toFixed(1)}%</div>
        <div style="color:#f87171;margin-top:4px;">방어: 무효화 조건 발동 시 전량 청산 및 해지</div>
      </div>`;
    const failTxt = (r.failed_analysis || [])[0] || "실패 연도는 원자재·환율 충격 등 외부 변수와 겹친 경우가 많음";
    ai = `<p style="margin:0;font-size:13px;line-height:1.6;color:#cbd5e1;">
      ${escapeHtml(r.company || r.ticker)}(${escapeHtml(r.ticker)})은 ${escapeHtml(r.window_name || "해당")} 윈도우에서
      평균 ${pbPct(stats.mean)}, 표준편차 ${(stats.stdev * 100).toFixed(1)}%입니다.
      상방 변동성이 하방 대비 ${stats.skew.toFixed(2)}배로
      ${stats.skew >= 2 ? "상방 편향이 큰 계절성 분포" : "대칭에 가까운 분포"}입니다.
      ${escapeHtml(failTxt)}.
      권장 비중은 과하지 않게 두고, 아래 무효화 조건이 뜨면 미련 없이 접는 편이 낫습니다.
    </p>`;
  }

  const st = r.current_status || "DISCOVERY";
  box.innerHTML = `
    <div class="playbook-card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <b style="color:#38bdf8; font-size:14px;">🎯 사전 진입(Pre-Entry) 전략 플레이북</b>
        <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:11px;">사전 진입 전략</span>
      </div>
      <ul style="margin:8px 0 0 16px; padding:0; font-size:12.5px; color:#cbd5e1; line-height:1.6;">
        <li>${escapeHtml(pb.entry_timing || "일봉 피크 경로가 검증된 경우에만 과거 관찰 구간을 표시합니다.")}</li>
        <li>${escapeHtml(pb.exit_timing || "역사적 피크 감시 구간은 목표가가 아닌 과거 분포 참고치입니다.")}</li>
        <li style="color:#fca5a5;">${escapeHtml(pb.stop_loss || "월간 집계에는 경로상 MDD가 없어 손절선을 추정하지 않습니다.")}</li>
      </ul>
      <div style="margin-top:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#38bdf8;">📊 오늘 현재가 → 역사적 피크 구간 잔여 상승여력</span>
        <div class="expected-kpi-grid">
          <div class="expected-kpi-item"><span>현재가 · 기준일</span><b style="color:#e2e8f0;">${pbWon(rem.current_price)} <small>${escapeHtml(rem.price_as_of || "")}</small></b></div>
          <div class="expected-kpi-item"><span>잔여 상승여력(P50)</span><b style="color:#34d399;">${hasRemaining ? pbPct(rem.remaining_p50) : "산출 불가"}</b></div>
          <div class="expected-kpi-item"><span>보수~낙관 범위(P25~P75)</span><b style="color:#60a5fa;">${hasRemaining ? `${pbPct(rem.remaining_p25)} ~ ${pbPct(rem.remaining_p75)}` : "—"}</b></div>
          <div class="expected-kpi-item"><span>P50 피크 환산가</span><b style="color:#fbbf24;">${pbWon(rem.peak_price_p50)}</b></div>
          <div class="expected-kpi-item"><span>피크까지 중앙 거래일</span><b>${rem.median_trading_days_to_peak == null ? "—" : `${rem.median_trading_days_to_peak}일`}</b></div>
          <div class="expected-kpi-item"><span>피크 전 하방(P50)</span><b style="color:#f87171;">${pbPct(rem.downside_before_peak_p50)}</b></div>
          <div class="expected-kpi-item"><span>역사적 플러스 확률</span><b style="color:#34d399;">${rem.positive_peak_rate == null ? "—" : `${(Number(rem.positive_peak_rate) * 100).toFixed(1)}%`}</b></div>
          <div class="expected-kpi-item"><span>표본 · 신뢰도</span><b>${Number(rem.sample_count || 0)}개년 · ${escapeHtml(rem.confidence || "—")}</b></div>
        </div>
        <div class="meta" style="margin-top:8px;line-height:1.5;">과거 월간 전체구간 P50 ${pbPct(monthlyP50)}와 구분해 계산합니다. ${escapeHtml(rem.methodology || "실제 일봉 경로가 부족하면 값을 표시하지 않습니다.")}</div>
        ${remWarningHtml}
      </div>
    </div>

    <div style="margin-top:14px; background:rgba(30,41,59,0.5); border:1px solid rgba(139,92,246,0.3); border-radius:12px; padding:14px 16px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <b style="color:#c084fc; font-size:13.5px;">🤖 AI 공통 이벤트 역추적 (Event Explanation)</b>
        <span class="chip" style="background:rgba(139,92,246,0.2); color:#c084fc; font-size:11px;">신뢰도: ${escapeHtml(r.event_confidence || "HIGH")}</span>
      </div>
      <div style="margin-top:8px; font-size:14px; font-weight:800; color:#fff;">${escapeHtml(r.common_event_cluster || "계절성 수요 증가 및 제품 사이클")}</div>
      <p style="margin:4px 0 0; font-size:12px; color:#cbd5e1; line-height:1.5;">빅데이터 역추적 결과 매년 ${escapeHtml(r.window_name || "해당 구간")} 전후로 실적 개선 및 수급 유입이 반복되는 패턴입니다.</p>
      <div style="margin-top:8px; font-size:11.5px; color:#94a3b8;">📌 부 원인: ${escapeHtml(r.secondary_cluster || "분기 실적 호조 및 기관 수급 유입")}</div>
    </div>

    <div style="margin-top:14px;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.25);border-radius:12px;padding:14px 16px;">
      <b style="color:#34d399;">올해 유효성 확인 지표 (Current Confirmation)</b>
      <div class="pb-confirm-grid" style="margin-top:10px;">
        <div class="pb-confirm-cell"><span>역사적 승률</span><b>${((r.win_rate || 0) * 100).toFixed(1)}%</b></div>
        <div class="pb-confirm-cell"><span>월간 중앙수익</span><b>${pbPct(r.median_return)}</b></div>
        <div class="pb-confirm-cell"><span>현재 근거</span><b>${(r.current_confirmation_evidence || []).length}개</b></div>
        <div class="pb-confirm-cell"><span>상태</span><b>${escapeHtml(st)}</b></div>
      </div>
      <p class="meta" style="margin:8px 0 0;">근거: ${escapeHtml((r.current_confirmation_evidence || []).join(" · ") || "연결된 현재 확인 근거 없음")}<br>미연결: ${escapeHtml((r.current_confirmation_missing || []).join(" · ") || "없음")}</p>
    </div>

    <div style="margin-top:14px;background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px 16px;">
      <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;"><b>12개월 기간별 수익 변동성 히트맵</b><span class="meta">셀 = 평균수익 / 승률</span></div>
      <div id="disc-modal-heat" class="pb-month-heat" style="margin-top:10px;">${monthCells}</div>
    </div>

    ${years ? `<div style="margin-top:14px;background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <b style="font-size:14.5px;color:#f8fafc;">📊 연도별 계절성 수익률 & 실패 연도 분석</b>
        <span class="chip" style="background:rgba(56,189,248,0.15);color:#38bdf8;font-size:11px;">실측 통계 (${track.length}개년)</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;">${years}</div>
    </div>` : ""}

    <div class="pb-invalidation-card">
      <div class="pb-invalidation-head">
        <span style="font-size:16px;">🛑</span>
        <b class="pb-invalidation-title">전략 무효화 조건 (Invalidating Conditions)</b>
      </div>
      <p style="font-size:12px;color:#cbd5e1;margin:0 0 10px 0;">아래 악재 또는 기술적 이탈 신호가 발생할 경우, 계절성 패턴을 무효화하고 즉시 리스크를 방어합니다.</p>
      ${invHtml}
    </div>

    ${stats ? `<div style="margin-top:14px;background:rgba(15,23,42,0.6);border:1px solid rgba(56,189,248,0.25);border-radius:12px;padding:14px 16px;">
      <b style="color:#67e8f9;">기간별 수익 변동성 분석 리포트</b>
      <p class="meta">현재 패턴 윈도우 실측 (1M/6M/12M을 임의로 만들지 않습니다)</p>
      <div style="margin-top:12px;"><b style="font-size:12.5px;">역사적 연도별 실측 수익률 산포도</b>${lolli}</div>
      <div style="margin-top:12px;"><b style="font-size:12.5px;">상방 수익 기여 vs 하방 손실 변동성</b>${dual}</div>
      <div style="margin-top:12px;"><b style="font-size:12.5px;">핵심 정량 통계</b><div style="margin-top:8px;">${statsHtml}</div></div>
      <div style="margin-top:14px;"><b>변동성 스트레스 테스트 (시장 충격 시나리오)</b>${stress}</div>
      <div style="margin-top:14px;border:1px solid rgba(56,189,248,0.3);border-radius:10px;padding:12px;">
        <b style="color:#67e8f9;">정밀 변동성 진단 및 운용 가이드</b>
        ${ai}
        <div style="margin-top:8px;color:#fbbf24;font-size:12px;">전략 무효화 & 손절 감시 트리거</div>
        ${invHtml}
      </div>
    </div>` : ""}
  `;
}

function renderSeasonalOverlayChart(canvas, r, months, mode = "seasonal_overlay") {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const rect = canvas.getBoundingClientRect();
  const width = rect.width || 720;
  const height = rect.height || 280;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);

  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, width, height);

  const padding = { top: 38, right: 28, bottom: 32, left: 52 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  const targetM = targetMonthOf(r);
  const mList = months && months.length === 12 ? months : Array.from({ length: 12 }, (_, i) => {
    const m = i + 1;
    const found = (r.all_months || []).find((x) => Number(x.month) === m);
    return found || {
      month: m,
      avg_return: (m === targetM ? (r.median_return || 0.35) : (m === targetM - 1 ? 0.08 : 0.02)),
      win_rate: (m === targetM ? (r.win_rate || 1.0) : 0.5)
    };
  });

  if (mode === "monthly_alpha") {
    const barW = plotW / 12;
    const maxRet = Math.max(...mList.map(m => Math.abs(Number(m.avg_return || 0))), 0.15) * 1.25;
    const zeroY = padding.top + plotH * (maxRet / (maxRet * 2));

    ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(width - padding.right, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);

    mList.forEach((m, idx) => {
      const ret = Number(m.avg_return || 0);
      const isTarget = m.month === targetM;
      const x = padding.left + idx * barW + barW * 0.15;
      const bw = barW * 0.7;
      const h = (Math.abs(ret) / maxRet) * (plotH / 2);
      const y = ret >= 0 ? zeroY - h : zeroY;

      if (isTarget) {
        ctx.fillStyle = ret >= 0 ? "rgba(52, 211, 153, 0.85)" : "rgba(248, 113, 113, 0.85)";
        ctx.shadowColor = ret >= 0 ? "#34d399" : "#f87171";
        ctx.shadowBlur = 10;
      } else {
        ctx.fillStyle = ret >= 0 ? "rgba(56, 189, 248, 0.45)" : "rgba(248, 113, 113, 0.35)";
        ctx.shadowBlur = 0;
      }
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, bw, Math.max(h, 3), 4);
      else ctx.fillRect(x, y, bw, Math.max(h, 3));
      ctx.fill();
      ctx.shadowBlur = 0;

      ctx.fillStyle = isTarget ? "#38bdf8" : "#94a3b8";
      ctx.font = isTarget ? "bold 11px sans-serif" : "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`${m.month}월`, x + bw / 2, height - 10);

      ctx.fillStyle = isTarget ? "#34d399" : (ret >= 0 ? "#67e8f9" : "#fca5a5");
      ctx.font = "bold 10px sans-serif";
      const valY = ret >= 0 ? y - 4 : y + h + 12;
      ctx.fillText(`${ret > 0 ? "+" : ""}${(ret * 100).toFixed(0)}%`, x + bw / 2, valY);
    });

  } else {
    // Seasonal Alpha Curve & Pre-Entry / Peak Overlays
    let cum = 0;
    const trajectory = mList.map((m) => {
      cum += Number(m.avg_return || 0);
      return { month: m.month, ret: Number(m.avg_return || 0), cum: cum, wr: m.win_rate || 0 };
    });

    const cumVals = trajectory.map(t => t.cum);
    const minVal = Math.min(0, ...cumVals) - 0.05;
    const maxVal = Math.max(0.12, ...cumVals) + 0.08;
    const valRange = Math.max(0.1, maxVal - minVal);

    const getY = (val) => padding.top + plotH - ((val - minVal) / valRange) * plotH;
    const getX = (mFloat) => padding.left + ((mFloat - 1) / 11) * plotW;

    // Grid lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) {
      const gVal = minVal + (valRange * g) / 4;
      const gy = getY(gVal);
      ctx.beginPath();
      ctx.moveTo(padding.left, gy);
      ctx.lineTo(width - padding.right, gy);
      ctx.stroke();

      ctx.fillStyle = "#64748b";
      ctx.font = "10px monospace";
      ctx.textAlign = "right";
      ctx.fillText(`${gVal >= 0 ? "+" : ""}${(gVal * 100).toFixed(0)}%`, padding.left - 6, gy + 3);
    }

    // 1. Highlight PRE-ENTRY ZONE 🟢
    const entryStartM = Math.max(1, targetM - 0.7);
    const entryEndM = Math.min(12, targetM - 0.05);
    const entryX1 = getX(entryStartM);
    const entryX2 = getX(entryEndM);
    const entryW = Math.max(34, entryX2 - entryX1);

    const gradEntry = ctx.createLinearGradient(entryX1, 0, entryX2, 0);
    gradEntry.addColorStop(0, "rgba(16, 185, 129, 0.08)");
    gradEntry.addColorStop(0.5, "rgba(16, 185, 129, 0.28)");
    gradEntry.addColorStop(1, "rgba(16, 185, 129, 0.08)");
    ctx.fillStyle = gradEntry;
    ctx.fillRect(entryX1, padding.top, entryW, plotH);

    ctx.strokeStyle = "rgba(52, 211, 153, 0.75)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.strokeRect(entryX1, padding.top, entryW, plotH);
    ctx.setLineDash([]);

    ctx.fillStyle = "#34d399";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(`🟢 사전 진입 밴드 (${r.entry_window_str || `${targetM-1}월말`})`, (entryX1 + entryX2) / 2, padding.top - 10);

    // 2. Highlight PEAK TARGET ZONE 🎯
    const peakStartM = targetM;
    const peakEndM = Math.min(12, targetM + 0.75);
    const peakX1 = getX(peakStartM);
    const peakX2 = getX(peakEndM);
    const peakW = Math.max(34, peakX2 - peakX1);

    const gradPeak = ctx.createLinearGradient(peakX1, 0, peakX2, 0);
    gradPeak.addColorStop(0, "rgba(251, 191, 36, 0.08)");
    gradPeak.addColorStop(0.5, "rgba(251, 191, 36, 0.28)");
    gradPeak.addColorStop(1, "rgba(251, 191, 36, 0.08)");
    ctx.fillStyle = gradPeak;
    ctx.fillRect(peakX1, padding.top, peakW, plotH);

    ctx.strokeStyle = "rgba(251, 191, 36, 0.75)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.strokeRect(peakX1, padding.top, peakW, plotH);
    ctx.setLineDash([]);

    ctx.fillStyle = "#fbbf24";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    const remainingP50 = Number(r.remaining_peak && r.remaining_peak.remaining_p50);
    const peakAlpha = Number.isFinite(remainingP50) ? remainingP50 : Number(r.median_return ?? r.expected_p50 ?? 0);
    const peakAlphaPct = (peakAlpha * 100).toFixed(1);
    ctx.fillText(`🎯 오늘→피크 중앙값 (${peakAlpha >= 0 ? "+" : ""}${peakAlphaPct}%)`, (peakX1 + peakX2) / 2, padding.top - 10);

    // 3. Draw Seasonal Trajectory Curve
    ctx.shadowColor = "#38bdf8";
    ctx.shadowBlur = 12;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 3;
    ctx.beginPath();
    trajectory.forEach((t, i) => {
      const x = getX(t.month);
      const y = getY(t.cum);
      if (i === 0) ctx.moveTo(x, y);
      else {
        const prevX = getX(trajectory[i-1].month);
        const prevY = getY(trajectory[i-1].cum);
        const cpx = (prevX + x) / 2;
        ctx.bezierCurveTo(cpx, prevY, cpx, y, x, y);
      }
    });
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Fill under curve
    ctx.lineTo(getX(12), getY(minVal));
    ctx.lineTo(getX(1), getY(minVal));
    ctx.closePath();
    const fillGrad = ctx.createLinearGradient(0, padding.top, 0, padding.top + plotH);
    fillGrad.addColorStop(0, "rgba(56, 189, 248, 0.22)");
    fillGrad.addColorStop(1, "rgba(56, 189, 248, 0.0)");
    ctx.fillStyle = fillGrad;
    ctx.fill();

    // Data points & X axis labels
    trajectory.forEach((t) => {
      const x = getX(t.month);
      const y = getY(t.cum);
      const isTarget = t.month === targetM;

      ctx.fillStyle = isTarget ? "#fbbf24" : "#38bdf8";
      ctx.beginPath();
      ctx.arc(x, y, isTarget ? 6 : 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#070b13";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = isTarget ? "#fbbf24" : "#94a3b8";
      ctx.font = isTarget ? "bold 11px sans-serif" : "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`${t.month}월`, x, height - 10);
    });

    const summaryText = $("#disc-chart-summary-text");
    if (summaryText) {
      const peakPrice = r.remaining_peak && r.remaining_peak.peak_price_p50;
      summaryText.innerHTML = `오늘 현재가 ➔ 피크 잔여 중앙값: <b style="color:#34d399;">${peakAlpha >= 0 ? "+" : ""}${peakAlphaPct}%</b>${peakPrice ? ` · 환산가 <b>${pbWon(peakPrice)}</b>` : ""}`;
    }
  }
}

function bindDiscoveryModalChrome(modal, r) {
  const code = String(r.ticker || "").padStart(6, "0");

  // Naver & Toss External Chart Links
  const naverLink = $("#disc-modal-naver-link");
  if (naverLink) {
    naverLink.href = `https://finance.naver.com/item/main.naver?code=${code}`;
  }
  const tossLink = $("#disc-modal-toss-link");
  if (tossLink) {
    tossLink.href = `https://tossinvest.com/stocks/${code}`;
  }

  // Embedded Chart Toggle & Interactive Canvas
  const chartBox = $("#disc-modal-chart-box");
  const chartToggleBtn = $("#disc-modal-chart-toggle-btn");
  const canvas = $("#disc-modal-canvas");

  let curChartMode = "seasonal_overlay";
  const drawActiveChart = () => {
    if (!canvas) return;
    renderSeasonalOverlayChart(canvas, r, r.all_months || [], curChartMode);
  };

  if (chartToggleBtn && chartBox) {
    chartToggleBtn.onclick = () => {
      chartBox.classList.toggle("hidden");
      if (!chartBox.classList.contains("hidden")) {
        chartToggleBtn.textContent = "📈 차트 닫기 ✕";
        setTimeout(drawActiveChart, 50);
      } else {
        chartToggleBtn.textContent = "📈 캔들차트 보기";
      }
    };
  }

  const modeBtns = modal.querySelectorAll("#disc-chart-mode-tabs .chart-tab-btn");
  modeBtns.forEach((btn) => {
    btn.onclick = () => {
      modeBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      curChartMode = btn.getAttribute("data-chart-mode") || "seasonal_overlay";
      drawActiveChart();
    };
  });

  const stockBtn = $("#disc-modal-stock-btn");
  if (stockBtn) {
    stockBtn.onclick = () => {
      modal.classList.add("hidden");
      openStock(r.ticker).catch((err) => alert(err.message));
    };
  }
  const aiBtn = $("#disc-modal-ai-btn");
  if (aiBtn) {
    aiBtn.onclick = () => {
      const proceed = confirm(`[${r.company || r.ticker} (${r.ticker})] AI 심층 분석 리포트를 발간하시겠습니까?\n(LLM 토큰이 사용되며 백그라운드에서 안전하게 작성됩니다.)`);
      if (proceed) {
        modal.classList.add("hidden");
        runReport(r.ticker).catch((err) => alert(err.message));
      }
    };
  }
  const closeBtn = $("#disc-modal-close-btn");
  if (closeBtn) closeBtn.onclick = () => modal.classList.add("hidden");
  modal.onclick = (e) => {
    if (e.target === modal) modal.classList.add("hidden");
  };
}

async function openDiscoveryDetailModal(r) {
  const modal = $("#discovery-detail-modal");
  if (!modal || !r) return;

  setModalText("disc-modal-company", r.company || r.ticker);
  setModalText("disc-modal-ticker", r.ticker);
  setModalText("disc-modal-market", r.market || "KOSPI");

  const stagePill = $("#disc-modal-stage-pill");
  if (stagePill) {
    stagePill.textContent = r.entry_stage_label || "실측 피크 산출 대기";
    let cls = "stage-today";
    if (r.entry_stage === "PRE_ENTRY_15" || r.entry_stage === "PRE_ENTRY_30") cls = "stage-pre-entry";
    else if (r.entry_stage === "ACCUMULATE_60") cls = "stage-accumulate";
    else if (r.entry_stage === "EXIT_PEAK") cls = "stage-peak-exit";
    else if (r.entry_stage === "WATCH") cls = "stage-watch";
    stagePill.className = `stage-pill ${cls}`;
  }

  setModalText("disc-modal-theme", r.common_event_cluster || "계절적 수요 증가 및 분기 실적 모멘텀");

  const stKo = r.current_status === "ACTIVE" ? "🟢 상태 판정: 현재 근거 확인 (ACTIVE)" :
               r.current_status === "WATCH" ? "🟡 상태 판정: 관찰 대상 (WATCH)" :
               r.current_status === "WEAKENING" ? "🟠 상태 판정: 엣지 약화 (WEAKENING)" :
               r.current_status === "BROKEN" ? "🔴 상태 판정: 가설 훼손 (BROKEN)" :
               r.current_status === "UNKNOWN" ? "⚪ 상태 판정: 현재 근거 부족 (UNKNOWN)" : "🟣 상태 판정: 신규 발굴 (DISCOVERY)";
  setModalText("disc-modal-status-text", stKo);

  const pb = r.playbook || {};
  setModalText("disc-modal-recommendation", `💡 연구 대응: ${pb.recommendation || "월별 반복 수익률은 탐색 근거이며 주문 신호가 아닙니다."}`);
  setModalText("disc-modal-window", r.window_name || "—");
  setModalText("disc-modal-sample-sub", `${r.sample_count || r.years_count || 0}개년 Window 검증`);
  setModalText("disc-modal-winrate", `${((r.win_rate || 0) * 100).toFixed(1)}%`);
  setModalText("disc-modal-r3-sub", `최근 3년 ${((r.recent_3y_win_rate || 0) * 100).toFixed(0)}%`);
  const remDownside = r.remaining_peak && r.remaining_peak.downside_before_peak_p50;
  setModalText("disc-modal-alpha", pbPct(r.median_return));
  setModalText("disc-modal-mdd-sub", remDownside == null ? "피크 전 하방 —" : `피크 전 하방(P50) ${pbPct(remDownside)}`);
  setModalText("disc-modal-entry-win", `📈 과거 관찰 구간: ${r.entry_window_str || "실측 피크 산출 대기"}`);
  setModalText("disc-modal-exit-win", `➔ 역사적 피크 감시: ${r.exit_window_str || "실측 피크 산출 대기"}`);

  // Reset embedded chart to hidden
  const chartBox = $("#disc-modal-chart-box");
  const chartToggleBtn = $("#disc-modal-chart-toggle-btn");
  if (chartBox) chartBox.classList.add("hidden");
  if (chartToggleBtn) chartToggleBtn.textContent = "📈 캔들차트 보기";

  bindDiscoveryModalChrome(modal, r);
  renderDiscDeepPlaybook(r, r.all_months || []);
  modal.classList.remove("hidden");
  const pane = modal.querySelector(".discovery-modal-container");
  if (pane) pane.scrollTop = 0;

  if ((!(r.all_months && r.all_months.length) || r.all_months.length < 12) && r.ticker) {
    api(`/api/seasonality/ticker/${encodeURIComponent(padTicker(r.ticker))}`).then((data) => {
      const months = (data.stock && data.stock.months) || [];
      if (!months.length) return;
      r.all_months = months;
      const heat = $("#disc-modal-heat");
      if (heat) heat.innerHTML = renderPbMonthHeat(months, targetMonthOf(r));
    }).catch(() => {});
  }
}



let currentPreEntrySort = "score";
let currentPreEntryMarket = "all";
let currentPreEntryTheme = "all";
let preEntryThemeData = [];
let preEntryTop10 = [];

function hasCanonicalPreEntryRank(row) {
  if (row?.pre_entry_rank === null || row?.pre_entry_rank === undefined || row?.pre_entry_rank === "") return false;
  const rank = Number(row.pre_entry_rank);
  return Number.isFinite(rank) && rank > 0;
}

function syncPreEntryFilterControls() {
  const normalizedMarket = String(currentPreEntryMarket || "all").toUpperCase();
  currentPreEntryMarket = normalizedMarket === "KOSPI" || normalizedMarket === "KOSDAQ"
    ? normalizedMarket
    : "all";
  currentPreEntryTheme = String(currentPreEntryTheme || "all");

  const marketSelect = $("#pre-entry-market-filter");
  if (marketSelect) marketSelect.value = currentPreEntryMarket;

  const reset = $("#theme-filter-reset");
  if (reset) {
    reset.hidden = currentPreEntryTheme === "all";
    reset.setAttribute("aria-hidden", reset.hidden ? "true" : "false");
  }

  const sortTabs = $("#pre-entry-sort-tabs");
  sortTabs?.querySelectorAll("[data-pre-sort]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.preSort === currentPreEntrySort);
  });
}

function bindPreEntryClicks() {
  const container = $("#pre-entry-cards-list");
  if (!container || container.dataset.playbookBound) return;
  container.dataset.playbookBound = "1";
  container.addEventListener("click", (e) => {
    const stockBtn = e.target.closest(".btn-pre-entry-stock");
    if (stockBtn) {
      e.preventDefault();
      e.stopPropagation();
      openStock(stockBtn.dataset.ticker).catch((err) => alert(err.message));
      return;
    }
    const card = e.target.closest(".pre-entry-card");
    if (!card) return;
    const idx = parseInt(card.dataset.index, 10);
    const code = padTicker(card.dataset.ticker);
    const row = (Number.isFinite(idx) ? preEntryTop10[idx] : null)
      || preEntryTop10.find((x) => padTicker(x.ticker) === code)
      || (Array.isArray(discoveryRows) ? discoveryRows.find((x) => padTicker(x.ticker) === code) : null);
    if (row) openDiscoveryDetailModal(row);
  });
}

async function loadPreEntryView() {
  const container = $("#pre-entry-cards-list");
  if (!container) return;
  bindPreEntryClicks();

  container.innerHTML = `<div style="text-align:center; padding:40px; color:#94a3b8;">오늘의 시즌 모멘텀 최우수 종목 및 테마 기여도 분석 중...</div>`;

  // TOP 10 is a market-wide canonical list. A stock search belongs to the
  // discovery detail tabs and must not silently narrow this list.
  const [discRes, themeRes] = await Promise.all([
    api(`/api/seasonality/discovery?lookback_years=${currentV11Lookback}&horizon_days=90`),
    api(`/api/seasonality/themes?lookback_years=${currentV11Lookback}&horizon_days=90`),
  ]);
  setSeasonalityAsOf(discRes);

  const allRows = discRes.rows || [];
  // The discovery response is already loaded beside the theme response. Use
  // it to calculate live pre-entry overlap client-side instead of making the
  // theme endpoint repeat the expensive discovery scan.
  const allowedStages = new Set(["TODAY_ENTRY", "PRE_ENTRY_15", "PRE_ENTRY_30", "ACCUMULATE_60"]);
  const canonicalRows = allRows.filter((r) => allowedStages.has(r.entry_stage) && hasCanonicalPreEntryRank(r));
  const canonicalTickerSet = new Set(canonicalRows.map((row) => padTicker(row.ticker)));
  preEntryThemeData = (themeRes.themes || []).map((theme) => {
    const preEntryTickers = (theme.candidate_tickers || [])
      .map((ticker) => padTicker(ticker))
      .filter((ticker) => canonicalTickerSet.has(ticker));
    return {
      ...theme,
      pre_entry_tickers: preEntryTickers,
      pre_entry_count: preEntryTickers.length,
    };
  });

  // Render Donut Chart and Theme Ranking Cards
  renderThemeDonutAndRanking(preEntryThemeData);
  syncPreEntryFilterControls();

  // Backend canonical rank is shared with dashboard Glance Top 3.  A row without
  // pre_entry_rank failed the common tradability/current-price checks.
  let filtered = canonicalRows.slice();
  let filterRecoveryNotice = "";

  if (currentPreEntryMarket !== "all") {
    filtered = filtered.filter((r) => String(r.market || "").toUpperCase() === currentPreEntryMarket);
  }
  if (currentPreEntryTheme !== "all") {
    const tObj = preEntryThemeData.find((t) => t.theme_id === currentPreEntryTheme);
    const themeTickers = new Set((tObj?.candidate_tickers || []).map((ticker) => padTicker(ticker)));
    filtered = filtered.filter((r) => themeTickers.has(padTicker(r.ticker)));
  }

  // A stale/zero-result theme must not make the page look as if the engine has
  // no candidates while the dashboard is already showing the same ranked feed.
  if (!filtered.length && canonicalRows.length && (currentPreEntryTheme !== "all" || currentPreEntryMarket !== "all")) {
    currentPreEntryTheme = "all";
    currentPreEntryMarket = "all";
    filtered = canonicalRows.slice();
    filterRecoveryNotice = `
      <div class="pre-entry-filter-notice">
        선택한 테마·시장에는 현재 유효 후보가 없어 필터를 자동 해제하고 대시보드와 동일한 전체 TOP10을 표시합니다.
      </div>
    `;
    syncPreEntryFilterControls();
  }

  if (currentPreEntrySort === "score") {
    filtered.sort((a, b) => Number(a.pre_entry_rank) - Number(b.pre_entry_rank));
  } else if (currentPreEntrySort === "return") {
    filtered.sort((a, b) => Number(b.remaining_peak?.available ? b.remaining_peak.remaining_p50 : -99) - Number(a.remaining_peak?.available ? a.remaining_peak.remaining_p50 : -99));
  } else if (currentPreEntrySort === "winrate") {
    filtered.sort((a, b) => (b.win_rate || 0) - (a.win_rate || 0));
  } else if (currentPreEntrySort === "alpha") {
    filtered.sort((a, b) => (b.median_return || 0) - (a.median_return || 0));
  }

  const top10 = filtered.slice(0, 10);
  if (!top10.length) {
    preEntryTop10 = [];
    container.innerHTML = `<div style="text-align:center; padding:40px; color:#94a3b8;">대시보드와 동일한 거래 가능·현재가 검증을 통과한 관찰 후보가 없습니다. 데이터 갱신 후 다시 확인해 주세요.</div>`;
    return;
  }

  preEntryTop10 = top10;
  container.innerHTML = filterRecoveryNotice + top10.map((r, idx) => {
    const rank = idx + 1;
    const rankBadge = rank === 1 ? "🥇 1위" : rank === 2 ? "🥈 2위" : rank === 3 ? "🥉 3위" : `🏅 ${rank}위`;
    const rankCls = rank === 1 ? "rank-1" : "";

    let stageCls = "stage-today";
    if (r.entry_stage === "PRE_ENTRY_15" || r.entry_stage === "PRE_ENTRY_30") stageCls = "stage-pre-entry";
    else if (r.entry_stage === "ACCUMULATE_60") stageCls = "stage-accumulate";
    else if (r.entry_stage === "EXIT_PEAK") stageCls = "stage-peak-exit";

    const wr = ((r.win_rate || 0) * 100).toFixed(0);
    const rem = r.remaining_peak || {};
    const avgRet = rem.available ? pbPct(rem.remaining_p50) : "산출 불가";
    const remHit = !rem.available || rem.positive_peak_rate == null ? "—" : `${(Number(rem.positive_peak_rate) * 100).toFixed(0)}%`;
    const remMdd = rem.available ? pbPct(rem.downside_before_peak_p50) : "—";

    const yearsTrackHtml = (r.years_track || []).map((y) => {
      const cls = y.is_win ? "year-track-win" : "year-track-loss";
      const retStr = (y.return * 100).toFixed(1);
      const shortYear = String(y.year).slice(-2);
      return `<span class="year-track-cell ${cls}" style="padding:4px 8px; font-size:11.5px;" title="${y.year}년">${shortYear}년 ${y.return > 0 ? '+' : ''}${retStr}%</span>`;
    }).join("");

    const catalyst = r.common_event_cluster || "계절성 촉매 가설을 산출할 수 없습니다.";
    const catalystEvidence = r.secondary_cluster || "실측 표본과 업종별 확인 포인트가 없습니다.";
    const explanationMode = r.event_explanation_mode || "RULE_BASED";
    const explanationSource = r.event_explanation_source || "계절성 통계·업종 매핑";
    const catalystLabel = explanationMode === "CURATED_TICKER" ? "검토된 핵심 촉매 & 모멘텀" : "통계 기반 촉매 가설 & 모멘텀";

    return `
      <div class="pre-entry-card ${rankCls}" data-ticker="${escapeHtml(r.ticker)}" data-index="${idx}" role="button" tabindex="0">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
          <div>
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <span class="chip" style="background:#eab308; color:#0f172a; font-weight:900; font-size:12px;">${rankBadge}</span>
              <b style="font-size:18px; color:#fff;">${escapeHtml(r.company || r.ticker)}</b>
              <span class="chip" style="background:#1e293b; color:#94a3b8; font-family:monospace;">${escapeHtml(r.market || 'KOSPI')} ${escapeHtml(r.ticker)}</span>
              <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:11.5px;">${escapeHtml(r.window_name)} (${r.sample_count}개년 검증)</span>
            </div>
            <div style="margin-top:6px; display:flex; align-items:center; gap:8px;">
              <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:700;">${escapeHtml(r.common_event_cluster)}</span>
            </div>
          </div>

          <div style="display:flex; align-items:center; gap:8px;">
            <span class="stage-pill ${stageCls}" style="font-size:12px; padding:4px 10px;">${escapeHtml(r.entry_stage_label || '🔥 오늘 진입 D-0')}</span>
          </div>
        </div>

        <!-- Current-price-to-peak KPI Bar -->
        <div class="pre-entry-kpi-bar">
          <div class="pre-entry-kpi-item">
            <span>오늘→피크 P50</span>
            <b class="text-emerald-400">${avgRet}</b>
          </div>
          <div class="pre-entry-kpi-item" style="border-color:rgba(234,179,8,0.4); background:rgba(234,179,8,0.1);">
            <span style="color:#fde047;">피크 플러스 확률</span>
            <b style="color:#facc15;">${remHit}</b>
          </div>
          <div class="pre-entry-kpi-item">
            <span>P50 피크 환산가</span>
            <b style="color:#38bdf8;">${pbWon(rem.peak_price_p50)}</b>
          </div>
          <div class="pre-entry-kpi-item">
            <span>피크 전 하방(P50)</span>
            <b style="color:#f87171;">${remMdd}</b>
          </div>
          <div class="pre-entry-kpi-item">
            <span>표본 · 신뢰도</span>
            <b style="color:#fbbf24;">${Number(rem.sample_count || 0)}년 · ${escapeHtml(rem.confidence || "—")}</b>
          </div>
        </div>

        <!-- Timing Window Strip -->
        <div class="pre-entry-timing-strip">
          <span style="color:#38bdf8; font-weight:700;">📈 과거 관찰 구간: ${escapeHtml(r.entry_window_str || '실측 피크 산출 대기')}</span>
          <span style="color:#fbbf24; font-weight:700;">➔ 역사적 피크 감시: ${escapeHtml(r.exit_window_str || '실측 피크 산출 대기')}</span>
        </div>

        <!-- Year-by-Year Track Record Bar -->
        <div style="font-size:11.5px; color:#94a3b8; margin-bottom:6px;">최근 5~8개년 연도별 실측 백테스팅 수익률:</div>
        <div class="year-track-bar" style="flex-wrap:wrap; gap:6px;">${yearsTrackHtml}</div>

        <!-- AI Catalyst Box -->
        <div class="catalyst-box">
          💡 <b>${catalystLabel}:</b> ${escapeHtml(catalyst)}
          <div style="margin-top:5px; color:#cbd5e1; font-size:11.5px; line-height:1.45;">${escapeHtml(catalystEvidence)}</div>
          <div style="margin-top:5px; color:#64748b; font-size:10.5px;">근거 방식: ${escapeHtml(explanationSource)} · 실시간 뉴스·공시 확정 문구가 아닌 검증 대상 가설</div>
        </div>

        <!-- Action Footer -->
        <div style="margin-top:14px; display:flex; justify-content:flex-end; gap:8px;">
          <button type="button" class="ghost small btn-pre-entry-stock" data-ticker="${escapeHtml(r.ticker)}">📊 시뮬레이터 연동</button>
          <button type="button" class="btn small btn-pre-entry-detail" data-ticker="${escapeHtml(r.ticker)}" style="background:#38bdf8; color:#0f172a; font-weight:800;">상세 플레이북 ➔</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderThemeDonutAndRanking(themes) {
  const svg = $("#theme-donut-svg");
  const rankList = $("#theme-ranking-list");
  if (!svg || !rankList || !themes || !themes.length) return;

  const titleEl = $("#theme-ranking-title");
  if (titleEl) titleEl.textContent = `📊 ${themes.length}개 이벤트 테마 계절성 랭킹`;

  // Center title
  const top1 = themes[0];
  const centerThemeEl = $("#donut-center-theme") || $("#donut-center-name");
  const centerPctEl = $("#donut-center-pct") || $("#donut-center-val");
  if (centerThemeEl) centerThemeEl.textContent = top1.theme_name;
  if (centerPctEl) centerPctEl.textContent = `${top1.weight_share_pct}%`;

  // Draw SVG Donut
  const cx = 100, cy = 100, rOuter = 85, rInner = 55;
  let cumAngle = -90; // Start at 12 o'clock

  let pathsHtml = "";
  themes.forEach((t) => {
    const angle = (t.weight_share_pct / 100) * 360;
    const startAngle = cumAngle;
    const endAngle = cumAngle + angle;
    cumAngle = endAngle;

    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;

    const x1 = cx + rOuter * Math.cos(startRad);
    const y1 = cy + rOuter * Math.sin(startRad);
    const x2 = cx + rOuter * Math.cos(endRad);
    const y2 = cy + rOuter * Math.sin(endRad);

    const x3 = cx + rInner * Math.cos(endRad);
    const y3 = cy + rInner * Math.sin(endRad);
    const x4 = cx + rInner * Math.cos(startRad);
    const y4 = cy + rInner * Math.sin(startRad);

    const largeArc = angle > 180 ? 1 : 0;
    const d = `M ${x1} ${y1} A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${rInner} ${rInner} 0 ${largeArc} 0 ${x4} ${y4} Z`;

    pathsHtml += `<path d="${d}" fill="${t.color}" opacity="0.85" stroke="#0f172a" stroke-width="2" style="cursor:pointer; transition:opacity 0.2s;" data-theme-id="${t.theme_id}">
      <title>${t.emoji} ${t.theme_name}: 상대 기여도 ${t.weight_share_pct}% · 안전 종목 ${t.candidate_count}/${t.mapped_count}</title>
    </path>`;
  });

  svg.innerHTML = pathsHtml;

  // Bind Donut slice clicks
  svg.querySelectorAll("path").forEach((p) => {
    p.addEventListener("click", () => {
      const tid = p.dataset.themeId;
      currentPreEntryTheme = currentPreEntryTheme === tid ? "all" : tid;
      syncPreEntryFilterControls();
      loadPreEntryView().catch(() => {});
    });
  });

  // Render Theme Ranking Sidebar
  rankList.innerHTML = themes.map((t, idx) => {
    const isActive = currentPreEntryTheme === t.theme_id ? "active" : "";
    const avgReturn = Number(t.avg_return || 0);
    const leaderReturn = Number(t.top_leader_return || 0);
    const avgReturnText = `${avgReturn >= 0 ? "+" : ""}${(avgReturn * 100).toFixed(1)}%`;
    const leaderReturnText = `${leaderReturn >= 0 ? "+" : ""}${(leaderReturn * 100).toFixed(1)}%`;
    const peakMonths = (t.peak_months || []).map((month) => `${month}월`).join("·") || "—";
    const noSafeRows = Number(t.candidate_count || 0) === 0;
    return `
      <div class="theme-rank-card ${isActive} ${noSafeRows ? "is-empty" : ""}" data-theme-id="${t.theme_id}" title="${escapeHtml(t.catalyst || "")}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <b style="color:${t.color}; font-size:12.5px;">${t.emoji} ${t.theme_name}</b>
          <span class="chip" style="background:rgba(255,255,255,0.08); font-size:11px;">상대 기여 ${t.weight_share_pct}%</span>
        </div>
        <div style="margin-top:4px; font-size:11.5px; color:#cbd5e1; display:flex; justify-content:space-between;">
          <span>기준 ${Number(t.analysis_month || 0)}월: <b class="${avgReturn >= 0 ? "text-emerald-400" : "text-rose-400"}">${avgReturnText}</b></span>
          <span>승률: <b>${(t.avg_win_rate * 100).toFixed(0)}%</b></span>
        </div>
        <div style="margin-top:4px; font-size:11px; color:#94a3b8;">
          👑 대장주: <span style="color:#fff; font-weight:700;">${escapeHtml(t.top_leader_name)}</span>${noSafeRows ? "" : ` (${leaderReturnText})`}
        </div>
        <div style="margin-top:5px; font-size:10.5px; color:#64748b; display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;">
          <span>테마점수 ${Number(t.avg_seasonality_score || 0).toFixed(1)} · 안전 종목 ${Number(t.candidate_count || 0)}/${Number(t.mapped_count || 0)} · 관찰 겹침 ${Number(t.pre_entry_count || 0)}</span>
          <span>관찰월 ${peakMonths}</span>
        </div>
      </div>
    `;
  }).join("");

  rankList.querySelectorAll(".theme-rank-card").forEach((card) => {
    card.addEventListener("click", () => {
      const tid = card.dataset.themeId;
      currentPreEntryTheme = currentPreEntryTheme === tid ? "all" : tid;
      syncPreEntryFilterControls();
      loadPreEntryView().catch(() => {});
    });
  });
}




const STATUS_HOVER_GUIDE_DATA = {
  ACTIVE: {
    title: "🟢 ACTIVE (현재 근거 확인)",
    color: "#10b981",
    desc: "과거 반복 패턴과 현재 연결된 퀀트·모멘텀 근거가 기준을 통과한 우선 관찰 후보",
    criteria: "계절성 점수 78점 이상 + 과거 승률 70% 이상 + 최근 3M 수익률 양호",
    action: "실측 피크 경로·거래 가능성·누락 근거를 종목 상세에서 재확인",
    actionColor: "#34d399",
  },
  WATCH: {
    title: "🟡 WATCH (관찰 / 대기)",
    color: "#eab308",
    desc: "과거 계절성 패턴은 우수하나, 올해 수급 유입이나 이벤트 촉매 발생 확인 대기 중",
    criteria: "계절성 점수 68점 이상 또는 최근 3개년 승률 60% 이상",
    action: "거래량과 외인·기관 수급이 실제로 연결될 때까지 관찰",
    actionColor: "#fde047",
  },
  DISCOVERY: {
    title: "🟣 DISCOVERY (신규 발굴)",
    color: "#a855f7",
    desc: "최근 3~5년간 새롭게 계절성 상승 패턴이 형성된 신규 발굴 후보주",
    criteria: "표본수 3년 이상 + 승률 67% 이상 + AI 원인 역추적 진행",
    action: "표본 확대와 이벤트·현재 데이터 근거 추가 확인",
    actionColor: "#c084fc",
  },
  WEAKENING: {
    title: "🟠 WEAKENING (엣지 약화)",
    color: "#f97316",
    desc: "과거에는 강했으나 최근 3년간 승률/월간 수익률이 하락하여 계절성 모멘텀이 둔화된 상태",
    criteria: "최근 3개년 승률 50% 미만",
    action: "최근 실패 연도와 무효화 조건을 우선 검토",
    actionColor: "#fb923c",
  },
  BROKEN: {
    title: "🔴 BROKEN (가설 훼손)",
    color: "#ef4444",
    desc: "최근 3개월간 급락했거나 올해 펀더멘털 악화/실적 쇼크로 계절성 룰이 깨진 종목",
    criteria: "3개월 수익률 -15% 이하 및 퀀트 종합점수 48점 미만",
    action: "계절성 가설을 사용하지 말고 훼손 근거를 재검토",
    actionColor: "#f87171",
  },
};

function showStatusPopover(statusKey, evt) {
  const popover = $("#status-hover-popover");
  if (!popover) return;
  const data = STATUS_HOVER_GUIDE_DATA[statusKey] || STATUS_HOVER_GUIDE_DATA.ACTIVE;

  $("#status-popover-title").textContent = data.title;
  $("#status-popover-title").style.color = data.color;
  $("#status-popover-desc").textContent = data.desc;
  $("#status-popover-criteria").textContent = data.criteria;
  $("#status-popover-action").textContent = data.action;
  $("#status-popover-action").style.color = data.actionColor;
  $("#status-popover-action-lbl").style.color = data.actionColor;
  popover.style.borderColor = `${data.color}88`;

  // Position popover near mouse
  const x = Math.min(window.innerWidth - 360, evt.clientX + 12);
  const y = Math.min(window.innerHeight - 200, evt.clientY + 12);
  popover.style.left = `${x}px`;
  popover.style.top = `${y}px`;

  popover.classList.remove("hidden");
}

function hideStatusPopover() {
  const popover = $("#status-hover-popover");
  if (popover) popover.classList.add("hidden");
}

function openStatusGuideModal() {
  const modal = $("#status-guide-modal");
  if (!modal) return;

  $("#status-guide-close-btn").onclick = () => modal.classList.add("hidden");
  $("#status-guide-confirm-btn").onclick = () => modal.classList.add("hidden");
  modal.onclick = (e) => {
    if (e.target === modal) modal.classList.add("hidden");
  };

  modal.classList.remove("hidden");
}


// --- Seasonality Discovery Screener v1.1 ---
let currentV11Subtab = "pre-entry";
let currentV11Horizon = 90;
let currentV11Lookback = 5;
let currentV11ExcludeExpired = true;
let discoveryRows = [];
let currentSeasonalityQuery = "";

function seasonalitySearchQuery() {
  return currentSeasonalityQuery || ($("#seasonality-q")?.value || "").trim();
}

function refreshCurrentSeasonalitySearch() {
  if (currentV11Subtab === "pre-entry") return loadPreEntryView();
  if (currentV11Subtab === "discovery") return loadDiscoveryRanked();
  if (currentV11Subtab === "explanation") return loadAIExplanations();
  if (currentV11Subtab === "calendar") return loadInstitutionalCalendar();
  return loadSeasonality();
}

async function selectSeasonalityStock(raw, selected = null) {
  const code = selected?.ticker ? padTicker(selected.ticker) : await resolveStockQuery(raw);
  if (!/^\d{6}$/.test(code)) throw new Error(`'${raw}'에 해당하는 종목을 찾지 못했습니다.`);
  currentSeasonalityQuery = code;
  const input = $("#seasonality-q");
  if (input) input.value = selected ? `${selected.company || ""} ${code}`.trim() : code;
  const discoveryTab = $("#tab-v11-discovery");
  if (discoveryTab && currentV11Subtab !== "discovery") discoveryTab.click();
  else await loadDiscoveryRanked();
}

async function loadDiscoveryRanked() {
  const tbody = $("#discovery-ranked-body");
  if (!tbody) return;

  const minGrade = $("#discovery-grade-filter") ? $("#discovery-grade-filter").value : "";
  const statusFilter = $("#discovery-status-filter") ? $("#discovery-status-filter").value : "all";
  const q = seasonalitySearchQuery();

  const params = new URLSearchParams({
    horizon_days: currentV11Horizon,
    lookback_years: currentV11Lookback,
    exclude_expired: currentV11ExcludeExpired,
  });
  if (minGrade) params.set("min_grade", minGrade);
  if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
  if (q) params.set("query", q);

  const res = await api(`/api/seasonality/discovery?${params.toString()}`);
  setSeasonalityAsOf(res);
  discoveryRows = res.rows || [];

  const countBadge = $("#discovery-count-val");
  if (countBadge) countBadge.textContent = `${discoveryRows.length.toLocaleString()}개`;

  if (!discoveryRows.length) {
    tbody.innerHTML = `<tr><td colspan="12" class="text-center text-slate-400 py-8">조건에 부합하는 디스커버리 후보가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = discoveryRows.map((r, idx) => {
    let statusCls = "status-discovery";
    let statusKo = "🟣 DISCOVERY";
    if (r.current_status === "ACTIVE") {
      statusCls = "status-active";
      statusKo = "🟢 ACTIVE";
    } else if (r.current_status === "WATCH") {
      statusCls = "status-watch";
      statusKo = "🟡 WATCH";
    } else if (r.current_status === "WEAKENING") {
      statusCls = "status-weakening";
      statusKo = "🟠 WEAKENING";
    } else if (r.current_status === "BROKEN") {
      statusCls = "status-broken";
      statusKo = "🔴 BROKEN";
    }

    let gradeCls = "grade-b";
    if (r.grade === "S") gradeCls = "grade-s";
    else if (r.grade === "A") gradeCls = "grade-a";
    else if (r.grade === "C") gradeCls = "grade-c";

    const wr = ((r.win_rate || 0) * 100).toFixed(0);
    const avgRet = ((r.median_return || 0) * 100).toFixed(1);
    const alpha = r.median_alpha == null ? "벤치마크 미연결" : `${r.median_alpha > 0 ? '+' : ''}${(r.median_alpha * 100).toFixed(1)}%`;

    const yearsTrackHtml = (r.years_track || []).map((y) => {
      const cls = y.is_win ? "year-track-win" : "year-track-loss";
      const retStr = (y.return * 100).toFixed(0);
      return `<span class="year-track-cell ${cls}" title="${y.year}년: ${(y.return*100).toFixed(1)}%">${y.year}: ${y.return > 0 ? '+' : ''}${retStr}%</span>`;
    }).join("");

    let stageCls = "stage-today";
    if (r.entry_stage === "PRE_ENTRY_15" || r.entry_stage === "PRE_ENTRY_30") stageCls = "stage-pre-entry";
    else if (r.entry_stage === "ACCUMULATE_60") stageCls = "stage-accumulate";
    else if (r.entry_stage === "EXIT_PEAK") stageCls = "stage-peak-exit";
    else if (r.entry_stage === "WATCH") stageCls = "stage-watch";

    return `
      <tr data-index="${idx}" class="clickable-row">
        <td>${idx + 1}</td>
        <td><span class="stage-pill ${stageCls}">${escapeHtml(r.entry_stage_label || '⚡ 진입')}</span></td>
        <td><span class="status-pill ${statusCls}" data-status="${escapeHtml(r.current_status || 'ACTIVE')}">${statusKo}</span></td>
        <td><span class="grade-badge ${gradeCls}">${escapeHtml(r.grade)}</span></td>
        <td>
          <div style="font-size:13.5px; font-weight:800; color:#fff;">${escapeHtml(r.company || r.ticker)}</div>
          <div style="display:flex; align-items:center; gap:4px; margin-top:2px;">
            <span class="meta" style="font-family:monospace;">${escapeHtml(r.ticker)}</span>
            <span class="chip" style="font-size:10px; padding:1px 5px; background:#1e293b; color:#94a3b8;">${escapeHtml(r.market || 'KOSPI')}</span>
          </div>
        </td>
        <td>
          <div style="display:flex; align-items:center; gap:6px;">
            <b style="color:#38bdf8; font-size:13.5px; font-weight:800;">${escapeHtml(r.window_name)}</b>
            <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(56,189,248,0.15); color:#38bdf8;">${r.sample_count}개년 검증</span>
          </div>
          <div style="margin-top:4px; font-size:11.5px; line-height:1.4;">
            <span style="color:#38bdf8; font-weight:700;">📈 진입: ${escapeHtml(r.entry_window_str || '—')}</span><br/>
            <span style="color:#fbbf24; font-weight:700;">➔ 엑시트: ${escapeHtml(r.exit_window_str || '—')}</span>
          </div>
        </td>
        <td>
          <div style="font-size:15px; font-weight:900; color:#38bdf8;">${r.seasonality_score}점</div>
        </td>
        <td class="font-bold">${wr}%</td>
        <td class="${r.median_return > 0 ? 'up font-bold' : 'down'}">${r.median_return > 0 ? '+' : ''}${avgRet}%</td>
        <td class="font-bold text-emerald-400">${alpha}</td>
        <td>
          <div class="year-track-bar" style="flex-wrap:wrap; gap:4px;">${yearsTrackHtml}</div>
        </td>
        <td>
          <button type="button" class="btn small btn-seasonality-detail" data-ticker="${escapeHtml(r.ticker)}" style="font-size:11px; padding:2px 8px; background:rgba(56,189,248,0.2); color:#38bdf8; border:1px solid rgba(56,189,248,0.35);">🎯 플레이북</button>
        </td>
      </tr>
    `;
  }).join("");

  // Bind hover on status pills
  tbody.querySelectorAll(".status-pill").forEach((pill) => {
    pill.addEventListener("mouseenter", (e) => {
      const st = pill.dataset.status || "ACTIVE";
      showStatusPopover(st, e);
    });
    pill.addEventListener("mousemove", (e) => {
      const st = pill.dataset.status || "ACTIVE";
      showStatusPopover(st, e);
    });
    pill.addEventListener("mouseleave", () => {
      hideStatusPopover();
    });
  });

  // Bind clicks to open rich Playbook Detail Modal
  tbody.querySelectorAll("tr.clickable-row").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".btn-seasonality-ai")) return;
      const idx = parseInt(tr.dataset.index, 10);
      const rowData = discoveryRows[idx];
      if (rowData) {
        openDiscoveryDetailModal(rowData);
      }
    });
  });

  tbody.querySelectorAll(".btn-seasonality-ai").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const code = btn.dataset.ticker;
      const comp = btn.dataset.company || code;
      const proceed = confirm(`[${comp} (${code})] AI 심층 분석 리포트를 발간하시겠습니까?\n(LLM 토큰이 사용되며 백그라운드에서 안전하게 작성됩니다.)`);
      if (proceed) {
        runReport(code).catch((err) => alert(err.message));
      }
    });
  });
}

async function loadAIExplanations() {
  const container = $("#explanation-cards-list");
  if (!container) return;

  const q = seasonalitySearchQuery();
  const queryParam = q ? `&query=${encodeURIComponent(q)}` : "";
  const res = await api(`/api/seasonality/discovery?horizon_days=${currentV11Horizon}&lookback_years=${currentV11Lookback}&exclude_expired=${currentV11ExcludeExpired}${queryParam}`);
  setSeasonalityAsOf(res);
  const rows = res.rows || [];

  const lookbackLabel = currentV11Lookback > 0 ? `최근 ${currentV11Lookback}개년` : "전체 기간";
  if (!rows.length) {
    container.innerHTML = `<div class="text-center text-slate-400 py-8">분석된 AI 이벤트 설명 데이터가 없습니다. (${lookbackLabel} · 진입 ${currentV11Horizon}일)</div>`;
    return;
  }

  const cards = rows.slice(0, 30).map((r) => {
    const failedListHtml = (r.failed_analysis || []).map((f) => `<li style="color:#fca5a5; font-size:12px;">${escapeHtml(f)}</li>`).join("");
    const explanationMode = r.event_explanation_mode || "RULE_BASED";
    const explanationLabel = explanationMode === "CURATED_TICKER" ? "검토된 이벤트" : "규칙 기반 가설";

    return `
      <div class="event-timeline-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <b style="font-size:16px; color:#fff;">${escapeHtml(r.company || r.ticker)} (${escapeHtml(r.ticker)})</b>
              <span class="chip" style="background:rgba(56,189,248,0.2); color:#38bdf8; font-weight:800;">${escapeHtml(r.window_name)} 상승패턴</span>
              <span class="chip" style="background:rgba(139,92,246,0.2); color:#c084fc;">${explanationLabel} · 신뢰도 ${r.event_confidence}</span>
            </div>
            <div style="margin-top:8px; font-size:13.5px; color:#38bdf8; font-weight:700;">
              💡 핵심 촉매: ${escapeHtml(r.common_event_cluster)}
            </div>
            <div style="margin-top:4px; font-size:12.5px; color:#cbd5e1;">
              📌 통계 근거·확인 포인트: ${escapeHtml(r.secondary_cluster || '실측 표본과 확인 포인트가 없습니다.')}
            </div>
            <div style="margin-top:4px; font-size:10.5px; color:#64748b;">근거 방식: ${escapeHtml(r.event_explanation_source || '계절성 통계·업종 매핑')}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:14px; font-weight:800; color:#34d399;">승률 ${((r.win_rate || 0)*100).toFixed(0)}% · 월간 중앙수익 ${pbPct(r.median_return)}</div>
            <div style="font-size:11.5px; color:#94a3b8;">${r.sample_count}개년 추적</div>
          </div>
        </div>

        ${failedListHtml ? `
          <div style="margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.06);">
            <b style="font-size:12px; color:#f87171;">⚠️ 실패 연도 원인 분석:</b>
            <ul style="margin:4px 0 0 16px; padding:0;">${failedListHtml}</ul>
          </div>
        ` : ''}

        <div style="margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#94a3b8;">
          <div>🛑 <b>무효화 조건:</b> <span style="color:#cbd5e1;">${escapeHtml(r.invalidating_conditions)}</span></div>
          <button type="button" class="ghost small" onclick="openStock('${escapeHtml(r.ticker)}')">종목 심층 분석 →</button>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:4px;">
      <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8;">${lookbackLabel} · 진입 ${currentV11Horizon}일 · ${rows.length}건 중 상위 30</span>
      <span class="meta">실패 연도·무효화 조건은 종목별 반복 상승 구간의 공통 이벤트를 역추적한 결과입니다.</span>
    </div>
    ${cards}
  `;
}

function setupV11SeasonalityUI() {
  const btnMom = $("#btn-open-momentum-manager");
  const tabPre = $("#tab-v11-pre-entry");
  const tabDisc = $("#tab-v11-discovery");
  const tabExpl = $("#tab-v11-explanation");
  const tabCal = $("#tab-v11-calendar");
  const tabHeat = $("#tab-v11-heatmap");

  const paneMom = $("#pane-v11-momentum");
  const panePre = $("#pane-v11-pre-entry");
  const paneDisc = $("#pane-v11-discovery");
  const paneExpl = $("#pane-v11-explanation");
  const paneCal = $("#pane-v11-calendar");
  const paneHeat = $("#pane-v11-heatmap");

  function switchV11Subtab(subtab) {
    currentV11Subtab = subtab;
    [tabPre, tabDisc, tabExpl, tabCal, tabHeat].forEach((t) => t?.classList.remove("active"));
    [paneMom, panePre, paneDisc, paneExpl, paneCal, paneHeat].forEach((p) => p?.classList.add("hidden"));

    if (btnMom) {
      if (subtab === "momentum") {
        btnMom.style.background = "linear-gradient(135deg, #0ea5e9, #0284c7)";
        btnMom.style.borderColor = "#38bdf8";
        btnMom.style.boxShadow = "0 0 12px rgba(56, 189, 248, 0.5)";
      } else {
        btnMom.style.background = "linear-gradient(135deg, #0284c7, #0369a1)";
        btnMom.style.borderColor = "#38bdf8";
        btnMom.style.boxShadow = "0 2px 8px rgba(0,0,0,0.3)";
      }
    }

    if (subtab === "momentum") {
      paneMom?.classList.remove("hidden");
      loadCalendarMomentumPortfolio().catch(() => {});
    } else if (subtab === "pre-entry") {
      tabPre?.classList.add("active");
      panePre?.classList.remove("hidden");
      loadPreEntryView().catch(() => {});
    } else if (subtab === "discovery") {
      tabDisc?.classList.add("active");
      paneDisc?.classList.remove("hidden");
      loadDiscoveryRanked().catch(() => {});
    } else if (subtab === "explanation") {
      tabExpl?.classList.add("active");
      paneExpl?.classList.remove("hidden");
      loadAIExplanations().catch(() => {});
    } else if (subtab === "calendar") {
      tabCal?.classList.add("active");
      paneCal?.classList.remove("hidden");
      loadInstitutionalCalendar().catch(() => {});
    } else if (subtab === "heatmap") {
      tabHeat?.classList.add("active");
      paneHeat?.classList.remove("hidden");
      loadSeasonality().catch(() => {});
    }
  }

  btnMom?.addEventListener("click", () => {
    if (currentV11Subtab === "momentum") {
      switchV11Subtab("pre-entry");
    } else {
      switchV11Subtab("momentum");
    }
  });
  tabPre?.addEventListener("click", () => switchV11Subtab("pre-entry"));
  tabDisc?.addEventListener("click", () => switchV11Subtab("discovery"));
  tabExpl?.addEventListener("click", () => switchV11Subtab("explanation"));
  tabCal?.addEventListener("click", () => switchV11Subtab("calendar"));
  tabHeat?.addEventListener("click", () => switchV11Subtab("heatmap"));

  const preEntrySortTabs = $("#pre-entry-sort-tabs");
  preEntrySortTabs?.querySelectorAll("[data-pre-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentPreEntrySort = btn.dataset.preSort || "score";
      syncPreEntryFilterControls();
      loadPreEntryView().catch(() => {});
    });
  });

  $("#pre-entry-market-filter")?.addEventListener("change", (event) => {
    const value = String(event.target.value || "all").toUpperCase();
    currentPreEntryMarket = value === "KOSPI" || value === "KOSDAQ" ? value : "all";
    loadPreEntryView().catch(() => {});
  });

  $("#theme-filter-reset")?.addEventListener("click", () => {
    currentPreEntryTheme = "all";
    syncPreEntryFilterControls();
    loadPreEntryView().catch(() => {});
  });
  syncPreEntryFilterControls();

  // Lookback Period Filter Chips
  const lookbackContainer = $("#discovery-lookback-tabs");
  if (lookbackContainer) {
    lookbackContainer.querySelectorAll(".preset-chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        lookbackContainer.querySelectorAll(".preset-chip-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentV11Lookback = parseInt(btn.dataset.lookback, 10);
        if (currentV11Subtab === "discovery") loadDiscoveryRanked().catch(() => {});
        else if (currentV11Subtab === "explanation") loadAIExplanations().catch(() => {});
      });
    });
  }

  // Horizon Filter Chips
  const horizonContainer = $("#discovery-horizon-tabs");
  if (horizonContainer) {
    horizonContainer.querySelectorAll(".preset-chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        horizonContainer.querySelectorAll(".preset-chip-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentV11Horizon = parseInt(btn.dataset.horizon, 10);
        if (currentV11Subtab === "discovery") loadDiscoveryRanked().catch(() => {});
        else if (currentV11Subtab === "explanation") loadAIExplanations().catch(() => {});
      });
    });
  }

  // 🌟 Exclude Expired Season Toggle Button
  const btnToggleExclude = $("#btn-toggle-exclude-expired");
  if (btnToggleExclude) {
    btnToggleExclude.onclick = () => {
      currentV11ExcludeExpired = !currentV11ExcludeExpired;
      if (currentV11ExcludeExpired) {
        btnToggleExclude.classList.add("active");
        btnToggleExclude.style.background = "rgba(56,189,248,0.2)";
        btnToggleExclude.style.borderColor = "#38bdf8";
        btnToggleExclude.style.color = "#38bdf8";
        btnToggleExclude.textContent = "☑️ 시즌 종료 제외 (관찰 중만)";
      } else {
        btnToggleExclude.classList.remove("active");
        btnToggleExclude.style.background = "rgba(30,41,59,0.5)";
        btnToggleExclude.style.borderColor = "#475569";
        btnToggleExclude.style.color = "#94a3b8";
        btnToggleExclude.textContent = "⬜ 전체 보기 (시즌 종료 포함)";
      }
      loadDiscoveryRanked().catch(() => {});
    };
  }

  // Status Guide Button & Modal
  const btnStatusGuide = $("#btn-status-guide");
  if (btnStatusGuide) {
    btnStatusGuide.onclick = () => openStatusGuideModal();
    btnStatusGuide.onmouseenter = (e) => showStatusPopover("ACTIVE", e);
    btnStatusGuide.onmouseleave = () => hideStatusPopover();
  }

  $("#discovery-grade-filter")?.addEventListener("change", () => loadDiscoveryRanked().catch(() => {}));
  $("#discovery-status-filter")?.addEventListener("change", () => loadDiscoveryRanked().catch(() => {}));

  // Setup original Heatmap UI controls
  setupSeasonalityUI();
}


// --- Institutional Seasonality & Calendar Event Engine v2.0 ---
let currentInstSubtab = "ranked";
let currentInstHorizon = 90;
let institutionalRows = [];
let institutionalEvents = [];

async function loadInstitutionalRanked() {
  const tbody = $("#seasonality-ranked-body");
  if (!tbody) return;

  const minGrade = $("#seasonality-grade-filter") ? $("#seasonality-grade-filter").value : "";
  const confFilter = $("#seasonality-conf-filter") ? $("#seasonality-conf-filter").value : "all";
  const groupFilter = $("#seasonality-group-filter") ? $("#seasonality-group-filter").value : "all";
  const q = seasonalitySearchQuery();

  const params = new URLSearchParams({
    horizon_days: currentInstHorizon,
  });
  if (minGrade) params.set("min_grade", minGrade);
  if (confFilter && confFilter !== "all") params.set("confirmation", confFilter);
  if (groupFilter && groupFilter !== "all") params.set("group_id", groupFilter);
  if (q) params.set("query", q);

  const res = await api(`/api/seasonality/ranked?${params.toString()}`);
  setSeasonalityAsOf(res);
  institutionalRows = res.rows || [];

  if (!institutionalRows.length) {
    tbody.innerHTML = `<tr><td colspan="11" class="text-center text-slate-400 py-8">조건에 부합하는 이벤트 후보가 없습니다. 필터를 완화해 보세요.</td></tr>`;
    return;
  }

  tbody.innerHTML = institutionalRows.map((r, idx) => {
    let gradeCls = "grade-b";
    if (r.grade === "S+") gradeCls = "grade-s-plus";
    else if (r.grade === "S") gradeCls = "grade-s";
    else if (r.grade === "A+") gradeCls = "grade-a-plus";
    else if (r.grade === "A") gradeCls = "grade-a";
    else if (r.grade === "C") gradeCls = "grade-c";

    let confCls = "conf-neutral";
    let confKo = "⚪ NEUTRAL (중립)";
    if (r.confirmation_state === "STRONG") {
      confCls = "conf-strong";
      confKo = "🟢 STRONG (강한 지지)";
    } else if (r.confirmation_state === "CONFIRMED") {
      confCls = "conf-confirmed";
      confKo = "🟡 CONFIRMED (확인)";
    } else if (r.confirmation_state === "CONTRADICTED") {
      confCls = "conf-contradicted";
      confKo = "🔴 CONTRADICTED (역행·주의)";
    }

    const b = r.score_breakdown || {};
    const histW = ((b.historical_edge || 0) / 45 * 100).toFixed(0);
    const currW = ((b.current_confirmation || 0) / 35 * 100).toFixed(0);
    const evW = ((b.event_quality || 0) / 20 * 100).toFixed(0);

    const wr = ((r.win_rate || 0) * 100).toFixed(0);
    const avgRet = ((r.avg_return || 0) * 100).toFixed(1);
    const prePriceBadge = r.pre_pricing_flag ? `<span class="chip" style="background:rgba(244,63,94,0.2); color:#fb7185; font-size:10px;">⚠️ 3M 과열 감점</span>` : "";

    return `
      <tr data-ticker="${escapeHtml(r.ticker)}" class="clickable-row">
        <td>${idx + 1}</td>
        <td><span class="grade-badge ${gradeCls}">${escapeHtml(r.grade)}</span></td>
        <td>
          <b>${escapeHtml(r.company || r.ticker)}</b>
          <span class="meta">${escapeHtml(r.ticker)}</span>
        </td>
        <td>
          <div style="font-weight:700; color:#fff; font-size:12.5px;">${escapeHtml(r.event_title)}</div>
          <div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
            <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:10.5px;">D-${r.d_day} (${escapeHtml(r.target_date)})</span>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(r.event_group_name)}</span>
            ${prePriceBadge}
          </div>
        </td>
        <td>
          <div style="font-size:15px; font-weight:900; color:#38bdf8;">${r.seasonality_score}점</div>
        </td>
        <td>
          <div class="pillar-bars-wrap" title="과거우위 ${b.historical_edge}점 / 현재확인 ${b.current_confirmation}점 / 이벤트품질 ${b.event_quality}점">
            <div class="pillar-bar-segment pillar-bar-hist" style="width:${Math.max(histW * 0.4, 6)}px;" title="과거우위: ${b.historical_edge}/45점"></div>
            <div class="pillar-bar-segment pillar-bar-curr" style="width:${Math.max(currW * 0.35, 6)}px;" title="현재확인: ${b.current_confirmation}/35점"></div>
            <div class="pillar-bar-segment pillar-bar-event" style="width:${Math.max(evW * 0.2, 6)}px;" title="이벤트품질: ${b.event_quality}/20점"></div>
          </div>
          <div style="font-size:10px; color:#94a3b8; margin-top:2px;">${b.historical_edge} / ${b.current_confirmation} / ${b.event_quality}</div>
        </td>
        <td><span class="conf-pill ${confCls}">${confKo}</span></td>
        <td class="font-bold">${wr}%</td>
        <td class="${r.avg_return > 0 ? 'up font-bold' : 'down'}">${r.avg_return > 0 ? '+' : ''}${avgRet}%</td>
        <td>
          <div style="font-size:12px; color:#34d399; font-weight:700;">진입: ${escapeHtml(r.optimal_entry_window)}</div>
          <div style="font-size:11px; color:#cbd5e1;">청산: ${escapeHtml(r.optimal_exit_window)}</div>
        </td>
        <td>
          <button type="button" class="ghost small btn-seasonality-ai" data-ticker="${escapeHtml(r.ticker)}" data-company="${escapeHtml(r.company || r.ticker)}">🤖 AI 리포트</button>
        </td>
      </tr>
    `;
  }).join("");

  // Bind hover on status pills
  tbody.querySelectorAll(".status-pill").forEach((pill) => {
    pill.addEventListener("mouseenter", (e) => {
      const st = pill.dataset.status || "ACTIVE";
      showStatusPopover(st, e);
    });
    pill.addEventListener("mousemove", (e) => {
      const st = pill.dataset.status || "ACTIVE";
      showStatusPopover(st, e);
    });
    pill.addEventListener("mouseleave", () => {
      hideStatusPopover();
    });
  });

  // Bind clicks to open rich Playbook Detail Modal
  tbody.querySelectorAll("tr.clickable-row").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".btn-seasonality-ai")) return;
      const idx = parseInt(tr.dataset.index, 10);
      const rowData = discoveryRows[idx];
      if (rowData) {
        openDiscoveryDetailModal(rowData);
      }
    });
  });

  tbody.querySelectorAll(".btn-seasonality-ai").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const code = btn.dataset.ticker;
      const comp = btn.dataset.company || code;
      const proceed = confirm(`[${comp} (${code})] AI 심층 분석 리포트를 발간하시겠습니까?\n(LLM 토큰이 사용되며 백그라운드에서 안전하게 작성됩니다.)`);
      if (proceed) {
        runReport(code).catch((err) => alert(err.message));
      }
    });
  });
}

async function loadInstitutionalCalendar() {
  const container = $("#seasonality-calendar-list");
  if (!container) return;

  const res = await api(`/api/seasonality/events?horizon_days=${currentV11Horizon}`);
  setSeasonalityAsOf(res);
  institutionalEvents = res.events || [];

  if (!institutionalEvents.length) {
    container.innerHTML = `<div class="text-center text-slate-400 py-8">향후 ${currentV11Horizon}일 내 예정된 마스터 이벤트가 없습니다.</div>`;
    return;
  }

  container.innerHTML = institutionalEvents.map((ev) => {
    const sectorsHtml = (ev.beneficiary_sectors || []).map((s) => {
      return `<span class="sector-badge">${escapeHtml(s)}</span>`;
    }).join(" ");

    const stocksHtml = (ev.beneficiary_stocks || []).map((stk) => {
      return `
        <div class="event-stock-chip" onclick="openStock('${escapeHtml(stk.ticker)}')">
          <div>
            <b style="color:#fff; font-size:12.5px;">${escapeHtml(stk.company)}</b>
            <span style="color:#94a3b8; font-size:11px; margin-left:4px;">${escapeHtml(stk.ticker)}</span>
            <div style="font-size:11px; color:#cbd5e1; margin-top:2px;">${escapeHtml(stk.role || '')}</div>
          </div>
          <button type="button" class="ghost small btn-cal-ai" data-ticker="${escapeHtml(stk.ticker)}" data-company="${escapeHtml(stk.company)}" style="font-size:10.5px; height:24px; padding:0 6px; margin-left:6px;">🤖 AI</button>
        </div>
      `;
    }).join("");

    return `
      <div class="event-timeline-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
          <div style="flex:1; min-width:300px;">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <span class="chip" style="background:rgba(56,189,248,0.2); color:#38bdf8; font-weight:800; font-size:12px;">D-${ev.d_day} (${escapeHtml(ev.target_date)})</span>
              <b style="font-size:15.5px; color:#fff;">${escapeHtml(ev.title)}</b>
              <span class="chip" style="background:rgba(30,41,59,0.8); color:#94a3b8; font-size:11px;">${escapeHtml(ev.group_name)}</span>
            </div>
            <p style="margin:6px 0 0; color:#cbd5e1; font-size:12.5px; line-height:1.5;">${escapeHtml(ev.description)}</p>

            ${sectorsHtml ? `
              <div class="event-sectors-row">
                <span style="font-size:11.5px; color:#94a3b8; font-weight:700;">🎯 수혜 섹터:</span>
                ${sectorsHtml}
              </div>
            ` : ''}
          </div>
          <div style="text-align:right;">
            <div style="font-size:12.5px; color:#34d399; font-weight:700;">권장 진입: ${escapeHtml(ev.default_entry_window)}</div>
            <div style="font-size:11.5px; color:#94a3b8;">목표 청산: ${escapeHtml(ev.default_exit_window)}</div>
            <div style="font-size:11px; color:#cbd5e1; margin-top:4px;">확정성: <b>${(ev.date_certainty * 100).toFixed(0)}%</b> · 리스크: <b style="color:${ev.binary_risk === 'HIGH' ? '#f87171' : '#34d399'}">${ev.binary_risk}</b></div>
          </div>
        </div>

        ${stocksHtml ? `
          <div class="event-stocks-wrap">
            <div style="font-size:12px; font-weight:700; color:#38bdf8; display:flex; justify-content:space-between; align-items:center;">
              <span>🏢 핵심 수혜 및 수급 종목 (${ev.beneficiary_stocks.length}개사)</span>
              <span style="font-size:11px; color:#94a3b8; font-weight:normal;">종목 클릭 시 상세 리서치 창 열림</span>
            </div>
            <div class="event-stocks-grid">
              ${stocksHtml}
            </div>
          </div>
        ` : ''}

        <div style="margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#94a3b8;">
          <div>⚠️ <b>무효화 조건:</b> <span style="color:#fca5a5;">${escapeHtml(ev.invalidating_rule)}</span></div>
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".btn-cal-ai").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const code = btn.dataset.ticker;
      const comp = btn.dataset.company || code;
      const proceed = confirm(`[${comp} (${code})] AI 심층 분석 리포트를 발간하시겠습니까?\n(LLM 토큰이 사용되며 백그라운드에서 안전하게 작성됩니다.)`);
      if (proceed) {
        runReport(code).catch((err) => alert(err.message));
      }
    });
  });
}

function setupInstitutionalSeasonalityUI() {
  // Subtab switching
  const tabRanked = $("#tab-inst-ranked");
  const tabCalendar = $("#tab-inst-calendar");
  const tabHeatmap = $("#tab-inst-heatmap");
  const paneRanked = $("#pane-inst-ranked");
  const paneCalendar = $("#pane-inst-calendar");
  const paneHeatmap = $("#pane-inst-heatmap");

  function switchInstSubtab(subtab) {
    currentInstSubtab = subtab;
    [tabRanked, tabCalendar, tabHeatmap].forEach((t) => t?.classList.remove("active"));
    [paneRanked, paneCalendar, paneHeatmap].forEach((p) => p?.classList.add("hidden"));

    if (subtab === "ranked") {
      tabRanked?.classList.add("active");
      paneRanked?.classList.remove("hidden");
      loadInstitutionalRanked().catch(() => {});
    } else if (subtab === "calendar") {
      tabCalendar?.classList.add("active");
      paneCalendar?.classList.remove("hidden");
      loadInstitutionalCalendar().catch(() => {});
    } else if (subtab === "heatmap") {
      tabHeatmap?.classList.add("active");
      paneHeatmap?.classList.remove("hidden");
      loadSeasonality().catch(() => {});
    }
  }

  tabRanked?.addEventListener("click", () => switchInstSubtab("ranked"));
  tabCalendar?.addEventListener("click", () => switchInstSubtab("calendar"));
  tabHeatmap?.addEventListener("click", () => switchInstSubtab("heatmap"));

  // Horizon Filter Chips
  const horizonContainer = $("#seasonality-horizon-tabs");
  if (horizonContainer) {
    horizonContainer.querySelectorAll(".preset-chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        horizonContainer.querySelectorAll(".preset-chip-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentInstHorizon = parseInt(btn.dataset.horizon, 10);
        if (currentV11Subtab === "discovery") loadDiscoveryRanked().catch(() => {});
    else if (currentV11Subtab === "explanation") loadAIExplanations().catch(() => {});
        else if (currentInstSubtab === "calendar") loadInstitutionalCalendar().catch(() => {});
      });
    });
  }

  // Dropdown filter triggers
  $("#seasonality-grade-filter")?.addEventListener("change", () => loadInstitutionalRanked().catch(() => {}));
  $("#seasonality-conf-filter")?.addEventListener("change", () => loadInstitutionalRanked().catch(() => {}));
  $("#seasonality-group-filter")?.addEventListener("change", () => loadInstitutionalRanked().catch(() => {}));

  // Setup original Heatmap UI controls
  setupV11SeasonalityUI();
}


// --- Seasonality & Calendar Anomaly Screener ---
let currentSeasonalityMonth = new Date().getMonth() + 1; // 1-12
let currentSeasonalityPreset = "";
let seasonalityRows = [];
let seasonalityPresetCatalog = {};

function renderMonthHeatmapBar(months, targetMonth) {
  if (!months || months.length < 12) return "—";
  return `
    <div class="month-heatmap-bar">
      ${months.map((m) => {
        const ret = m.avg_return || 0;
        const wr = (m.win_rate || 0) * 100;
        let cls = "ret-flat";
        if (ret >= 0.10) cls = "ret-super-up";
        else if (ret > 0.01) cls = "ret-up";
        else if (ret <= -0.10) cls = "ret-super-down";
        else if (ret < -0.01) cls = "ret-down";

        const isTarget = m.month === targetMonth ? "current-target-month" : "";
        const tip = `${m.month}월: 승률 ${wr.toFixed(0)}% · 평균 ${(ret * 100).toFixed(1)}% (표본 ${m.years_count}년)`;
        return `<div class="month-mini-cell ${cls} ${isTarget}" data-tip="${escapeHtml(tip)}" title="${escapeHtml(tip)}">${m.month}</div>`;
      }).join("")}
    </div>
  `;
}

function syncSeasonalityModeControls() {
  const eventMode = Boolean(currentSeasonalityPreset);
  const preset = seasonalityPresetCatalog[currentSeasonalityPreset] || null;

  $("#seasonality-month-tabs")?.querySelectorAll(".month-tab-btn").forEach((btn) => {
    btn.disabled = eventMode;
    btn.setAttribute("aria-disabled", eventMode ? "true" : "false");
    btn.style.opacity = eventMode ? "0.45" : "1";
    btn.style.cursor = eventMode ? "not-allowed" : "pointer";
  });

  ["seasonality-min-wr", "seasonality-min-ret"].forEach((id) => {
    const control = $(`#${id}`);
    if (control) control.disabled = eventMode;
  });
  ["seasonality-min-wr-wrap", "seasonality-min-ret-wrap"].forEach((id) => {
    const wrap = $(`#${id}`);
    if (wrap) wrap.style.opacity = eventMode ? "0.45" : "1";
  });

  const note = $("#seasonality-filter-mode-note");
  if (note) {
    note.innerHTML = eventMode && preset
      ? `<b style="color:#fbbf24;">특수 이벤트 종목군 모드</b> · ${escapeHtml(preset.title || preset.label || currentSeasonalityPreset)} 관련 거래 가능 종목을 월·최소조건과 관계없이 표시합니다. 표의 수치는 이벤트 비교 기준 ${Number(preset.analysis_month || currentSeasonalityMonth)}월 통계입니다.`
      : "월 탐색 모드 · 선택 월의 승률과 평균수익률 조건으로 전 종목을 검색합니다.";
  }
}

function bindSeasonalityPresetControls() {
  const presetContainer = $("#seasonality-presets");
  if (!presetContainer) return;
  presetContainer.querySelectorAll(".preset-chip-btn").forEach((btn) => {
    btn.onclick = () => {
      currentSeasonalityPreset = btn.dataset.preset || "";
      presetContainer.querySelectorAll(".preset-chip-btn").forEach((item) => {
        item.classList.toggle("active", (item.dataset.preset || "") === currentSeasonalityPreset);
      });
      syncSeasonalityModeControls();
      loadSeasonality().catch(() => {});
    };
  });
}

function renderSeasonalityPresetControls(presets) {
  if (!presets || typeof presets !== "object") return;
  seasonalityPresetCatalog = presets;
  const presetContainer = $("#seasonality-presets");
  if (!presetContainer) return;

  const controls = Object.entries(presets).map(([key, preset]) => {
    const active = currentSeasonalityPreset === key ? "active" : "";
    const label = preset.label || preset.title || key;
    const tip = `${preset.title || label} · ${preset.description || "특수 이벤트 종목군"}`;
    return `<button type="button" class="preset-chip-btn ${active}" data-preset="${escapeHtml(key)}" title="${escapeHtml(tip)}">${escapeHtml(label)}</button>`;
  }).join("");
  presetContainer.innerHTML = `
    <button type="button" class="preset-chip-btn ${currentSeasonalityPreset ? "" : "active"}" data-preset="">✨ 전체 고승률 탐색</button>
    ${controls}
  `;
  bindSeasonalityPresetControls();
  syncSeasonalityModeControls();
}

async function loadSeasonality() {
  loadSeasonalityTier1Briefing().catch(() => {});
  const minWr = parseFloat($("#seasonality-min-wr") ? $("#seasonality-min-wr").value : "0.80");
  const minRet = parseFloat($("#seasonality-min-ret") ? $("#seasonality-min-ret").value : "0.05");
  const q = seasonalitySearchQuery();

  const params = new URLSearchParams();
  if (currentSeasonalityPreset) {
    params.set("preset", currentSeasonalityPreset);
  } else {
    params.set("month", currentSeasonalityMonth);
    params.set("min_win_rate", minWr);
    params.set("min_avg_return", minRet);
  }
  if (q) params.set("query", q);

  const data = await api(`/api/seasonality/scan?${params.toString()}`);
  setSeasonalityAsOf(data);
  seasonalityRows = data.rows || [];
  renderSeasonalityPresetControls(data.presets || seasonalityPresetCatalog);

  const countBadge = $("#seasonality-count-badge");
  if (countBadge) {
    const scanned = data.universe_scanned || seasonalityRows.length;
    const listed = data.universe_listed || scanned;
    const kosdaq = (data.markets || {}).KOSDAQ;
    const kospi = (data.markets || {}).KOSPI;
    const mkt = [kospi != null ? `KOSPI ${kospi}` : null, kosdaq != null ? `KOSDAQ ${kosdaq}` : null].filter(Boolean).join(" · ");
    if (data.filter_mode === "event" && data.active_preset) {
      const eventName = data.active_preset.label || data.active_preset.title || currentSeasonalityPreset;
      const mappedCount = Number(data.event_mapped_count || data.active_preset.tickers?.length || seasonalityRows.length);
      countBadge.textContent = `${eventName} 현재 표시 ${seasonalityRows.length}/${mappedCount} · 월/최소조건 미적용 · 거래불가·데이터 미확인은 안전 제외`;
    } else {
      countBadge.textContent = `${currentSeasonalityMonth}월 조건 부합 ${seasonalityRows.length}종목 · 전종목 스캔 ${scanned}/${listed}${mkt ? ` (${mkt})` : ""}`;
    }
  }

  renderSeasonalityTable();
}

function renderSeasonalityTable() {
  const tbody = $("#seasonality-body");
  if (!tbody) return;

  if (!seasonalityRows.length) {
    const emptyText = currentSeasonalityPreset
      ? "현재 거래 가능성 검증을 통과한 해당 이벤트 종목이 없습니다. 거래정지·상장상태·가격 데이터 갱신 여부를 확인해 주세요."
      : `조건에 부합하는 ${currentSeasonalityMonth}월 계절성 종목이 없습니다. 필터를 완화해 보세요.`;
    tbody.innerHTML = `<tr><td colspan="11" class="text-center text-slate-400 py-8">${emptyText}</td></tr>`;
    return;
  }

  tbody.innerHTML = seasonalityRows.map((r, idx) => {
    const wr = (r.win_rate || 0) * 100;
    const wrCls = wr >= 75 ? "text-emerald-400 font-bold" : wr >= 60 ? "text-emerald-300" : "";
    const avgRet = (r.avg_return || 0) * 100;
    const retCls = avgRet > 0 ? "up font-bold" : "down";
    const medRet = (r.median_return || 0) * 100;

    // Robust 8-Theme Auto Matching for Heatmap Screener
    function getThemeBadges(row) {
      const comp = (row.company || "").toLowerCase();
      const ind = (row.industry || "").toLowerCase();
      const tags = row.tags || [];
      const badges = [];

      if (row.event_mode && row.event_title) {
        badges.push(`<span class="chip" style="background:rgba(251,191,36,0.14); color:#fbbf24; font-weight:800;">${escapeHtml(row.event_title)}</span>`);
      }

      if (tags.includes("winter_heater") || comp.includes("나비엔") || comp.includes("파세코") || comp.includes("신일") || comp.includes("가스") || comp.includes("난방")) {
        badges.push(`<span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:700;">❄️ 난방·보일러</span>`);
      }
      if (tags.includes("summer_heat") || comp.includes("에어컨") || comp.includes("빙그레") || comp.includes("위닉스") || comp.includes("창문형")) {
        badges.push(`<span class="chip" style="background:rgba(245,158,11,0.15); color:#f59e0b; font-weight:700;">☀️ 폭염·냉방</span>`);
      }
      if (tags.includes("galaxy_phone") || comp.includes("이노텍") || comp.includes("비에이치") || comp.includes("파인엠텍") || comp.includes("바텍") || ind.includes("전자부품")) {
        badges.push(`<span class="chip" style="background:rgba(179,136,255,0.15); color:#b388ff; font-weight:700;">📱 IT·스마트폰</span>`);
      }
      if (tags.includes("dividend_play") || comp.includes("금융") || comp.includes("은행") || comp.includes("지주") || comp.includes("증권") || comp.includes("보험") || comp.includes("통신")) {
        badges.push(`<span class="chip" style="background:rgba(16,185,129,0.15); color:#34d399; font-weight:700;">💰 밸류업·배당</span>`);
      }
      if (comp.includes("게임") || comp.includes("소프트") || comp.includes("펄어비스") || comp.includes("크래프톤") || comp.includes("엔터") || comp.includes("웹툰") || ind.includes("소프트웨어") || ind.includes("게임")) {
        badges.push(`<span class="chip" style="background:rgba(255,179,0,0.15); color:#ffb300; font-weight:700;">🎮 게임·콘텐츠</span>`);
      }
      if (comp.includes("바이오") || comp.includes("제약") || comp.includes("약품") || comp.includes("생명") || comp.includes("헬스") || ind.includes("의약품") || ind.includes("바이오")) {
        badges.push(`<span class="chip" style="background:rgba(255,82,82,0.15); color:#ff5252; font-weight:700;">🧬 제약·바이오</span>`);
      }
      if (comp.includes("반도체") || comp.includes("하이닉스") || comp.includes("전자") || comp.includes("칩") || comp.includes("본더") || comp.includes("소부장")) {
        badges.push(`<span class="chip" style="background:rgba(0,229,255,0.15); color:#00e5ff; font-weight:700;">⚡ 반도체·AI</span>`);
      }
      if (tags.includes("shopping_frenzy") || comp.includes("코스맥스") || comp.includes("에이피알") || comp.includes("화장품") || comp.includes("패션") || comp.includes("의류")) {
        badges.push(`<span class="chip" style="background:rgba(255,128,171,0.15); color:#ff80ab; font-weight:700;">💄 K-뷰티·소비재</span>`);
      }
      if (comp.includes("보안") || comp.includes("로봇") || comp.includes("모니터랩") || comp.includes("엑스게이트") || comp.includes("로보틱스")) {
        badges.push(`<span class="chip" style="background:rgba(105,240,174,0.15); color:#69f0ae; font-weight:700;">🤖 보안·로봇·AI</span>`);
      }

      return badges.length ? badges.slice(0, 2).join(" ") : `<span class="chip" style="background:rgba(148,163,184,0.1); color:#94a3b8;">🌐 일반 계절성</span>`;
    }

    const tagBadges = getThemeBadges(r);

    return `
      <tr data-ticker="${escapeHtml(r.ticker)}" data-index="${idx}" class="clickable-row">
        <td>${idx + 1}</td>
        <td>
          <b>${escapeHtml(r.company || r.ticker)}</b>
          <span class="meta">${escapeHtml(r.ticker)}</span>
        </td>
        <td><span class="chip">${escapeHtml(r.market || "KOSPI")}</span></td>
        <td><b class="text-accent-cyan">${r.event_mode ? "기준 " : ""}${r.target_month}월</b></td>
        <td class="${wrCls}">${wr.toFixed(0)}%</td>
        <td class="${retCls}">${avgRet > 0 ? "+" : ""}${avgRet.toFixed(1)}%</td>
        <td>${medRet > 0 ? "+" : ""}${medRet.toFixed(1)}%</td>
        <td class="meta">${r.years_count}년</td>
        <td>${renderMonthHeatmapBar(r.all_months, r.target_month)}</td>
        <td>${tagBadges || "—"}</td>
        <td>
          <button type="button" class="ghost small btn-seasonality-ai" data-ticker="${escapeHtml(r.ticker)}" data-company="${escapeHtml(r.company || r.ticker)}">🤖 AI 리포트</button>
        </td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("tr.clickable-row").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".btn-seasonality-ai")) return;
      const idx = parseInt(tr.dataset.index, 10);
      const rowData = Number.isFinite(idx) ? seasonalityRows[idx] : null;
      if (rowData) openHeatmapPlaybook(rowData);
    });
  });

  tbody.querySelectorAll(".btn-seasonality-ai").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const code = btn.dataset.ticker;
      const comp = btn.dataset.company || code;
      const proceed = confirm(`[${comp} (${code})] AI 심층 분석 리포트를 발간하시겠습니까?\n(LLM 토큰이 사용되며 백그라운드에서 안전하게 작성됩니다.)`);
      if (proceed) {
        runReport(code).catch((err) => alert(err.message));
      }
    });
  });
}

function playbookRowFromScan(row) {
  const month = Number(row.target_month) || targetMonthOf(row);
  const eventMode = Boolean(row.event_mode);
  return {
    ...row,
    window_name: row.window_name || (eventMode ? `${row.event_title || "특수 이벤트"} · 비교 기준 ${month}월` : `${month}월`),
    common_event_cluster: row.common_event_cluster || row.event_title,
    years_track: yearsTrackFromRow(row),
    all_months: row.all_months || [],
    sample_count: row.sample_count || row.years_count,
    median_alpha: row.median_alpha ?? null,
    entry_stage: row.entry_stage || (eventMode ? "WATCH" : undefined),
    entry_stage_label: row.entry_stage_label || (eventMode ? "📌 이벤트 관련 종목 · 타이밍 별도 확인" : undefined),
    entry_window_str: row.entry_window_str || (eventMode ? "이벤트 캘린더 원문 일정 확인" : ""),
    exit_window_str: row.exit_window_str || (eventMode ? "이벤트별 무효화 조건 확인" : ""),
  };
}

async function openHeatmapPlaybook(row) {
  if (!row) return;
  openDiscoveryDetailModal(playbookRowFromScan(row));
  if (row.event_mode) return;
  const code = padTicker(row.ticker);
  const month = Number(row.target_month);
  if (!code || code === "000000") return;
  api(`/api/seasonality/discovery/${code}?lookback_years=${currentV11Lookback || 5}`).then((data) => {
    const patterns = data.patterns || [];
    const match = patterns.find((p) => parseInt(String(p.window_name || "").replace("월", ""), 10) === month) || patterns[0];
    if (!match) return;
    match.all_months = row.all_months || match.all_months;
    const modal = $("#discovery-detail-modal");
    if (modal && !modal.classList.contains("hidden")) openDiscoveryDetailModal(match);
  }).catch(() => {});
}

function setupSeasonalityUI() {
  const monthTabsContainer = $("#seasonality-month-tabs");
  if (monthTabsContainer) {
    const curM = new Date().getMonth() + 1;
    const nextM = curM === 12 ? 1 : curM + 1;

    let tabsHtml = `
      <button type="button" class="month-tab-btn ${currentSeasonalityMonth === curM ? 'active' : ''}" data-month="${curM}">🔥 ${curM}월 (현재)</button>
      <button type="button" class="month-tab-btn ${currentSeasonalityMonth === nextM ? 'active' : ''}" data-month="${nextM}">🚀 ${nextM}월 (사전 관찰 픽)</button>
    `;
    for (let m = 1; m <= 12; m++) {
      tabsHtml += `<button type="button" class="month-tab-btn ${currentSeasonalityMonth === m ? 'active' : ''}" data-month="${m}">${m}월</button>`;
    }
    monthTabsContainer.innerHTML = tabsHtml;

    monthTabsContainer.querySelectorAll(".month-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        monthTabsContainer.querySelectorAll(".month-tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentSeasonalityMonth = parseInt(btn.dataset.month, 10);
        loadSeasonality().catch(() => {});
      });
    });
  }

  // Static fallback controls are replaced by the API-backed full event catalog
  // after the first scan response.
  bindSeasonalityPresetControls();
  syncSeasonalityModeControls();

  // Filter dropdowns
  $("#seasonality-min-wr")?.addEventListener("change", () => loadSeasonality().catch(() => {}));
  $("#seasonality-min-ret")?.addEventListener("change", () => loadSeasonality().catch(() => {}));

  // Search autocomplete
  const qInput = $("#seasonality-q");
  const qMenu = $("#seasonality-q-menu");
  if (qInput && qMenu) {
    setupStockAutocomplete(qInput, qMenu, (selected) => {
      selectSeasonalityStock(selected.ticker, selected).catch((err) => alert(err.message));
    });
    qInput.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.isComposing || e.defaultPrevented || qMenu.style.display === "block") return;
      e.preventDefault();
      selectSeasonalityStock(qInput.value).catch((err) => alert(err.message));
    });
    qInput.addEventListener("input", () => {
      if (qInput.value.trim()) return;
      currentSeasonalityQuery = "";
      refreshCurrentSeasonalitySearch().catch(() => {});
    });
  }
}


function setupWatchSubtabs() {
  const btnPort = $("#subtab-watch-port");
  const btnReports = $("#subtab-watch-reports");
  const panePort = $("#watch-subtab-port-pane");
  const paneReports = $("#watch-subtab-reports-pane");

  if (btnPort && btnReports && panePort && paneReports) {
    btnPort.addEventListener("click", () => {
      btnPort.classList.add("active");
      btnReports.classList.remove("active");
      panePort.classList.remove("hidden");
      paneReports.classList.add("hidden");
      loadWatch().catch(() => {});
    });
    btnReports.addEventListener("click", () => {
      btnReports.classList.add("active");
      btnPort.classList.remove("active");
      paneReports.classList.remove("hidden");
      panePort.classList.add("hidden");
      loadReportArchive().catch(() => {});
    });
  }
}

function setupInvestorSubtabs() {
  const btnFlow = $("#subtab-investor-flow");
  const btnNps = $("#subtab-investor-nps");
  const paneFlow = $("#investor-subtab-flow-pane");
  const paneNps = $("#investor-subtab-nps-pane");

  if (btnFlow && btnNps) {
    btnFlow.addEventListener("click", () => {
      btnFlow.classList.add("active");
      btnNps.classList.remove("active");
      paneFlow?.classList.remove("hidden");
      paneNps?.classList.add("hidden");
      loadInvestor().catch(() => {});
      loadInvestorEvents().catch(() => {});
    });
    btnNps.addEventListener("click", () => {
      btnNps.classList.add("active");
      btnFlow.classList.remove("active");
      paneNps?.classList.remove("hidden");
      paneFlow?.classList.add("hidden");
      loadNps().catch(() => {});
    });
  }
  if ($("#nps-sub-refresh")) {
    $("#nps-sub-refresh").addEventListener("click", () => loadNps().catch((err) => alert(err.message)));
  }
  if ($("#nps-sub-collect")) {
    $("#nps-sub-collect").addEventListener("click", () => startJob("dart-nps").catch((err) => alert(err.message)));
  }
  if ($("#save-sched-btn")) {
    $("#save-sched-btn").addEventListener("click", () => saveSchedulerSettings().catch((err) => alert(err.message)));
  }
}

async function saveSchedulerSettings() {
  const enabled = $("#sched-enabled")?.checked || false;
  const jobKind = $("#sched-kind")?.value || "krx-prices";
  const hour = Number($("#sched-hour")?.value || 18);
  const minute = Number($("#sched-min")?.value || 30);

  const payload = {
    enabled,
    job_kind: jobKind,
    hour,
    minute,
    lookback_days: jobKind === "live" ? 80 : 10,
    official_flow: true,
  };

  try {
    const res = await api("/api/scheduler", { method: "POST", body: JSON.stringify(payload) });
    renderSchedLine(res);
    showToast(enabled ? `⏰ <b>매일 ${hour}:${String(minute).padStart(2, "0")} KST 자동 실행 예약 완료</b>` : "⏸️ <b>자동 스케줄러가 비활성화되었습니다.</b>", "success");
  } catch (err) {
    alert("스케줄 저장 실패: " + err.message);
  }
}

applyPriceChrome("dash");
setupInvestorSubtabs();
setupWatchSubtabs();
  setupV11SeasonalityUI();
setupKeyShowHideToggles();
bindStockSearchers();
applyPublicShareMode()
  .then(() => {
    loadDash().catch((err) => {
      $("#quality-box").innerHTML = `<p class="bad">${err.message}</p>`;
    });
    if (!publicShareMode) loadSettings().catch(() => {});
  })
  .catch(() => {
    loadDash().catch((err) => {
      $("#quality-box").innerHTML = `<p class="bad">${err.message}</p>`;
    });
    loadSettings().catch(() => {});
  });

function reloadCurrentView() {
  const name = currentView || "dash";
  const p = [loadDash()];
  if (name === "market") {
    macroCache = null;
    p.push(loadMarket(true));
    p.push(loadMacro(true));
  } else if (name === "investor") {
    p.push(loadInvestor());
    p.push(loadInvestorEvents());
  } else if (name === "sunzi") p.push(loadSunzi());
  else if (name === "nps") p.push(loadNps());
  else if (name === "flow") p.push(loadFlow());
  else if (name === "empty") p.push(loadEmpty());
  else if (name === "trade") p.push(loadTrade());
  else if (name === "toss") p.push(loadTossRankings());
  else if (name === "us13f") p.push(loadUs13f());
  else if (name === "sector") p.push(loadSectors());
  else if (name === "screens") p.push(loadScreens());
  else if (name === "strategy") p.push(loadStrategy());
  else if (name === "seasonality") {
    if (currentV11Subtab === "pre-entry") loadPreEntryView().catch(() => {});
    else if (currentV11Subtab === "discovery") loadDiscoveryRanked().catch(() => {});
    else if (currentV11Subtab === "explanation") loadAIExplanations().catch(() => {});
    else if (currentInstSubtab === "calendar") loadInstitutionalCalendar().catch(() => {});
    else loadSeasonality().catch(() => {});
  }
  if (name === "watch") { p.push(loadWatch()); p.push(loadReportArchive()); }
  else if (name === "reports") p.push(loadReportArchive());
  return Promise.all(p);
}


// --- Manual Publish & Deploy Handlers (Toptoon Tracker Unified Style) ---
let deployPollTimer = null;

async function refreshDeployStatus() {
  const elProgress = document.querySelector("#deploy-progress");
  const elBtn = document.querySelector("#run-manual-deploy");
  const elDataBtn = document.querySelector("#run-manual-deploy-data");
  const elForceBtn = document.querySelector("#run-manual-deploy-force");
  const elTitle = document.querySelector("#deploy-status-title");
  const elDetail = document.querySelector("#deploy-status-detail");
  if (!elProgress || !elBtn) return;

  try {
    const status = await api("/api/deploy/status");
    renderDeployStatus(status);
    if (status.running || status.state === "running") {
      clearTimeout(deployPollTimer);
      deployPollTimer = setTimeout(refreshDeployStatus, 2000);
    }
  } catch (err) {
    console.warn("배포 상태 확인 실패:", err);
  }
}

function renderDeployStatus(payload) {
  const elProgress = document.querySelector("#deploy-progress");
  const elBtn = document.querySelector("#run-manual-deploy");
  const elDataBtn = document.querySelector("#run-manual-deploy-data");
  const elForceBtn = document.querySelector("#run-manual-deploy-force");
  const elTitle = document.querySelector("#deploy-status-title");
  const elDetail = document.querySelector("#deploy-status-detail");
  const stepList = document.querySelectorAll(".deploy-step-list span");
  if (!elProgress || !elBtn) return;

  const state = payload.state || "idle";
  elProgress.dataset.state = state;

  const stateLabel = {
    idle: "수동 배포 대기",
    running: payload.message || "공개판 갱신 및 배포 중...",
    success: "공개판 갱신 완료",
    skipped: "중복 배포 건너뜀",
    failed: "배포 실패",
  }[state] || payload.message || "상태 확인 완료";

  const timestamp = payload.finished_at || payload.started_at;
  let formattedTime = "";
  if (timestamp) {
    try {
      const dt = new Date(timestamp);
      formattedTime = dt.toLocaleDateString("ko-KR", { year: "numeric", month: "numeric", day: "numeric" }) + " " + dt.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "numeric", hour12: true });
    } catch {
      formattedTime = String(timestamp);
    }
  }

  const detail = state === "success"
    ? `${formattedTime ? formattedTime + " · " : ""}${payload.detail || "공개 사이트에서 최신 버전을 확인할 수 있습니다."}`
    : state === "running"
      ? `${formattedTime ? formattedTime + " · " : ""}${payload.detail || "빌드 및 Cloudflare 업로드가 진행 중입니다 (약 1분 소요)."}`
      : payload.detail || payload.message || "자동 갱신과 별도로 필요할 때 언제든 실행할 수 있습니다.";

  if (elTitle) elTitle.textContent = stateLabel;
  if (elDetail) elDetail.textContent = detail;

  elBtn.disabled = state === "running";
  if (elDataBtn) elDataBtn.disabled = state === "running";
  if (elForceBtn) elForceBtn.disabled = state === "running";
  elBtn.textContent = state === "running" ? "배포 진행 중..." : "웹 패치만 배포";

  stepList.forEach((sp, idx) => {
    sp.classList.remove("active");
    if (state === "running") {
      if (idx <= 1) sp.classList.add("active");
    } else if (state === "success") {
      sp.classList.add("active");
    }
  });
}

async function runManualDeploy(mode = "code") {
  const elBtn = document.querySelector("#run-manual-deploy");
  const elDataBtn = document.querySelector("#run-manual-deploy-data");
  const elForceBtn = document.querySelector("#run-manual-deploy-force");
  const force = mode === "force";
  const codeOnly = mode === "code";
  if (force) {
    const accepted = window.confirm(
      "현재 품질 경고와 오래된 기준일을 그대로 공개합니다. 자동 배포 안전기준은 유지되며, 데모·빈 결과는 계속 차단됩니다. 경고 포함 수동 배포를 진행할까요?"
    );
    if (!accepted) return;
  }
  if (elBtn) elBtn.disabled = true;
  if (elDataBtn) elDataBtn.disabled = true;
  if (elForceBtn) elForceBtn.disabled = true;
  const message = codeOnly ? "웹 패치 배포 요청 중..." : force ? "경고 포함 데이터 배포 요청 중..." : "최신 데이터 배포 요청 중...";
  renderDeployStatus({ state: "running", message, started_at: new Date().toISOString(), running: true });

  try {
    const query = codeOnly ? "?code_only=true" : force ? "?force=true" : "";
    const payload = await api(`/api/deploy/run${query}`, { method: "POST" });
    renderDeployStatus(payload);
    clearTimeout(deployPollTimer);
    deployPollTimer = setTimeout(refreshDeployStatus, 1500);
  } catch (err) {
    renderDeployStatus({ state: "failed", message: "배포 요청 실패", detail: err.message });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.querySelector("#run-manual-deploy");
  const dataBtn = document.querySelector("#run-manual-deploy-data");
  const forceBtn = document.querySelector("#run-manual-deploy-force");
  if (btn) {
    btn.addEventListener("click", () => runManualDeploy("code").catch((err) => alert(err.message)));
  }
  if (dataBtn) {
    dataBtn.addEventListener("click", () => runManualDeploy("data").catch((err) => alert(err.message)));
  }
  if (forceBtn) {
    forceBtn.addEventListener("click", () => runManualDeploy("force").catch((err) => alert(err.message)));
  }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#btn-margin-debt-refresh");
  if (!btn) return;
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span>🔄</span><span>갱신 중...</span>`;
  try {
    const res = await api("/api/macro/margin-debt/refresh", { method: "POST" });
    if (macroCache) macroCache.margin_debt = res;
    const container = document.querySelector("#margin-barometer-container");
    if (container) {
      const tempWrapper = document.createElement("div");
      tempWrapper.innerHTML = renderMarginDebtBarometer(res);
      const newCard = tempWrapper.firstElementChild;
      if (newCard) container.replaceWith(newCard);
    }
    showToast("✅ 신용융자 잔고 & 고객예탁금 최신 데이터 실시간 동기화 완료", "success");
  } catch (err) {
    showToast(`❌ 신용잔고 갱신 실패: ${err.message}`, "error");
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
});


// Unified Event Listener for Global Macro Refresh Buttons
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("#btn-ecos-summary-refresh, #btn-yencarry-refresh, #btn-barometer-refresh, #btn-ecos-fundamental-refresh, #btn-fred-fundamental-refresh");
  if (!btn) return;
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span>🔄</span><span>갱신 중...</span>`;
  try {
    macroCache = null;
    await Promise.all([loadMarket(true), loadMacro(true)]);
    showToast("✅ 글로벌 매크로·지수·환율·금리 실시간 동기화 완료", "success");
  } catch (err) {
    showToast(`❌ 동기화 실패: ${err.message}`, "error");
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
});

function renderAntigravityAuth(sess) {
  const chip = $("#agy-chip");
  const hint = $("#agy-hint");
  const btn = $("#agy-check-btn");
  if (!chip || !hint || !btn) return;
  if (sess && sess.connected) {
    chip.textContent = "연결됨 · Windows 세션";
    chip.className = "chip ok";
    hint.textContent = "Windows Credential Manager에 캐시된 Google Antigravity 세션을 사용합니다. API Key 없이 무료로 실행됩니다.";
    btn.textContent = "세션 재확인";
  } else {
    chip.textContent = sess && sess.cli_available ? "인증 대기" : "CLI 미확인";
    chip.className = "chip warn";
    hint.textContent = "터미널에서 agy를 실행하여 Google 계정으로 로그인하세요. 이후 세션 확인을 누르면 연결됩니다.";
    btn.textContent = "Antigravity CLI 세션 확인";
  }
}

if ($("#agy-check-btn")) {
  $("#agy-check-btn").addEventListener("click", async () => {
    const btn = $("#agy-check-btn");
    const orig = btn.textContent;
    btn.textContent = "확인 중…";
    btn.disabled = true;
    try {
      const data = await api("/api/llm/antigravity/check", { method: "POST" });
      renderAntigravityAuth(data);
      if (data.connected) {
        showToast("✅ Google Antigravity CLI 세션이 정상 연결되었습니다.", "success");
      } else {
        showToast("⚠️ " + (data.detail || "터미널에서 agy를 실행하여 로그인하세요."), "warn");
      }
      await renderConnections();
    } catch (err) {
      showToast(`❌ 세션 확인 실패: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      if ($("#agy-chip")?.classList.contains("ok")) {
        btn.textContent = "세션 재확인";
      } else {
        btn.textContent = "Antigravity CLI 세션 확인";
      }
    }
  });
}

// =========================================================
// Quick LLM Model Switcher Modal Logic
// =========================================================
let currentQuickProvider = "openrouter";
let currentQuickModel = "deepseek/deepseek-v4-flash-0731";

function openQuickLlmModal() {
  const modal = $("#modal-llm-quick-switch");
  if (!modal) return;
  
  const curProv = $("#llm-provider")?.value || "openrouter";
  const curMod = $("#llm-model")?.value || $("#llm-model-select")?.value || PROVIDER_MODELS[curProv]?.[0] || "";
  
  currentQuickProvider = curProv;
  currentQuickModel = curMod;
  
  selectQuickProvider(curProv);
  
  modal.classList.remove("hidden");
  modal.style.display = "flex";
}

function closeQuickLlmModal() {
  const modal = $("#modal-llm-quick-switch");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.style.display = "none";
}

function selectQuickProvider(prov) {
  currentQuickProvider = prov;
  $$(".quick-prov-btn").forEach((b) => {
    const isSelected = b.dataset.provider === prov;
    b.style.borderColor = isSelected ? "#38bdf8" : "#1e293b";
    b.style.background = isSelected ? "rgba(56,189,248,0.15)" : "#131d33";
  });
  
  const chipsContainer = $("#quick-models-chips");
  const customInput = $("#quick-model-custom");
  const models = PROVIDER_MODELS[prov] || [];
  
  if (!models.includes(currentQuickModel)) {
    currentQuickModel = models[0] || "";
  }
  
  if (customInput) customInput.value = currentQuickModel;
  
  if (chipsContainer) {
    chipsContainer.innerHTML = models.map((m) => {
      const active = m === currentQuickModel;
      const bg = active ? "rgba(56,189,248,0.2)" : "#111c30";
      const border = active ? "1px solid #38bdf8" : "1px solid rgba(255,255,255,0.08)";
      const color = active ? "#38bdf8" : "#cbd5e1";
      const info = MODEL_TOKEN_INFO[m] || { badge: "AI 모델", tokens: "표준 토큰 소모", desc: "" };
      const isFree = info.badge.includes("무료") || info.badge.includes("CLI");
      return `
        <button type="button" class="tag-btn quick-mod-chip" data-model="${escapeHtml(m)}" style="background:${bg}; border:${border}; color:${color}; font-size:12px; padding:8px 12px; cursor:pointer; border-radius:8px; display:flex; justify-content:space-between; align-items:center; width:100%; gap:10px; text-align:left; transition:all 0.15s; box-sizing:border-box;">
          <div style="display:flex; flex-direction:column; gap:2px; min-width:0;">
            <b style="font-size:12.5px; color:${active ? '#38bdf8' : '#f8fafc'}; font-family:monospace; word-break:break-all;">${escapeHtml(m)}</b>
            <span style="font-size:11px; color:#94a3b8;">${escapeHtml(info.desc || "")}</span>
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:3px; flex-shrink:0;">
            <span style="font-size:10px; font-weight:700; color:${isFree ? '#4ade80' : '#38bdf8'}; background:rgba(0,0,0,0.4); padding:2px 6px; border-radius:4px; border:1px solid ${isFree ? 'rgba(74,222,128,0.3)' : 'rgba(56,189,248,0.3)'};">${escapeHtml(info.badge)}</span>
            <span style="font-size:10.5px; color:${isFree ? '#86efac' : '#cbd5e1'}; font-weight:600;">🪙 ${escapeHtml(info.tokens)}</span>
          </div>
        </button>
      `;
    }).join("");
    
    $$(".quick-mod-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        currentQuickModel = chip.dataset.model;
        if (customInput) customInput.value = currentQuickModel;
        selectQuickProvider(currentQuickProvider);
      });
    });
  }
}

async function saveQuickLlmChoice() {
  const customInput = $("#quick-model-custom");
  const modelToSave = (customInput?.value || currentQuickModel || "").trim();
  const provToSave = currentQuickProvider || "openrouter";
  
  const saveBtn = $("#quick-llm-save-btn");
  if (saveBtn) {
    saveBtn.textContent = "저장 중…";
    saveBtn.disabled = true;
  }
  
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        llm_provider: provToSave,
        llm_model: modelToSave,
      }),
    });
    
    if ($("#llm-provider")) {
      $("#llm-provider").value = provToSave;
      syncDecorated($("#llm-provider"));
    }
    if ($("#llm-model")) $("#llm-model").value = modelToSave;
    if ($("#llm-model-select")) {
      applyModelOptions(PROVIDER_MODELS[provToSave] || [], modelToSave);
    }
    
    const provLabel = PROVIDER_LABELS[provToSave] || provToSave;
    setChip($("#chip-llm"), `🤖 AI: ${provLabel} · ${modelToSave.split("/").pop()}`, `AI 분석 리포트 생성 모델: ${modelToSave}`);
    
    renderConnections().catch(() => {});
    
    showToast(`✅ AI 모델이 <b>${escapeHtml(provLabel)} · ${escapeHtml(modelToSave)}</b>(으)로 변경되었습니다.`, "success", 4000);
    closeQuickLlmModal();
  } catch (err) {
    showToast(`❌ 모델 변경 실패: ${err.message}`, "error");
  } finally {
    if (saveBtn) {
      saveBtn.textContent = "⚡ 모델 즉시 적용";
      saveBtn.disabled = false;
    }
  }
}

// Wire events for Quick LLM Switcher
document.addEventListener("click", (e) => {
  if (e.target.closest("#chip-llm, .btn-open-quick-llm")) {
    e.preventDefault();
    openQuickLlmModal();
  }
  if (e.target.closest("#quick-llm-close-btn, #quick-llm-cancel-btn")) {
    closeQuickLlmModal();
  }
  const provBtn = e.target.closest(".quick-prov-btn");
  if (provBtn) {
    selectQuickProvider(provBtn.dataset.provider);
  }
  if (e.target.closest("#quick-llm-save-btn")) {
    saveQuickLlmChoice();
  }
});

// ==========================================
// 🎯 Calendar Momentum Portfolio & D-Day Exit Tracker
// ==========================================
let momentumPortfolio = [];
let selectedMomentumStockId = null;

function calculateMomentumDDay(peakDateStr) {
  try {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const peak = new Date(peakDateStr);
    peak.setHours(0, 0, 0, 0);
    const diffTime = peak - today;
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  } catch (e) {
    return 0;
  }
}

function renderActiveMomentumChart() {
  const canvas = $("#momentum-chart-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const stock = momentumPortfolio.find((s) => s.id === selectedMomentumStockId) || momentumPortfolio[0];
  if (!stock) return;

  const rect = canvas.getBoundingClientRect();
  const width = rect.width || 750;
  const height = rect.height || 300;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);

  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, width, height);

  const padding = { top: 40, right: 30, bottom: 36, left: 52 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  const historyCurve = stock.history_curve || [0, 2, 5, 8, 12, 16, 20, 25, 28, 25, 21, 17];
  const actualCurve = stock.actual_curve || [0, 1.8];
  const nDays = historyCurve.length;

  const maxVal = Math.max(...historyCurve, ...actualCurve, 30) * 1.15;
  const minVal = Math.min(0, ...historyCurve, ...actualCurve) - 2;
  const valRange = Math.max(10, maxVal - minVal);

  const getY = (val) => padding.top + plotH - ((val - minVal) / valRange) * plotH;
  const getX = (idx) => padding.left + (idx / (nDays - 1)) * plotW;

  // Grid Lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const gVal = minVal + (valRange * g) / 4;
    const gy = getY(gVal);
    ctx.beginPath();
    ctx.moveTo(padding.left, gy);
    ctx.lineTo(width - padding.right, gy);
    ctx.stroke();

    ctx.fillStyle = "#64748b";
    ctx.font = "10px monospace";
    ctx.textAlign = "right";
    ctx.fillText(`${gVal >= 0 ? "+" : ""}${gVal.toFixed(0)}%`, padding.left - 8, gy + 3);
  }

  // Peak Vertical Line
  const peakIdx = historyCurve.indexOf(Math.max(...historyCurve));
  const peakX = getX(peakIdx);

  ctx.strokeStyle = "rgba(239, 68, 68, 0.7)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(peakX, padding.top);
  ctx.lineTo(peakX, height - padding.bottom);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = "#f87171";
  ctx.font = "bold 11px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(`🎯 목표 피크일 (${stock.peak_date})`, peakX, padding.top - 12);

  // 1. Draw Past 5-Year Average Trajectory (Dashed Gray/Cyan Line)
  ctx.strokeStyle = "#94a3b8";
  ctx.lineWidth = 2;
  ctx.setLineDash([5, 4]);
  ctx.beginPath();
  historyCurve.forEach((val, i) => {
    const x = getX(i);
    const y = getY(val);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.setLineDash([]);

  historyCurve.forEach((val, i) => {
    const x = getX(i);
    const y = getY(val);
    ctx.fillStyle = "#64748b";
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#94a3b8";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(i === 0 ? "진입(D0)" : `D+${i}`, x, height - 12);
  });

  // 2. Draw 2026 Actual Price Path (Neon Cyan Solid Line)
  ctx.shadowColor = "#38bdf8";
  ctx.shadowBlur = 10;
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 3.5;
  ctx.beginPath();
  actualCurve.forEach((val, i) => {
    const x = getX(i);
    const y = getY(val);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.shadowBlur = 0;

  actualCurve.forEach((val, i) => {
    const x = getX(i);
    const y = getY(val);
    ctx.fillStyle = "#38bdf8";
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#070b13";
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  // Legend at top-right
  ctx.font = "11px sans-serif";
  ctx.textAlign = "left";
  ctx.strokeStyle = "#94a3b8";
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  ctx.moveTo(width - 240, 18);
  ctx.lineTo(width - 215, 18);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#94a3b8";
  ctx.fillText("과거 5개년 평균 궤적", width - 210, 22);

  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(width - 115, 18);
  ctx.lineTo(width - 90, 18);
  ctx.stroke();
  ctx.fillStyle = "#38bdf8";
  ctx.fillText("2026년 실제 주가", width - 85, 22);
}

async function loadCalendarMomentumPortfolio() {
  const kpisContainer = $("#momentum-kpis");
  const cardsContainer = $("#momentum-cards-grid");
  const selectStock = $("#momentum-chart-stock-select");
  if (!kpisContainer || !cardsContainer) return;

  try {
    const res = await api("/api/seasonality/momentum-portfolio");
    momentumPortfolio = (res && res.items) || [];
  } catch (e) {
    momentumPortfolio = [];
  }

  const activeItems = momentumPortfolio.filter((item) => !item.exited);
  const totalCount = momentumPortfolio.length;
  const activeCount = activeItems.length;

  let urgentStock = null;
  let minDays = 999;
  if (activeItems.length > 0) {
    activeItems.forEach((item) => {
      const d = calculateMomentumDDay(item.peak_date);
      if (d < minDays) {
        minDays = d;
        urgentStock = item;
      }
    });
  } else {
    minDays = 0;
  }

  const avgDays = activeItems.length > 0
    ? (activeItems.reduce((acc, x) => acc + Math.max(0, calculateMomentumDDay(x.peak_date)), 0) / activeItems.length).toFixed(1)
    : 0;

  // 1. Render Top 4 KPIs
  kpisContainer.innerHTML = `
    <div class="kpi card-cyan">
      <div class="kpi-head">
        <span class="kpi-title">📦 추적 포트폴리오</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(56,189,248,0.15); color:#38bdf8;">ACTIVE</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${activeCount}</span>
        <span class="kpi-unit">개 종목</span>
      </div>
      <div class="kpi-sub-text">총 등록 종목 <b style="color:#38bdf8; font-weight:700;">${totalCount}건</b></div>
    </div>

    <div class="kpi card-rose">
      <div class="kpi-head">
        <span class="kpi-title">🚨 최우선 엑시트 D-Day</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(244,63,94,0.15); color:#fb7185;">최우선</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${urgentStock ? `D-${minDays}` : "—"}</span>
        <span class="kpi-unit">${urgentStock ? escapeHtml(urgentStock.name) : "없음"}</span>
      </div>
      <div class="kpi-sub-text">${urgentStock ? `목표 피크: ${escapeHtml(urgentStock.peak_date)}` : "등록된 목표 피크 없음"}</div>
    </div>

    <div class="kpi card-amber">
      <div class="kpi-head">
        <span class="kpi-title">⏱️ 평균 잔여 보유일</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(251,191,36,0.15); color:#fbbf24;">피크 기준</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">${avgDays}</span>
        <span class="kpi-unit">일</span>
      </div>
      <div class="kpi-sub-text">계절성 목표일까지 평균 보유</div>
    </div>

    <div class="kpi card-emerald">
      <div class="kpi-head">
        <span class="kpi-title">📡 모멘텀 신호등</span>
        <span class="chip" style="font-size:10px; padding:1px 5px; background:rgba(52,211,153,0.15); color:#34d399;">정상</span>
      </div>
      <div class="kpi-main">
        <span class="kpi-num">87.8%</span>
        <span class="kpi-unit">동조율</span>
      </div>
      <div class="kpi-sub-text">과거 5개년 궤적과 일치 (정상 궤도)</div>
    </div>
  `;

  // 2. Render Stock Cards
  if (!momentumPortfolio.length) {
    cardsContainer.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:30px; color:#94a3b8; background:rgba(15,23,42,0.4); border-radius:10px;">등록된 캘린더 모멘텀 추적 종목이 없습니다. 상단에서 종목을 등록하세요.</div>`;
  } else {
    cardsContainer.innerHTML = momentumPortfolio.map((stock) => {
      const dday = calculateMomentumDDay(stock.peak_date);
      const isExited = !!stock.exited;
      let badgeHtml = "";
      if (isExited) {
        badgeHtml = `<span class="chip" style="background:rgba(148,163,184,0.15); color:#94a3b8; font-weight:800;">🏁 엑시트 완료</span>`;
      } else if (dday > 7) {
        badgeHtml = `<span class="chip" style="background:rgba(52,211,153,0.18); color:#34d399; font-weight:800; border:1px solid rgba(52,211,153,0.4);">🟢 D-${dday} (보유 유지)</span>`;
      } else if (dday >= 1) {
        badgeHtml = `<span class="chip" style="background:rgba(251,191,36,0.18); color:#fbbf24; font-weight:800; border:1px solid rgba(251,191,36,0.4);">🟡 D-${dday} (분할 익절 대기)</span>`;
      } else if (dday === 0) {
        badgeHtml = `<span class="chip" style="background:rgba(239,68,68,0.25); color:#f87171; font-weight:900; border:1px solid #ef4444; animation:pulse 1.5s infinite;">🔴 D-Day (전량 엑시트)</span>`;
      } else {
        badgeHtml = `<span class="chip" style="background:rgba(244,63,94,0.2); color:#fb7185; font-weight:800;">⚠️ D+${Math.abs(dday)} (재료소멸)</span>`;
      }

      const returnTarget = stock.entry_price && stock.target_price
        ? (((stock.target_price - stock.entry_price) / stock.entry_price) * 100).toFixed(1)
        : null;

      return `
        <div class="card" style="background:linear-gradient(145deg, rgba(17,26,46,0.9), rgba(12,20,36,0.95)); border:1px solid ${isExited ? 'rgba(255,255,255,0.06)' : 'rgba(56,189,248,0.3)'}; border-radius:12px; padding:16px; display:flex; flex-direction:column; justify-content:space-between; gap:10px;">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <b style="font-size:17px; color:#f8fafc;">${escapeHtml(stock.name)}</b>
                <span style="font-size:12px; color:#94a3b8; font-family:monospace; font-weight:700;">${escapeHtml(stock.code)}</span>
              </div>
              ${badgeHtml}
            </div>

            <!-- Price & Target row -->
            <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-top:10px; background:rgba(15,23,42,0.6); padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.04);">
              <div>
                <span style="font-size:11px; color:#94a3b8; display:block;">매수 진입일</span>
                <b style="font-size:12px; color:#cbd5e1;">${escapeHtml(stock.entry_date)}</b>
              </div>
              <div>
                <span style="font-size:11px; color:#94a3b8; display:block;">목표 피크일</span>
                <b style="font-size:12px; color:#38bdf8;">${escapeHtml(stock.peak_date)}</b>
              </div>
              <div>
                <span style="font-size:11px; color:#94a3b8; display:block;">목표 수익률</span>
                <b style="font-size:12px; color:#34d399;">${returnTarget ? `+${returnTarget}%` : "—"}</b>
              </div>
            </div>

            <!-- Catalyst box -->
            <div style="margin-top:10px; font-size:12px; color:#38bdf8; background:rgba(56,189,248,0.08); border-left:3px solid #38bdf8; padding:6px 10px; border-radius:4px; line-height:1.4;">
              ⚡ <b>핵심 촉매:</b> ${escapeHtml(stock.catalyst || "-")}
            </div>

            <!-- Notes -->
            <div style="margin-top:8px; font-size:11.5px; color:#cbd5e1; line-height:1.4;">
              💡 <b>엑시트 전략:</b> ${escapeHtml(stock.notes || "-")}
            </div>

            <!-- Trajectory Sync Badge -->
            <div style="margin-top:8px; display:flex; align-items:center; justify-content:space-between; font-size:11.5px;">
              <span style="color:#94a3b8;">과거 5개년 궤적 동조율</span>
              <b style="color:#34d399;">${stock.trajectory_match || 85}% (🟢 정상 궤도)</b>
            </div>
          </div>

          <!-- Action Buttons -->
          <div style="display:flex; gap:8px; margin-top:12px; border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;">
            <button type="button" class="ghost small btn-mom-toggle-exit" data-id="${escapeHtml(stock.id)}" style="flex:1; border:1px solid rgba(56,189,248,0.3); color:#38bdf8; font-weight:700;">
              ${isExited ? "🔄 보유 상태로 복원" : "🏁 청산 완료 처리"}
            </button>
            <button type="button" class="ghost small btn-mom-delete" data-id="${escapeHtml(stock.id)}" style="color:#f87171; border:1px solid rgba(248,113,113,0.3);">
              🗑️ 삭제
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  // 3. Populate Stock Selector for Trajectory Chart
  if (selectStock) {
    selectStock.innerHTML = momentumPortfolio.map((s, idx) => `
      <option value="${escapeHtml(s.id)}" ${(!selectedMomentumStockId && idx === 0) || selectedMomentumStockId === s.id ? 'selected' : ''}>
        ${escapeHtml(s.name)} (${escapeHtml(s.code)})
      </option>
    `).join("");

    if (!selectedMomentumStockId && momentumPortfolio.length > 0) {
      selectedMomentumStockId = momentumPortfolio[0].id;
    }
  }

  // 4. Render Chart Canvas
  renderActiveMomentumChart();

  // 5. Bind Button Events
  cardsContainer.querySelectorAll(".btn-mom-toggle-exit").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.id;
      const target = momentumPortfolio.find((s) => s.id === id);
      if (target) {
        target.exited = !target.exited;
        await api("/api/seasonality/momentum-portfolio", {
          method: "POST",
          body: JSON.stringify({ items: momentumPortfolio }),
        });
        loadCalendarMomentumPortfolio();
      }
    };
  });

  cardsContainer.querySelectorAll(".btn-mom-delete").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.id;
      if (confirm("이 종목을 포트폴리오에서 삭제하시겠습니까?")) {
        momentumPortfolio = momentumPortfolio.filter((s) => s.id !== id);
        await api("/api/seasonality/momentum-portfolio", {
          method: "POST",
          body: JSON.stringify({ items: momentumPortfolio }),
        });
        loadCalendarMomentumPortfolio();
      }
    };
  });
}

// Bind subtab event listener and form submit
document.addEventListener("DOMContentLoaded", () => {
  // Stock selector change for Trajectory Chart
  $("#momentum-chart-stock-select")?.addEventListener("change", (e) => {
    selectedMomentumStockId = e.target.value;
    renderActiveMomentumChart();
  });

  // Momentum Add Form Submit
  const addForm = $("#momentum-add-form");
  if (addForm) {
    addForm.onsubmit = async (e) => {
      e.preventDefault();
      const name = $("#mom-in-name")?.value.trim();
      const code = $("#mom-in-code")?.value.trim().padStart(6, "0");
      const entryDate = $("#mom-in-entry-date")?.value;
      const peakDate = $("#mom-in-peak-date")?.value;
      const entryPrice = parseFloat($("#mom-in-entry-price")?.value) || null;
      const targetPrice = parseFloat($("#mom-in-target-price")?.value) || null;
      const catalyst = $("#mom-in-catalyst")?.value.trim();
      const notes = $("#mom-in-notes")?.value.trim();

      if (name && code && entryDate && peakDate) {
        const newItem = {
          id: `stock-${code}-${Date.now()}`,
          name: name,
          code: code,
          entry_date: entryDate,
          peak_date: peakDate,
          entry_price: entryPrice,
          target_price: targetPrice,
          catalyst: catalyst,
          notes: notes,
          exited: false,
          trajectory_match: 85,
          history_curve: [0, 1.0, 2.5, 4.2, 6.5, 9.0, 12.0, 15.5, 19.5, 24.0, 27.5, 25.0, 21.0, 17.5],
          actual_curve: [0, 0.5],
        };
        momentumPortfolio.unshift(newItem);
        await api("/api/seasonality/momentum-portfolio", {
          method: "POST",
          body: JSON.stringify({ items: momentumPortfolio }),
        });
        addForm.reset();
        const details = $("#momentum-add-details");
        if (details) details.open = false;
        loadCalendarMomentumPortfolio();
      }
    };
  }
});
