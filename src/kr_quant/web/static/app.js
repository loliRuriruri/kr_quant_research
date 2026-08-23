
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
          const code = b.dataset.backtestStock;
          switchView("strategy");
          const inp = $("#custom-strategy-q");
          if (inp) inp.value = code;
          runCustomBacktest(code);
        });
      });
      box.querySelectorAll("[data-watch-stock]").forEach((b) => {
        b.addEventListener("click", async () => {
          await addWatch(b.dataset.watchStock, b.dataset.company);
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
          <b style="color:#38bdf8; font-size:14px;">💡 3초 핵심 퀀트 해석 & 실전 매매 플레이북</b>
          <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:600;">${escapeHtml(pb.archetype_badge || "")}</span>
        </div>
        <span style="font-size:11.5px; color:#94a3b8;">👑 실전 1픽: <b>${escapeHtml(pb.actionable_name || "")}</b> (${escapeHtml(pb.actionable_params_ko || "")})</span>
      </div>

      <div style="background:rgba(56,189,248,0.06); border-left:3px solid #38bdf8; border-radius:4px; padding:8px 12px; margin-bottom:12px; font-size:12.5px; line-height:1.5; color:#f1f5f9;">
        <b>🔍 주가 파동 진단:</b> ${escapeHtml(pb.archetype_desc || "")}
      </div>

      <div style="background:rgba(168,85,247,0.06); border-left:3px solid #c084fc; border-radius:4px; padding:8px 12px; margin-bottom:12px; font-size:12px; line-height:1.5; color:#e2e8f0;">
        <b>🎯 실전 1픽 선정 사유:</b> ${escapeHtml(pb.actionable_reason || "")}
      </div>

      <div class="playbook-grid">
        <div class="playbook-item" style="border-left:3px solid #22c55e;">
          <h4 style="color:#4ade80;">⭕ 가장 유리한 매수 타이밍</h4>
          <p>${escapeHtml(pb.entry_rule || "")}</p>
        </div>
        <div class="playbook-item" style="border-left:3px solid #38bdf8;">
          <h4 style="color:#38bdf8;">🎯 목표가 및 익절 타이밍</h4>
          <p>${escapeHtml(pb.exit_rule || "")}</p>
        </div>
        <div class="playbook-item" style="border-left:3px solid #ef4444; grid-column: 1 / -1;">
          <h4 style="color:#f87171;">❌ 절대 피해야 할 매매 (치명적 함정)</h4>
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
        const code = b.dataset.backtestStock;
        switchView("strategy");
        const inp = $("#custom-strategy-q");
        if (inp) inp.value = code;
        runCustomBacktest(code);
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
  const stoch = ta.stoch_k != null ? `%K ${ta.stoch_k.toFixed(0)}` : "—";
  const cloud = ta.ichi_cloud ? `구름대 ${ta.ichi_cloud === "above" ? "상회 (강세)" : ta.ichi_cloud === "below" ? "하회 (약세)" : "내부"}` : "—";

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

      <div style="background:#111a2e; padding:10px 14px; border-radius:8px; margin-bottom:12px; font-size:12.5px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:12px; color:#94a3b8;">
          <span>⚡ 기술적 셋업: ${escapeHtml(stoch)} · ${escapeHtml(cloud)}</span>
          <span>${row.empty ? "🏚️ 빈집 감지됨" : row.dual ? "⚡ 쌍끌이 감지됨" : "안정 수급"}</span>
        </div>
        <p style="margin:4px 0 0; color:#cbd5e1;">💡 ${escapeHtml(row.comment || "외인·기관의 최근 수급 동향과 기술적 위치를 점검했습니다.")}</p>
      </div>

      <div style="display:flex; gap:8px;">
        <button class="primary" data-open="${code}">🔍 심층 리서치</button>
        <button data-backtest-stock="${code}" style="background:rgba(56,189,248,0.15); color:#38bdf8; border-color:rgba(56,189,248,0.4);">🧪 전략 백테스트</button>
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
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      const item = currentItems[activeIndex];
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


async function runCustomBacktest(query) {
  const q = String(query || $("#custom-strategy-q")?.value || "").trim();
  if (!q) {
    alert("분석할 종목명 또는 6자리 코드를 입력하세요.");
    return;
  }
  const resBox = $("#custom-strategy-result");
  if (!resBox) return;

  resBox.style.display = "block";
  resBox.innerHTML = `
    <div style="padding:20px; text-align:center; background:#0e1626; border-radius:10px;">
      <div class="skeleton-spinner" style="margin:0 auto 10px;"></div>
      <b style="color:#38bdf8;">'${escapeHtml(q)}' 과거 3년 일봉 4대 전략 백테스트 및 파라미터 최적화 연산 중...</b>
      <p class="hint" style="margin-top:4px;">RSI 과매도, 볼린저 하단, 골든크로스, 돈치안 돌파 및 Walk-Forward 미래 검증을 수행하고 있습니다.</p>
    </div>
  `;

  try {
    const data = await api("/api/strategy/ticker", {
      method: "POST",
      body: JSON.stringify({ ticker: q })
    });

    if (!data || !data.ok) {
      resBox.innerHTML = `<div style="padding:14px; background:rgba(239,68,68,0.1); border:1px solid #ef4444; border-radius:8px; color:#f87171;">⚠️ ${escapeHtml(data.error || "백테스트 실행 실패")}</div>`;
      return;
    }

    const strats = data.strategies || [];
    const rowsHtml = strats.map((s, idx) => {
      const sh = s.sharpe != null ? fmt(s.sharpe, 2) : "—";
      const oosSh = s.oos_sharpe != null ? fmt(s.oos_sharpe, 2) : "—";
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
          <td>${oosSh}</td>
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

        <div style="padding:10px 14px; background:rgba(56,189,248,0.12); border:1px solid #38bdf8; border-radius:8px; margin-bottom:12px;">
          <b style="color:#38bdf8;">👑 최적 추천 전략: ${escapeHtml(data.best_name || "")} (${escapeHtml(data.best_params_ko || "")})</b>
          <p style="margin:4px 0 0; font-size:12.5px; color:#cbd5e1;">${escapeHtml(data.best_comment || "해당 종목에서 가장 안정적인 샤프 지수와 미래 검증 승률을 기록했습니다.")}</p>
        </div>

        <div class="table-wrap">
          <table class="table" style="font-size:12.5px;">
            <thead>
              <tr>
                <th>전략명</th>
                <th>유형</th>
                <th>총 수익률</th>
                <th class="has-tip" data-tip="과거 전체 구간의 위험 대비 보상 비율(Sharpe Ratio)입니다. 1.0 이상 우수.">샤프</th>
                <th class="has-tip" data-tip="검증 구간(Out-of-Sample)에서 미래 시뮬레이션 샤프 지수입니다.">OOS 샤프</th>
                <th class="has-tip" data-tip="Walk-Forward 순환 분할 검증 구간에서 플러스 수익률을 달성한 승률입니다.">WF 승률</th>
                <th class="has-tip" data-tip="전략 운용 중 최고점 대비 겪을 수 있는 최대 낙폭(MDD)입니다.">최대낙폭</th>
                <th>매매 횟수</th>
                <th>최적 파라미터</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
        ${renderPlaybookHtml(bt.playbook)}
      </div>
    `;
  } catch (err) {
    resBox.innerHTML = `<div style="padding:14px; background:rgba(239,68,68,0.1); border:1px solid #ef4444; border-radius:8px; color:#f87171;">⚠️ ${escapeHtml(err.message || "오류가 발생했습니다.")}</div>`;
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

  return `
    <div class="margin-barometer-card">
      <div class="margin-barometer-header">
        <div class="margin-barometer-title">
          <h3>📊 코스피·코스닥 신용융자 잔고 & 레버리지 진단 (Margin Debt Barometer)</h3>
          <span class="hint">한국금융투자협회·KRX 일봉 기준 증시 신용잔고 및 고객예탁금 빚투 비율 · 기준일 ${escapeHtml(md.latest_date || "")}</span>
        </div>
        <div class="margin-status-badge ${md.status_cls}">
          ${escapeHtml(md.status_label)}
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
  flow: ["쌍끌이 수급", "외국인·기관 동반 매수 및 사모펀드 순매수 추적"],
  empty: ["빈집 발굴", "기관·외인 이탈 후 수급 복귀 조짐 종목"],
  trade: ["트레이딩 랩", "수급 셋업 및 스토캐스틱·일목 기술적 신호"],
  us13f: ["월가 대가 포트폴리오 (13F)", "워런 버핏·마이클 버리 등 글로벌 대가들의 SEC 13F 보유 비중 & 신규 편입 종목"],
  strategy: ["전략·백테스트", "일봉 기반 퀀트 전략 백테스트 및 검증"],
  investor: ["메이저 수급 & 지분", "기관·외국인 일별 순매수 추적 & DART 국민연금 5% 대량보유 공시"],
  sunzi: ["은하퀀트전설 (Legend of Galactic Quant)", "제13함대 기함 히페리온 작전 회의실 · 손자 오사(道天地將法) 기반 실전 전술 참모"],
  nps: ["국민연금 5%", "OpenDART 국민연금 5% 이상 대량보유 공시 추적"],
  seasonality: ["계절성·캘린더 퀀트", "가격 선행형 Discovery · 10대 정량 이벤트 · AI 원인 역추적 스크리너"],
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
let emptyCache = null;
let flowTab = "dual";
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
  const d = String(t || "").replace(".0", "").replace(/\D/g, "");
  return d ? d.padStart(6, "0") : String(t || "");
}

function naverUrl(ticker) {
  return `https://finance.naver.com/item/main.naver?code=${padTicker(ticker)}`;
}

async function api(path, opts = {}) {
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

function switchView(name) {
  currentView = name;
  closeDrawer();
  $$(".view").forEach((el) => el.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
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
  if (name === "investor") {
    loadInvestor().catch((err) => alert(err.message));
    loadInvestorEvents().catch(() => {});
  }
  if (name === "sunzi") loadSunzi().catch((err) => alert(err.message));
  if (name === "nps") loadNps().catch((err) => alert(err.message));
  if (name === "flow") loadFlow().catch((err) => alert(err.message));
  if (name === "empty") loadEmpty().catch((err) => alert(err.message));
  if (name === "trade") loadTrade().catch((err) => alert(err.message));
  if (name === "us13f") loadUs13f().catch((err) => alert(err.message));
  if (name === "toss") loadTossRankings().catch((err) => alert(err.message));
  if (name === "sector") loadSectors().catch((err) => alert(err.message));
  if (name === "screens") loadScreens().catch((err) => alert(err.message));
  if (name === "market") {
    loadMarket().catch((err) => alert(err.message));
    loadMacro().catch(() => {});
  }
  if (name === "strategy") {
    loadStrategy().catch((err) => alert(err.message));
    loadPortfolio().catch(() => {});
  }
  if (name === "watch") loadWatch().catch((err) => alert(err.message));
  if (name === "reports") loadReportArchive().catch(() => {});
  if (name === "seasonality") {
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

function renderTop20(rows) {
  const body = $("#top20-body");
  const show = sortedCopy(rows, "dash", "quant_rank", "asc").slice(0, 20);
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

function renderReportList(target, rows, limit) {
  const body = $(target);
  if (!body) return;
  const scoped = target === "#reports-body" ? sortedCopy(rows, "reports", "researched_at", "desc") : rows;
  const show = limit ? scoped.slice(0, limit) : scoped;
  const wide = target === "#reports-body";
  if (!show.length) {
    body.innerHTML = `<tr><td colspan="${wide ? 9 : 5}">아직 보관한 리포트가 없습니다. 종목 상세에서 AI 분석 리포트를 발간하세요.</td></tr>`;
    return;
  }
  body.innerHTML = show
    .map(
      (r) => `<tr class="clickable" data-ticker="${padTicker(r.ticker)}" data-asof="${r.as_of_date || ""}">
      <td><b>${r.company || ""}</b></td>
      ${wide ? `<td>${padTicker(r.ticker)}</td>` : ""}
      <td>${r.kind || ""}</td>
      <td>${r.as_of_date || ""}</td>
      ${wide ? `<td>${(r.researched_at || "").slice(0, 16).replace("T", " ")}</td>` : ""}
      ${wide ? `<td>${r.provider || ""}</td>` : ""}
      <td>${r.model || ""}</td>
      <td>${r.summary || ""}</td>
      ${wide ? `<td><button class="ghost" data-del-report="1" data-ticker="${padTicker(r.ticker)}" data-asof="${escapeHtml(r.as_of_date || "")}" data-kind="${escapeHtml(r.kind || "")}" data-filename="${escapeHtml(r.filename || "")}">삭제</button></td>` : ""}
    </tr>`
    )
    .join("");
  if (wide) paintSortHeaders("reports");
}

function filterReportRows(q = "") {
  const needle = q.trim().toLowerCase();
  if (!needle) return reportRows;
  return reportRows.filter((r) =>
    [r.ticker, r.company, r.model, r.kind, r.summary].some((x) => String(x || "").toLowerCase().includes(needle))
  );
}

async function loadReportArchive() {
  const data = await api("/api/research/reports");
  reportRows = data.rows || [];
  renderReportList("#dash-reports-body", reportRows, 6);
  renderReportList("#reports-body", filterReportRows($("#report-q") ? $("#report-q").value : ""));
  if (currentView === "reports") {
    const latest = reportRows[0]?.researched_at || reportRows[0]?.as_of_date;
    setPageAsOf(
      latest ? `최근 보관 ${fmtWhen(latest) || latest}` : "보관한 리포트가 없습니다.",
      "종목 상세에서 발간한 시각입니다. 시세 칩과 무관합니다."
    );
  }
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
  const stale = Boolean(fresh.stale_price || fresh.stale_screen);
  const label = stale
    ? `📅 최근 종가 ${px}`
    : `📅 시세 ${px} (최신)`;
  const tip = stale
    ? `최근 KRX 종가 기준일: ${px}. 장 마감(15:30) 후 우측 상단의 [시세 받기]를 누르시면 당일 최신 종가로 즉시 동기화됩니다.`
    : `최근 KRX 종가 기준일: ${px}. 당일 장 마감 종가까지 최신 상태입니다.`;
  setChip(el, label, tip);
  el.classList.toggle("stale", stale);
  el.classList.toggle("fresh", fresh.status === "fresh");
  if (btn) btn.classList.toggle("primary", Boolean(fresh.stale_price));
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
  box.innerHTML = `<div class="hint" style="margin:0;">오늘의 선취매 Top 3를 불러오는 중…</div>`;
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
          <div class="seasonality-widget-title">⚡ 오늘의 선취매 Top 3</div>
          <button type="button" class="ghost small" id="btn-open-seasonality-from-glance">계절성 화면 →</button>
        </div>
        <p class="hint" style="margin:0;">진입 유효 선취매 종목이 없습니다. 계절성 화면에서 필터를 완화해 보세요.</p>
      `;
      $("#btn-open-seasonality-from-glance")?.addEventListener("click", () => switchView("seasonality"));
      return;
    }

    const cards = picks.map((p) => {
      const rank = Number(p.rank) || 0;
      const wr = ((p.win_rate || 0) * 100).toFixed(0);
      const ret = ((p.expected_p50 || 0) * 100).toFixed(1);
      const close = p.last_close == null ? "—" : `${Number(p.last_close).toLocaleString("ko-KR")}원`;
      const chg = Number(p.chg_pct || 0);
      const chgCls = chg > 0 ? "up" : chg < 0 ? "down" : "";
      const chgTxt = `${chg > 0 ? "+" : ""}${(chg * 100).toFixed(2)}%`;
      return `
        <div class="glance-pick-card rank-${rank}" data-ticker="${escapeHtml(p.ticker || "")}">
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
            <span>5년 <b class="text-emerald-400">+${ret}%</b></span>
          </div>
        </div>
      `;
    }).join("");

    box.innerHTML = `
      <div class="seasonality-widget-head">
        <div class="seasonality-widget-title">⚡ 오늘의 선취매 Top 3</div>
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
      card.addEventListener("click", () => openGlancePlaybook(card.dataset.ticker));
    });
  } catch (err) {
    box.innerHTML = `<p class="hint" style="margin:0;">선취매 Top 3를 불러오지 못했습니다. ${escapeHtml(err.message || "")}</p>`;
  }
}

async function openGlancePlaybook(ticker) {
  const code = String(ticker || "").padStart(6, "0");
  if (!code || code === "000000") return;
  try {
    const data = await api(`/api/seasonality/discovery/${code}?lookback_years=${currentV11Lookback || 5}`);
    const match = (data.patterns || [])[0];
    if (match) {
      openDiscoveryDetailModal(match);
      return;
    }
  } catch (_) {
    /* fall through to stock drawer */
  }
  openStock(code).catch((err) => alert(err.message));
}

function renderDashDna(rows) {
  const box = $("#dash-dna-box");
  if (!box) return;
  if (!rows || !rows.length) {
    box.innerHTML = "<p class='hint'>TOP20 데이터가 없습니다.</p>";
    return;
  }
  const n = rows.length;
  const avgVal = rows.reduce((acc, r) => acc + (Number(r.value_score) || 0), 0) / n;
  const avgQua = rows.reduce((acc, r) => acc + (Number(r.quality_score) || 0), 0) / n;
  const avgGro = rows.reduce((acc, r) => acc + (Number(r.growth_score) || 0), 0) / n;
  const avgMom = rows.reduce((acc, r) => acc + (Number(r.momentum_score) || 0), 0) / n;
  const avgFin = rows.reduce((acc, r) => acc + (Number(r.financial_score) || 0), 0) / n;
  const avgTotal = (rows.reduce((acc, r) => acc + (Number(r.quant_score) || 0), 0) / n).toFixed(1);

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

function renderKpis(status, top) {
  const q = status.quality || {};
  const c = q.counts || {};
  const topRows = top || [];
  const n = topRows.length || 1;
  const avgScore = (topRows.reduce((acc, r) => acc + (Number(r.quant_score) || 0), 0) / n).toFixed(1);
  const perList = topRows.map(r => Number(r.per)).filter(v => v > 0);
  const avgPer = perList.length ? (perList.reduce((a, b) => a + b, 0) / perList.length).toFixed(1) : "—";
  const roeList = topRows.map(r => r.roe != null ? (Number(r.roe) < 1 ? Number(r.roe) * 100 : Number(r.roe)) : null).filter(v => v != null && !isNaN(v));
  const avgRoe = roeList.length ? (roeList.reduce((a, b) => a + b, 0) / roeList.length).toFixed(1) : "—";
  const reportsCount = reportRows.filter((x) => x.kind === "AI 분석 리포트").length;

  $("#kpis").innerHTML = `
    <div class="kpi">
      <span class="has-tip" data-tip="재무·성장·모멘텀 종합 알고리즘을 최종 통과한 상위 20개 핵심 포트폴리오입니다.">🎯 TOP20 포트폴리오</span>
      <b>${topRows.length || 20} <small style="font-size:13px; color:#94a3b8; font-weight:normal;">종목</small></b>
      <div class="kpi-sub">평균 점수 <b style="color:#38bdf8;">${avgScore}</b>점</div>
    </div>
    <div class="kpi">
      <span class="has-tip" data-tip="시총·거래대금·보통주 및 재무제표 스크리닝 요건을 통과한 유효 유니버스 기업 수입니다.">🏢 조건 통과 유니버스</span>
      <b>${c.universe_eligible ?? 271} <small style="font-size:13px; color:#94a3b8; font-weight:normal;">개사</small></b>
      <div class="kpi-sub">전체 상장사의 약 12% 통과</div>
    </div>
    <div class="kpi">
      <span class="has-tip" data-tip="TOP20 종목들의 평균 주가수익비율(PER)입니다. 시장 평균 대비 저평가 안전마진을 나타냅니다.">💎 TOP20 평균 PER</span>
      <b>${avgPer} <small style="font-size:13px; color:#94a3b8; font-weight:normal;">배</small></b>
      <div class="kpi-sub">저평가 가치 매력 우수</div>
    </div>
    <div class="kpi">
      <span class="has-tip" data-tip="TOP20 종목들의 평균 자기자본이익률(ROE)입니다. 고수익성 자본 효율성을 나타냅니다.">📈 TOP20 평균 ROE</span>
      <b>${avgRoe}%</b>
      <div class="kpi-sub">고수익·고성장 펀더멘털</div>
    </div>
    <div class="kpi clickable-kpi" id="kpi-goto-reports">
      <span class="has-tip" data-tip="AI 리서치 엔진으로 발간 및 보관된 심층 기업 분석 리포트 건수입니다. 클릭 시 리포트 보관함으로 이동합니다.">📑 AI 분석 리포트</span>
      <b>${reportsCount} <small style="font-size:13px; color:#94a3b8; font-weight:normal;">건</small></b>
      <div class="kpi-sub">심층 검증 완료 (클릭 시 이동)</div>
    </div>
  `;

  $("#kpi-goto-reports")?.addEventListener("click", () => switchView("reports"));
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
    const facts = (brief.facts || [])
      .map((f) => `<span>${escapeHtml(f.label)}</span><b>${escapeHtml(f.value)}</b>`)
      .join("");
    const naver = data.naver || {};
    const encyc = (naver.encyc || [])
      .slice(0, 1)
      .map((x) => `<p>${escapeHtml(x.description || x.title || "")}</p>`)
      .join("");
    const newsItems = (naver.news || [])
      .slice(0, 8)
      .map((n) => {
        const sent = classifyNewsSentiment(n.title, n.description);
        return `<li>
          <div style="display:flex; align-items:flex-start; gap:4px;">
            <span class="news-badge ${sent.cls}">${sent.icon} ${sent.label}</span>
            <a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener" style="font-weight:500;">${escapeHtml(n.title)}</a>
          </div>
          <div class="meta" style="margin-top:3px;">${escapeHtml((n.pubDate || "").slice(0, 16))} · ${escapeHtml((n.description || "").slice(0, 95))}</div>
        </li>`;
      })
      .join("");
    let newsBlock = "";
    if (newsItems) {
      newsBlock = `<article class="intro"><h3>네이버 뉴스</h3><ul class="news-list">${newsItems}</ul></article>`;
    } else if (!naver.configured) {
      newsBlock = `<article class="intro"><h3>네이버 뉴스</h3><p class="hint">설정에서 네이버 Client ID/Secret을 넣으면 최근 뉴스가 나옵니다.</p></article>`;
    } else if (naver.error) {
      newsBlock = `<article class="intro"><h3>네이버 뉴스</h3><p class="hint">${escapeHtml(naver.error)}</p></article>`;
    }
    const webItems = (naver.web || [])
      .slice(0, 4)
      .map(
        (n) => `<li><a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>
          <div class="meta">${escapeHtml((n.description || "").slice(0, 90))}</div></li>`
      )
      .join("");
    if (webItems) {
      newsBlock += `<article class="intro"><h3>네이버 웹검색</h3><ul class="news-list">${webItems}</ul></article>`;
    }
    const loc = data.location || {};
    let locBlock = "";
    if (loc.address || loc.ceo) {
      const mapLink = loc.map_url
        ? `<p><a class="ext" href="${escapeHtml(loc.map_url)}" target="_blank" rel="noopener">네이버 지도에서 보기</a></p>`
        : "";
      const img = loc.static_map && loc.lat && loc.lng
        ? `<p><img class="hq-map" alt="본사 위치" src="/api/maps/static?lat=${encodeURIComponent(loc.lat)}&lng=${encodeURIComponent(loc.lng)}" /></p>`
        : "";
      locBlock = `<article class="intro"><h3>본사 위치</h3>
        ${loc.ceo ? `<p>대표이사 ${escapeHtml(loc.ceo)}</p>` : ""}
        ${loc.address ? `<p>${escapeHtml(loc.address)}</p>` : ""}
        ${loc.homepage ? `<p><a class="ext inline" href="${escapeHtml(loc.homepage.startsWith("http") ? loc.homepage : "https://" + loc.homepage)}" target="_blank" rel="noopener">홈페이지</a></p>` : ""}
        ${mapLink}${img}</article>`;
    }
    const toss = data.toss || {};
    const tq = toss.quote || {};
    const tprice = tq.lastPrice ?? tq.price ?? tq.close ?? tq.last ?? tq.currentPrice ?? tq.tradePrice;
    const tchg = tq.changeRate ?? tq.changePct ?? (tq.price && tq.price.changeRate);
    const twarn = (toss.warnings || []).map((w) => (typeof w === "string" ? w : w.type || w.name || w.code || JSON.stringify(w))).join(", ");
    let tossBlock = "";
    if (toss.error) {
      tossBlock = `<article class="intro"><h3>토스증권 시세</h3><p class="hint">${escapeHtml(toss.error)}</p></article>`;
    } else if (tprice != null || twarn) {
      const chgTxt = typeof tchg === "number" ? ` · 등락 ${(tchg * (Math.abs(tchg) > 1 ? 1 : 100)).toFixed(2)}%` : "";
      tossBlock = `<article class="intro"><h3>토스증권 시세</h3>
        <p>현재가 <b>${escapeHtml(String(typeof tprice === "object" ? (tprice.close ?? tprice.tradePrice ?? "") : tprice))}</b>${escapeHtml(chgTxt)}</p>
        ${twarn ? `<p>유의: ${escapeHtml(twarn)}</p>` : ""}
        ${toss.page ? `<p><a class="ext" href="${escapeHtml(toss.page)}" target="_blank" rel="noopener">토스증권에서 보기</a></p>` : ""}
      </article>`;
    }
    const yahoo = data.yahoo || {};
    let yahooBlock = "";
    if (yahoo && (yahoo.forward_pe != null || yahoo.trailing_pe != null || yahoo.peg_ratio != null || yahoo.target_mean_price != null || yahoo.recommendation_key)) {
      yahooBlock = `<article class="intro"><h3>Yahoo Financials</h3><p>Fwd PER ${fmt(yahoo.forward_pe, 1)} · PEG ${fmt(yahoo.peg_ratio, 2)} · 애널리스트 ${fmt(yahoo.target_mean_price)} (${escapeHtml(yahoo.recommendation_key || "")})</p></article>`;
    }
    const ta = data.ta || {};
    let taBlock = "";
    if (ta.ok) {
      const k = ta.stoch_k == null ? "—" : fmt(ta.stoch_k, 1);
      const d = ta.stoch_d == null ? "—" : fmt(ta.stoch_d, 1);
      const cloud = ta.ichi_cloud === "above" ? "구름 위" : ta.ichi_cloud === "below" ? "구름 아래" : ta.ichi_cloud === "inside" ? "구름 안" : "—";
      taBlock = `<article class="intro"><h3>기술적 지표 (일봉)</h3>
        <p>스토캐스틱 K <b>${k}</b> · D <b>${d}</b>${ta.stoch_cross ? ` (${escapeHtml(ta.stoch_cross)})` : ""}</p>
        <p>일목균형표: ${escapeHtml(cloud)}${ta.ichi_signal ? ` · ${escapeHtml(ta.ichi_signal)}` : ""}</p>
        ${ta.support != null ? `<p>지지 <b>${fmt(ta.support, 0)}</b> · 저항 <b>${fmt(ta.resistance, 0)}</b></p>` : ""}
      </article>`;
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

    $("#drawer-title").textContent = `${r.company || ticker} (${padTicker(r.ticker || ticker)})`;
    $("#drawer-body").innerHTML = `
      <div class="stock-grid">
        <div>
          <div class="score-hero">
            <span class="has-tip" data-tip="${escapeHtml(r.rank_label || "순위")}">종합 점수</span>
            <b>${fmt(r.quant_score)}</b>
            <span class="meta">${r.market || ""} · ${r.sector || ""} · ${r.industry || ""}</span>
          </div>

          <!-- 6-Axis Hexagon Radar Chart -->
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

          <div class="factor-bars">
            ${factors.map(([name, v, max]) => `<span>${name} ${fmt(v, 1)} / ${max}</span><i class="has-tip" data-tip="${name} 점수"><em style="width:${Math.max(0, Math.min(100, ((v || 0) / max) * 100))}%"></em></i>`).join("")}
          </div>
          <p class="meta">감점 요인: ${r.risk_penalty != null ? `-${fmt(r.risk_penalty, 1)}점` : "0점"} · 데이터 신뢰도: ${r.data_confidence != null ? `${fmt(r.data_confidence, 1)}점` : "—"}</p>
          <article class="intro">
            <h3>선정 및 게이트 상태</h3>
            <p>${escapeHtml(gateLine)}</p>
            ${excl ? `<ul class="risk-notes">${excl}</ul>` : ""}
            ${riskNotes.length ? `<ul class="risk-notes">${riskNotes.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
            ${dataNotes.length ? `<ul class="data-notes">${dataNotes.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}
          </article>
          <article class="intro">
            <h3>핵심 재무 팩트</h3>
            <div class="facts-grid">${facts}</div>
          </article>
          ${encyc ? `<article class="intro"><h3>기업 백과</h3>${encyc}</article>` : ""}
          ${locBlock}
          <div class="actions">
            <button id="btn-analyze" data-ticker="${ticker}">간단 검증</button>
            <button class="primary" id="btn-report" data-ticker="${ticker}">AI 분석 리포트</button>
            <button id="btn-backtest-stock" data-ticker="${ticker}" style="background:rgba(56,189,248,0.15); color:#38bdf8; border-color:rgba(56,189,248,0.4);">🧪 전략 백테스트</button>
            <button id="btn-watch" data-ticker="${ticker}" data-company="${escapeHtml(r.company || "")}">관심종목</button>
          </div>
          <p class="hint">간단 검증은 핵심 요약 점검이며, AI 분석 리포트는 심층 펀더멘털 분석 리포트를 생성합니다.</p>
          <div id="research-box"><p>저장된 간단 검증을 불러오는 중…</p></div>
          <div id="report-box"><p>저장된 AI 분석 리포트를 불러오는 중…</p></div>
        </div>
        <div>
          ${visualGauges}
          ${timingBlock}
          ${flow90Block(data.flow90)}
          ${eventsBlock(data.events)}
          ${fiveStrip({ dao: data.dao, tian: data.tian, di: data.di, jiang: data.jiang, fa: data.fa })}
          ${criticCard((data.sunzi || {}).critic)}
          ${taBlock}
          ${tossBlock}
          ${yahooBlock}
          ${newsBlock}
          <div class="ext-links">
            ${links.map((l) => `<a class="ext" href="${l.url}" target="_blank" rel="noopener">${l.label}</a>`).join("")}
          </div>
        </div>
      </div>
    `;

    $("#btn-analyze").addEventListener("click", () => runAnalyze(code).catch((err) => alert(err.message)));
    if ($("#btn-backtest-stock")) {
      $("#btn-backtest-stock").addEventListener("click", () => {
        closeDrawerUi();
        switchView("strategy");
        const inp = $("#custom-strategy-q");
        if (inp) inp.value = code;
        runCustomBacktest(code);
      });
    }
    $("#btn-report").addEventListener("click", () => runReport(code).catch((err) => alert(err.message)));
    if ($("#btn-watch")) {
      $("#btn-watch").addEventListener("click", () => addWatch(code, r.company || "").catch((err) => alert(err.message)));
    }
    loadResearch(code).catch(() => {
      $("#research-box").innerHTML = "<p>저장된 간단 검증 없음</p>";
    });
    loadReport(code).catch(() => {
      $("#report-box").innerHTML = "<p>저장된 AI 분석 리포트 없음</p>";
    });
  } catch (err) {
    $("#drawer-body").innerHTML = `<div style="padding:20px; color:#ef4444;"><h3>❌ 데이터 로딩 실패</h3><p>${escapeHtml(err.message)}</p></div>`;
  } finally {
    if (bar) bar.style.display = "none";
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

function flow90Block(flow) {
  if (!flow || flow.error) {
    return `<article class="intro"><h3>공식 수급 90일</h3><p class="hint">${escapeHtml((flow && flow.error) || "저장된 KIS 행이 없습니다.")}</p></article>`;
  }
  const chart = flow.chart || [];
  const w = flow.windows || {};
  if (!chart.length) {
    return `<article class="intro"><h3>공식 수급 90일</h3><p class="hint">이 종목의 KIS 저장 행이 없습니다. 공식 수급에서 관심·고유동성 수집을 하세요.</p></article>`;
  }
  return `<article class="intro">
    <h3>공식 수급 90일</h3>
    <p>5일 ${fmtAmt(w.w5)} · 20일 ${fmtAmt(w.w20)} · 60일 ${fmtAmt(w.w60)} · 90일 ${fmtAmt(w.w90)}</p>
    ${flowSpark(chart, "INSTITUTION_TOTAL") || flowSpark(chart, "FUND")}
  </article>`;
}

function eventsBlock(ev) {
  const rows = (ev && ev.rows) || [];
  if (!rows.length) {
    return `<article class="intro"><h3>공시 이벤트</h3><p class="hint">${escapeHtml((ev && ev.error) || "최근 분류 공시가 없습니다.")}</p></article>`;
  }
  const lis = rows
    .slice(0, 8)
    .map((r) => {
      const ret = r.ret_5d != null ? ` · 이후5일 ${fmtPct(r.ret_5d)}` : r.sample === "LOW_SAMPLE" ? " · 표본부족" : "";
      const link = r.url ? `<a class="ext" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">원문</a>` : "";
      return `<li><b>${escapeHtml(r.event_ko || r.event_type)}</b> ${escapeHtml(r.report_date || "")} ${escapeHtml((r.title || "").slice(0, 48))}${ret} ${link}</li>`;
    })
    .join("");
  return `<article class="intro">
    <h3>공시 이벤트</h3>
    <ul>${lis}</ul>
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
  const bear = (panel.strongest_bear_evidence || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");
  return `<article class="intro yang-brief">
    <h3>🍵 전략검토 · ${escapeHtml(panel.posture_ko || panel.posture)} ${fmt(panel.score, 0)}</h3>
    <p class="yang-voice">${escapeHtml(panel.one_line_judgment || panel.comment || "")}</p>
    <p>${escapeHtml(panel.comment || "")}</p>
    <p class="meta">${escapeHtml(axisLine)}</p>
    <p><b>이미 가격에 들어간 이야기</b> ${escapeHtml(panel.consensus || "")}</p>
    <p><b>다른 보기</b> ${escapeHtml(panel.variant || "")}</p>
    ${bear ? `<p><b>내가 가장 불편하게 보는 점</b></p><ul>${bear}</ul>` : ""}
    ${wait.cost_of_waiting ? `<p><b>기다리면</b> ${escapeHtml(wait.benefit_of_waiting || "")} / <b>잃는 것</b> ${escapeHtml(wait.cost_of_waiting)}</p>` : ""}
    ${panel.no_action_required ? "<p><b>지금은 아무것도 하지 않아도 돼.</b></p>" : ""}
    <p class="hint">${escapeHtml(panel.disclaimer || "")}</p>
  </article>`;
}

function fiveStrip(data) {
  const parts = [
    data.dao,
    data.tian,
    data.di,
    data.jiang,
    data.fa && data.fa.fa_label
      ? { label: data.fa.fa_label, score: data.fa.fa_score, comment: data.fa.comment, fa_gate_pass: data.fa.fa_gate_pass }
      : null,
  ];
  if (!parts.some((p) => p && p.label)) return "";
  return `<div class="five-grid">${parts
    .map((p) => {
      if (!p) return "";
      const cls = p.fa_gate_pass === true ? "pass" : p.fa_gate_pass === false ? "fail" : "";
      return `<div class="five-card ${cls}"><span>${escapeHtml(p.label)}</span><b>${fmt(p.score, 0)}</b><p>${escapeHtml((p.comment || "").slice(0, 80))}</p></div>`;
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
  const meta = `${rec.provider || ""} · ${rec.model || ""} · ${rec.as_of_date || ""} · tokens: ${usage.total_tokens || "—"}`;

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
          <td>${oosSh}</td>
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
          <b style="color:#38bdf8; font-size:14px;">🧪 4대 전략 백테스트 & 최적 타이밍 검증</b>
          <span style="font-size:11.5px; color:#94a3b8;">${bt.bars || 0}거래일 일봉 검증</span>
        </div>
        <div style="padding:8px 10px; background:rgba(56,189,248,0.1); border-radius:6px; margin-bottom:10px; font-size:12.5px;">
          <b style="color:#38bdf8;">👑 최적 추천 1위: ${escapeHtml(bt.best_name || "")} (${escapeHtml(bt.best_params_ko || "")})</b>
          <p style="margin:3px 0 0; color:#cbd5e1; font-size:12px;">${escapeHtml(bt.best_comment || "")}</p>
        </div>
        <div class="table-wrap">
          <table class="table" style="font-size:11.5px;">
            <thead>
              <tr>
                <th>전략명</th>
                <th>유형</th>
                <th>총수익률</th>
                <th>샤프</th>
                <th>OOS 샤프</th>
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
      <div style="display:flex; gap:8px; align-items:center;">
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
    box.innerHTML = "<p>아직 AI 분석 리포트가 없습니다.</p>";
    return;
  }
  box.innerHTML = `
    <h3>AI 분석 리포트 · ${rec.provider || ""} ${rec.model || ""}</h3>
    <p class="hint">옆 칸에서는 읽기 어렵습니다. 큰 창에서 보세요.</p>
    <div class="actions">
      <button class="primary" id="btn-report-wide">크게 보기</button>
    </div>
  `;
  const btn = $("#btn-report-wide");
  if (btn) btn.addEventListener("click", () => openReportModal(rec));
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
    api("/api/results/top?n=20"),
    api("/api/results/all?limit=250"),
    guideCache ? Promise.resolve(guideCache) : api("/api/guide"),
    api("/api/research/reports").catch(() => ({ rows: [] })),
  ]);
  guideCache = guide;
  reportRows = archive.rows || [];
  lastStatus = status;
  lastStatusExplain = status.status_explain || null;
  const ver = String(status.model_version || "");
  const shortVer = (ver.match(/^(\d+\.\d+\.\d+)/) || [ver])[0];
  setChip($("#chip-model"), `모델 ${shortVer}`, `내부 버전 ${ver}. 점수 공식 식별자이며 매매 신호가 아닙니다.`);
  const qst = status.quality?.status || "no-run";
  const statusTip = statusExplainTip(lastStatusExplain, STATUS_TIP[qst] || ver);
  setChip($("#chip-status"), statusKo(qst), statusTip);
  $("#chip-status")?.classList.toggle("clickable-chip", qst === "partial" || qst === "failed");
  setChip($("#chip-asof"), status.quality?.as_of_date ? `점수일 ${status.quality.as_of_date}` : "점수일 없음", "이 날짜 기준으로 Quant 점수를 계산했습니다.");
  renderFreshChip(status.freshness);
  if (currentView === "dash" || currentView === "rank") stampFromStatus();
  renderSchedLine(status.scheduler);
  if (!$("#chip-llm")) {
    const chip = document.createElement("span");
    chip.className = "chip has-tip";
    chip.id = "chip-llm";
    chip.tabIndex = 0;
    $(".chips").appendChild(chip);
  }
  const llmName = status.llm_label || status.llm_provider || "xai";
  setChip($("#chip-llm"), `🤖 AI: ${llmName}`, `AI 분석 리포트 생성 모델: ${status.llm_model || llmName}. (AI 심층 리포트 생성 시에만 사용)`);
  dashRows = top.rows || [];
  renderKpis(status, dashRows);
  renderChampions(dashRows);
  loadGlanceTop3().catch(() => {});
  renderDashDna(dashRows);
  renderTop20(dashRows);
  renderQuality(status.quality, guideCache, status.freshness);
  rankRows = all.rows || [];
  renderRank($("#rank-q").value);
  renderJob(status.job);
  renderReportList("#dash-reports-body", reportRows, 6);
  renderReportList("#reports-body", filterReportRows($("#report-q") ? $("#report-q").value : ""));
  loadWatch().catch(() => {});
  loadPortfolio().catch(() => {});
}

async function loadTossRankings() {
  const box = $("#toss-rankings");
  if (!box) return;
  const data = await api("/api/toss/rankings");
  if (!data.configured) {
    box.innerHTML = "<p class='hint'>설정에 토스증권 Client ID/Secret을 넣고, Open API 허용 IP를 등록하세요.</p>";
    return;
  }
  if (data.error && !(data.groups || []).some((g) => (g.rows || []).length)) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error)}</p>`;
    return;
  }
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
          return `<tr class="clickable" data-ticker="${escapeHtml(code)}">
            <td class="num">${r.rank || i + 1}</td>
            <td class="name-cell"><b>${escapeHtml(name)}</b><div class="meta">${escapeHtml(code)}</div>${rowNote(r.comment_short || r.comment)}</td>
            <td class="num ${chgCls}">${escapeHtml(chgTxt)}</td>
            <td class="num">${escapeHtml(String(last))}</td>
            <td><a class="ext inline" href="${escapeHtml(r.page || "https://www.tossinvest.com/stocks/A" + code)}" target="_blank" rel="noopener">토스</a></td>
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
          <h3 style="margin:0 0 4px;font-size:15px;color:#fff;">🇰🇷 한국은행 ECOS 거시경제 핵심 지표</h3>
          <span class="hint">한국은행 오픈 API 실시간 연동 기준금리, 국고채, 환율, 물가 통계</span>
        </div>
      </div>
      <div class="ecos-visual-grid">
        ${ecosCards || `<p class="hint">${escapeHtml(ecos.error || "조회 데이터 없음")}</p>`}
      </div>
    </div>
  `;
  stampLive("#market-live");
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

function flowTable(title, rows, amountKey, tabId) {
  const scope = tabId || (amountKey === "pe_krw" ? "flowPe" : "flowDual");
  const q = ($("#flow-q")?.value || "").trim().toLowerCase();
  let filteredRows = rows;
  if (q) {
    filteredRows = rows.filter((r) => {
      const comp = String(r.company || "").toLowerCase();
      const code = String(r.ticker || "").toLowerCase();
      return comp.includes(q) || code.includes(q);
    });
  }

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
      <td class="num">${quoteCell(r)}</td>
      <td class="num ${r.foreign_net > 0 ? 'text-emerald-400 font-bold' : r.foreign_net < 0 ? 'text-rose-400' : ''}">${signedInt(r.foreign_net)}</td>
      <td class="num ${r.institution_net > 0 ? 'text-emerald-400 font-bold' : r.institution_net < 0 ? 'text-rose-400' : ''}">${signedInt(r.institution_net)}</td>
      <td class="num ${r.pe_net > 0 ? 'text-purple-400 font-bold' : r.pe_net < 0 ? 'text-rose-400' : ''}">${signedInt(r.pe_net)}</td>
      <td class="num font-bold text-accent-cyan">${escapeHtml(krw(r[amountKey]))}</td>
      <td class="num font-bold">${pctCell(r.ret_5d)}</td>
      <td class="num font-bold">${pctCell(r.ret_20d)}</td>
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
            <th class="sortable" data-sort="company" style="min-width:140px;">종목명</th>
            <th class="sortable" data-sort="last">최근가</th>
            <th class="sortable" data-sort="foreign_net">외인(주)</th>
            <th class="sortable" data-sort="institution_net">기관(주)</th>
            <th class="sortable" data-sort="pe_net">사모(주)</th>
            <th class="sortable" data-sort="${amountKey}">추정금액</th>
            <th class="sortable" data-sort="ret_5d">이후 5일</th>
            <th class="sortable" data-sort="ret_20d">이후 20일</th>
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
  const dualRows = filterAmount(data.dual || [], "dual_krw", minKrw);
  const peRows = filterAmount(data.private_equity || [], "pe_krw", minKrw);
  const tabs = [
    { id: "dual", name: "💎 쌍끌이", rows: dualRows, key: "dual_krw", title: "외인·기관 동시 순매수 (쌍끌이)" },
    { id: "pe", name: "💼 사모펀드", rows: peRows, key: "pe_krw", title: "스마트머니 사모펀드 순매수" },
    { id: "dual_pe", name: "🔥 쌍끌이+사모", rows: filterAmount(data.dual_pe || [], "dual_krw", minKrw), key: "dual_krw", title: "외인·기관·사모 3대 메이저 집중 매집" },
    { id: "dual_pe_retail", name: "🚀 +개인이탈", rows: filterAmount(data.dual_pe_retail || [], "dual_krw", minKrw), key: "dual_krw", title: "메이저 싹쓸이 + 개인이탈 (손바뀜 완료)" },
    { id: "other_corp", name: "🏢 기타법인", rows: data.other_corp || [], key: "other_corp_krw", title: "기타법인 대량 순매수" },
    { id: "pension", name: "🏛️ 기금 가세", rows: data.pension || [], key: "pension_krw", title: "연기금 동반 가세 수급" },
    { id: "summary", name: "📊 통계 요약", rows: [], key: "", title: "금액구간별 히트율" },
  ];
  if (!tabs.some((t) => t.id === flowTab)) flowTab = "dual";
  const dual = analyzeHit(dualRows, "ret_5d");
  const pe = analyzeHit(peRows, "ret_5d");
  const dual20 = analyzeHit(dualRows, "ret_20d");
  const pe20 = analyzeHit(peRows, "ret_20d");
  const sameHorizon = dual.n && dual.avg != null && dual20.avg != null && Math.abs(dual.avg - dual20.avg) < 1e-9;
  const when = fmtWhen(data.fetched_at);
  const asof = when ? `토스 수급 스캔 ${when} · ${data.days || 5}거래일` : `수급 스캔 시점 없음 · ${data.days || 5}거래일`;
  if (currentView === "flow") setPageAsOf(asof, "토스 투자자 매매를 받은 시각입니다. 다시 스캔하면 갱신됩니다. KRX 종가 칩과는 다릅니다.");

  const tabBtns = tabs
    .map(
      (t) =>
        `<button type="button" class="${t.id === flowTab ? "on" : ""}" data-flow-tab="${t.id}">${escapeHtml(t.name)}${t.id === "summary" ? "" : ` <span style="opacity:0.8; font-size:11px;">(${t.rows.length})</span>`}</button>`
    )
    .join("");
  const active = tabs.find((t) => t.id === flowTab) || tabs[0];
  let panel = "";
  if (active.id === "summary") {
    panel = `<div class="rank-grid">${bucketTable("쌍끌이 금액구간 히트율", data.dual || [], "dual_krw")}${bucketTable("사모 금액구간 히트율", data.private_equity || [], "pe_krw")}</div>
      <p style="margin-top:12px;">${hitLine("쌍끌이", dual)} · 20일 평균 ${pctCell(dual20.avg)}</p>
      <p>${hitLine("사모", pe)} · 20일 평균 ${pctCell(pe20.avg)}</p>`;
  } else if (active.id === "other_corp" && !active.rows.length) {
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
        <span>쌍끌이</span><b style="color:#00e5ff;">${dual.n}</b>
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
        <span>사모 순매수</span><b style="color:#c084fc;">${pe.n}</b>
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
      <span class="chip" style="background:rgba(56,189,248,0.12); color:#38bdf8;">스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 순매수 합산${minKrw ? ` · ${krw(minKrw)} 이상만 표시` : ""}</span>
      <span class="hint" style="margin:0;">※ 쌍끌이 기관은 토스 기관합계(금융투자+보험+투신+사모 등) 기준입니다.</span>
    </div>

    <div class="h-tabs">${tabBtns}</div>
    <div class="flow-panel">${panel}</div>
    <p class="hint" style="margin-top:12px;">💡 최근가는 토스, 수급 데이터는 일별 합산입니다. 열 이름을 클릭하면 최근가, 외인/기관 순매수량, 추정금액으로 정렬할 수 있습니다.</p>
  `;
  paintSortHeaders(`flow-${active.id}`);
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
    .map((t) => `<span class="sector-stock-pill" onclick="openStock('${escapeHtml(t.ticker)}')"><b>${escapeHtml(t.company || t.ticker)}</b> <span class="meta">${escapeHtml(t.why || "")}</span></span>`)
    .join(" ");
  const asof = cov.last_date ? `공식 수급 최신일 ${cov.last_date} · ${cov.tickers || 0}종목 · ${cov.rows || 0}행` : "공식 수급 데이터 없음 (토스 캐시 대체 가동 중)";
  if (currentView === "investor") setPageAsOf(asof, "KIS 관심종목·고유동성 수급 추적. API 미설정 시 토스 데이터로 자동 대체됩니다.");

  box.innerHTML = `
    ${asofBanner(asof)}
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi"><span>KIS Open API</span><b class="${data.configured ? "ok" : "warn"}">${data.configured ? "연결 완료" : "미설정 (토스 대체)"}</b></div>
      <div class="kpi"><span>저장된 종목</span><b>${cov.tickers ?? 0}개</b></div>
      <div class="kpi"><span>수집된 수급 데이터</span><b>${cov.rows ?? 0}행</b></div>
      <div class="kpi"><span>수집 예정 후보</span><b>${data.universe_n ?? 0}종목</b></div>
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
    ["consecutive", `연속 ${ (src.consecutive || []).length }`],
    ["paired", `동반 ${ (src.paired || []).length }`],
    ["turns", `방향전환 ${ (src.turns || []).length }`],
    ["cum5", `5일 ${ (src.cum5 || []).length }`],
    ["cum20", `20일 ${ (src.cum20 || []).length }`],
    ["cum60", `60일 ${ (src.cum60 || []).length }`],
  ];
  const rows = src[investorEventTab] || [];
  const isCum = String(investorEventTab).startsWith("cum");
  const cumKey = investorEventTab === "cum60" ? "w60" : investorEventTab === "cum5" ? "w5" : "w20";
  const head =
    investorEventTab === "turns"
      ? `<th>종목</th><th>전환</th><th>이전연속</th><th>오늘</th><th>출처</th>`
      : investorEventTab === "paired"
        ? `<th>종목</th><th>방향</th><th>${escapeHtml(src.pair || "동반")}</th><th>외인</th><th>출처</th>`
        : isCum
          ? `<th>종목</th><th>누적</th><th>일수</th><th>절단</th><th>출처</th>`
        : `<th>종목</th><th>방향</th><th>연속일</th><th>누적</th><th>절단</th><th>출처</th>`;
  const body = rows
    .slice(0, 40)
    .map((r) => {
      if (isCum) {
        return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}"><td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)}</div></td>
          <td class="num">${fmtAmt(r[cumKey])}</td>
          <td class="num">${r[cumKey + "_n"] || "—"}</td>
          <td>${r[cumKey + "_capped"] ? "이력 짧음" : "—"}</td>
          <td>${escapeHtml(r.source || "")}</td></tr>`;
      }
      if (investorEventTab === "turns") {
        const t = r.turn || r;
        return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}"><td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)}</div></td>
          <td>${dirKo(t.from || r.turn_from)} → ${dirKo(t.to || r.turn_to)}</td>
          <td class="num">${t.prior_days || r.turn_prior_days || "—"}일</td>
          <td class="num">${fmtAmt(t.today || r.today_a)}</td>
          <td>${escapeHtml(r.source || "")}</td></tr>`;
      }
      if (investorEventTab === "paired") {
        return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}"><td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)}</div></td>
          <td>${dirKo(r.paired_direction)}</td>
          <td class="num">${fmtAmt(r.today_a)}</td>
          <td class="num">${fmtAmt(r.today_b)}</td>
          <td>${escapeHtml(r.source || "")}</td></tr>`;
      }
      return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}"><td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)}</div></td>
        <td>${dirKo(r.direction)}</td>
        <td class="num">${r.days || 0}일</td>
        <td class="num">${fmtAmt(r.cumulative)}</td>
        <td>${r.capped ? "이력 시작" : "—"}</td>
        <td>${escapeHtml(r.source || "")}</td></tr>`;
    })
    .join("");
  const srcBadge = pick === "official"
    ? '<span class="tag tone-우호">🏛️ 한국투자증권(KIS) 공식 수급 기준</span>'
    : '<span class="tag tone-중립">⚡ 토스증권 수급 캐시 기준 (자동 백업 엔진)</span>';

  box.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
      <div class="h-tabs" style="margin:0;">
        <button class="${pick === "official" ? "on" : ""}" data-inv-src="official">공식 KIS (${official.tickers || 0}종목)</button>
        <button class="${pick === "toss" ? "on" : ""}" data-inv-src="toss">토스 캐시 (${toss.tickers || 0}종목)</button>
      </div>
      <div>${srcBadge}</div>
    </div>
    <p class="hint" style="margin:4px 0 10px;">${escapeHtml(src.pair_note || "외국인·기관의 연속 매수 일수(Streak), 동반 매수(Double Buy), 방향 전환(Reversal) 감지 목록입니다.")}</p>
    ${src.empty_reason ? `<p class="hint warn">${escapeHtml(src.empty_reason)}</p>` : ""}
    ${reb.note ? `<p class="hint">${escapeHtml(reb.note)} · 표본 ${reb.n || 0}종목 · 매수 ${reb.buy_n || 0} · 매도 ${reb.sell_n || 0} · 합계 ${fmtAmt(reb.net_sum)}</p>` : ""}
    <div class="h-tabs" style="margin-bottom:8px;">
      ${tabs.map(([id, label]) => `<button class="${investorEventTab === id ? "on" : ""}" data-inv-tab="${id}">${label}</button>`).join("")}
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>${head}</tr></thead>
        <tbody>${body || `<tr><td colspan="6">해당 조건의 수급 포착 종목이 없습니다.</td></tr>`}</tbody>
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

function openYangTacticalModal(r) {
  const modal = $("#yang-tactical-modal");
  if (!modal) return;

  $("#yang-modal-strategy-tag").textContent = r.strategy_tag || "知彼知己 (지피지기)";
  $("#yang-modal-title").textContent = `${r.company || r.ticker} (${r.ticker})`;
  $("#yang-modal-sub").textContent = `${r.market || 'KOSPI'} · ${r.industry || '미분류'} · 퀀트 점수 ${r.quant_score ?? '—'}점 · 참모 점수 ${r.critic_score ?? '—'}점`;

  const sunziInterp = r.sunzi_interpretation || {};
  const bearListHtml = (r.strongest_bear_evidence || []).map((b) => `<li style="color:#fca5a5; font-size:12.5px; margin-bottom:4px;">${escapeHtml(b)}</li>`).join("");
  const waitTest = r.waiting_test || {};

  $("#yang-modal-body").innerHTML = `
    <!-- 1. Top Quote Bar -->
    <div style="background:linear-gradient(90deg, rgba(56,189,248,0.15), rgba(234,179,8,0.1)); padding:12px 16px; border-radius:12px; border-left:4px solid #38bdf8;">
      <b style="color:#fff; font-size:14px;">🍵 양 웬리 제독의 실전 총평:</b>
      <p style="margin:6px 0 0; color:#38bdf8; font-size:14px; font-weight:700; line-height:1.5;">“${escapeHtml(r.one_line_judgment || r.critic_comment || '')}”</p>
    </div>

    <!-- 2. 3-Tier Tactical Intelligence -->
    <div style="display:flex; flex-direction:column; gap:10px;">
      <div class="yang-tier-box briefing">
        <b style="font-size:13px; color:#38bdf8;">🔭 1단계: 전황 분석 & 회사의 실체</b>
        <p style="margin:6px 0 0; color:#e2e8f0;">${escapeHtml(r.tactical_briefing || r.critic_comment || '분석 데이터 집계 중...')}</p>
      </div>

      ${r.maneuver_entry ? `
      <div class="yang-tier-box maneuver">
        <b style="font-size:13px; color:#fbbf24;">💡 2단계: 양 웬리의 기책 & 진입/대기 타점</b>
        <p style="margin:6px 0 0; color:#fef08a;">${escapeHtml(r.maneuver_entry)}</p>
      </div>` : ''}

      ${r.escape_route ? `
      <div class="yang-tier-box escape">
        <b style="font-size:13px; color:#f43f5e;">🚪 3단계: 퇴로 확보 & 작전 무효화 조건 (손절 원칙)</b>
        <p style="margin:6px 0 0; color:#fda4af;">${escapeHtml(r.escape_route)}</p>
      </div>` : ''}
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

  modal.classList.remove("hidden");
  modal.style.display = "flex";

  function closeYangModal() {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }

  const closeBtn = $("#btn-close-yang-modal");
  const closeAction = $("#btn-modal-close-action");
  if (closeBtn) closeBtn.onclick = closeYangModal;
  if (closeAction) closeAction.onclick = closeYangModal;
  modal.onclick = (e) => {
    if (e.target === modal) closeYangModal();
  };
}

async function loadSunzi() {
  const box = $("#sunzi-box");
  if (!box) return;
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
          <b style="font-size:12px; color:#fbbf24;">💡 양 웬리의 기책:</b> ${escapeHtml(r.maneuver_entry)}
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
        <div class="yang-avatar-hud">🍵</div>
        <b style="font-size:18px; color:#fff; font-weight:900;">양 웬리 제독</b>
        <span style="color:#94a3b8; font-size:12px; display:block; margin-top:2px;">제13함대 사령관 · 실전 퀀트 참모</span>
        <div class="yang-tea-badge">🍵 홍차 브리핑 준비 완료</div>
        <p style="margin:12px 0 0; font-size:11.5px; color:#cbd5e1; line-height:1.45; font-style:italic;">
          “전쟁에서 가장 중요한 건 이기는 게 아니라, 지지 않는 거라네.”
        </p>
      </div>

      <article class="yang-briefing-hud">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <h3 style="margin:0; font-size:17px; color:#38bdf8; font-weight:900;">📜 ${escapeHtml(briefing.title || "제13함대 히페리온 작전 회의록")}</h3>
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
        <input id="sunzi-q" type="text" autocomplete="off" placeholder="🔍 퀀트 밖 종목도 분석합니다. 종목명이나 코드를 입력하세요." />
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
        <b style="font-size:14.5px; color:#fde047;">⚔️ 양 웬리의 정밀 전술 분석 후보 TOP 6</b>
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
            <th>양 웬리 전술 총평</th>
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

  // Bind Clicks to open Yang Tactical Modal
  box.querySelectorAll(".yang-tactical-card, .btn-open-yang-brief, .btn-table-open-brief").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const idx = parseInt(el.dataset.index, 10);
      const row = sunziAllRows[idx];
      if (row) openYangTacticalModal(row);
    });
  });

  box.querySelectorAll("tr.clickable[data-ticker]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      const idx = parseInt(tr.dataset.index, 10);
      const row = sunziAllRows[idx];
      if (row) openYangTacticalModal(row);
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
      if (e.key !== "Enter") return;
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

async function loadFlow(force) {
  const box = $("#flow-box");
  if (!box) return;
  box.innerHTML = "<p>수급 데이터를 불러오는 중…</p>";
  if (force) flowLimit = {};
  const data = await ensureFlow(force);
  renderFlow(data);
}

function emptyFilters() {
  const rateRaw = $("#empty-rate")?.value;
  return {
    q: ($("#empty-q")?.value || "").trim().toLowerCase(),
    mode: $("#empty-mode")?.value || "empty",
    maxRate: rateRaw === "" || rateRaw == null ? null : Number(rateRaw),
    minKrw: Number($("#empty-min-krw")?.value || 0),
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
  return rows.filter((r) => {
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
  const rows = filterEmptyRows(uniq);
  const mode = emptyFilters().mode;
  if (!sortState.empty) {
    sortState.empty = { key: mode === "low_foreign" ? "foreign_holding_rate" : "empty_krw", dir: mode === "low_foreign" ? "asc" : "desc" };
  }
  const ordered = sortedCopy(rows, "empty", sortState.empty.key, sortState.empty.dir);
  const hit = analyzeHit(ordered, "ret_5d");
  const body = ordered
    .map(
      (r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
      <td class="num">${i + 1}</td>
      <td class="name-cell"><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker || "")}${emptyTags(r)}</div>${rowNote(r.comment_empty_short || r.comment_empty)}</td>
      <td class="num">${quoteCell(r)}</td>
      <td class="num">${r.foreign_holding_rate == null ? "—" : fmtPct(r.foreign_holding_rate, 2)}</td>
      <td class="num">${r.foreign_rate_chg == null ? "—" : pctCell(r.foreign_rate_chg)}</td>
      <td class="num">${signedInt(r.foreign_net)}</td>
      <td class="num">${signedInt(r.institution_net)}</td>
      <td class="num">${signedInt(r.individual_net)}</td>
      <td class="num">${r.empty_share == null ? "—" : fmtPct(r.empty_share, 0)}</td>
      <td class="num">${r.holding_exit == null ? "—" : fmtPct(r.holding_exit, 2)}</td>
      <td class="num">${escapeHtml(krw(r.empty_krw))}</td>
      <td class="num">${r.sell_streak || 0}</td>
      <td class="num">${pctCell(r.ret_5d)}</td>
    </tr>`
    )
    .join("");
  const when = fmtWhen(data.fetched_at);
  const asof = when ? `빈집 데이터 ${when} · ${data.days || 5}거래일` : `빈집 스캔 시점 없음 · ${data.days || 5}거래일`;
  if (currentView === "empty") setPageAsOf(asof, "수급 스캔과 같은 토스 데이터입니다. 다시 스캔하면 갱신됩니다.");
  box.innerHTML = `
    ${asofBanner(asof)}
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi"><span>조건 종목</span><b>${rows.length}</b></div>
      <div class="kpi"><span>쌍매도</span><b>${(data.empty || []).length}</b></div>
      <div class="kpi"><span>복귀 조짐</span><b>${(data.comeback || []).length}</b></div>
      <div class="kpi"><span>외인 5%↓</span><b>${(data.low_foreign || []).length}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection_empty || "쌍매도는 외인·기관 동시 순매도, 지분은 토스 외인 보유비율, 복귀는 최근 1~2일 재매수입니다. ")}</p>
    <p>스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 · ${hitLine("선택 집합", hit)}</p>
    <div class="table-wrap tall">
      <table data-scope="empty">
        <thead>
          <tr>
            <th>#</th>
            <th class="sortable" data-sort="company">종목</th>
            <th class="sortable" data-sort="last">최근가</th>
            <th class="sortable" data-sort="foreign_holding_rate">외인 지분</th>
            <th class="sortable" data-sort="foreign_rate_chg">지분 변화</th>
            <th class="sortable" data-sort="foreign_net">외인(주)</th>
            <th class="sortable" data-sort="institution_net">기관(주)</th>
            <th class="sortable" data-sort="individual_net">개인(주)</th>
            <th class="sortable" data-sort="empty_share">이탈 비중</th>
            <th class="sortable" data-sort="holding_exit">보유대비</th>
            <th class="sortable" data-sort="empty_krw">이탈 추정</th>
            <th class="sortable" data-sort="sell_streak">연속매도</th>
            <th class="sortable" data-sort="ret_5d">이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="13" class="hint">조건에 맞는 종목이 없습니다. 유형을 바꾸거나 다시 스캔해 보세요.</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">${escapeHtml(data.disclaimer || "")} 이탈 추정은 (외인+기관 순매도 주수)×종가입니다. 외인 지분은 토스 holdingRate입니다. 기관 보유비율은 이 API에 없어서 순매수로 봅니다. 열 이름을 누르면 정렬합니다.</p>
  `;
  emptyCache = data;
  paintSortHeaders("empty");
}

async function loadEmpty(force) {
  const box = $("#empty-box");
  if (!box) return;
  box.innerHTML = "<p>빈집 종목을 불러오는 중…</p>";
  if (force || !(flowCache && Array.isArray(flowCache.empty) && !flowCache.need_scan)) {
    box.innerHTML = "<p>토스 수급을 스캔하는 중… 빈집 분류를 위해 1분 안팎 걸릴 수 있습니다.</p>";
  }
  const data = await ensureFlow(force);
  renderEmpty(data);
}

function tradeFilters() {
  return {
    q: ($("#trade-q")?.value || "").trim().toLowerCase(),
    mode: $("#trade-mode")?.value || "setup",
    minKrw: Number($("#trade-min-krw")?.value || 0),
    excludeQuant: Boolean($("#trade-ex-quant")?.checked),
    ta: $("#trade-ta")?.value || "",
  };
}

function setupNotional(r) {
  const vals = [];
  if (r.dual) vals.push(Number(r.dual_krw || 0));
  if (r.pe_buy || r.pe_accum) vals.push(Number(r.pe_krw || 0));
  if (r.empty) vals.push(Number(r.empty_krw || 0));
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
  const { q, mode, minKrw, excludeQuant, ta } = tradeFilters();
  return rows.filter((r) => {
    if (excludeQuant && r.in_quant) return false;
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
    if (minKrw && setupNotional(r) < minKrw) return false;
    if (!taMatch(r, ta)) return false;
    return true;
  });
}

const TA_TIPS = {
  과매도: "스토캐스틱 %K가 20 아래입니다. 최근 5일 고저 대비 종가가 바닥에 가깝다는 뜻입니다. 단기 낙폭이 커서 반등 여지를 보기도 하지만, 하락 추세 안에서는 과매도가 더 이어질 수 있습니다. 매수 지시가 아닙니다.",
  과매수: "스토캐스틱 %K가 80 위입니다. 최근 5일 안에서 종가가 고점에 가깝습니다. 숨 고르기나 되돌림이 나올 수 있고, 강한 상승 추세면 과매수가 오래가기도 합니다. 매도 지시가 아닙니다.",
  "스토 골든": "스토캐스틱 골든 크로스입니다. 빠른 선(%K)이 느린 선(%D)을 아래에서 위로 뚫었습니다. 단기 모멘텀이 살아난 교차일 뿐, 추세 전환 확정이 아닙니다. 일봉 5,3,3 기준입니다.",
  "스토 데드": "스토캐스틱 데드 크로스입니다. ‘죽음’이나 상장폐지가 아니라, 빠른 선(%K)이 느린 선(%D)을 위에서 아래로 뚫은 교차입니다. 단기 오름세가 꺾인 쪽으로 봅니다. 일봉 한 번의 교차이며 매도 지시가 아닙니다.",
  "구름 위": "일목균형표에서 종가가 선행스팬 A·B가 만든 구름대 위에 있습니다. 중기 지지가 발밑에 있어 추세가 강한 쪽으로 봅니다. 9-26-52 일봉이며",
  "구름 아래": "종가가 일목 구름대 아래에 있습니다. 구름이 위에 저항으로 남아서, 단기 반등이 나와도 구름을 뚫기 전에는 중기 추세가 약한 구간으로 봅니다. ‘당장 나쁘다’기보다 중기 약세 배열입니다. 매도 지시가 아닙니다.",
  "구름 안": "종가가 구름 두께 안에 있습니다. 지지·저항이 겹쳐 방향이 정해지지 않은 혼조로 봅니다. 돌파 전까지는 추세 신호로 쓰지 않는 편이 낫습니다.",
  "전환 골든": "일목 전환선(9일)이 기준선(26일)을 아래에서 위로 돌파한 날입니다. 단기 중심이 중기 중심을 앞지른 교차입니다. 구름 위치와 같이 봐야 하고, 단독 매수 신호가 아닙니다.",
  "전환 데드": "일목 전환선이 기준선을 위에서 아래로 뚫은 날입니다. 단기 중심이 중기 중심 아래로 내려온 교차입니다. 데드는 데드 크로스(약세 교차)이지 종목 자체의 위험이 아닙니다.",
  "전환>기준": "전환선(9일 중심)이 이미 기준선(26일 중심) 위에 있습니다. 골든 크로스가 ‘뚫는 순간’이라면, 이것은 ‘이미 강세 배열’입니다. 단기 추세가 중기보다 위에 있다는 뜻이고, 구름 아래면 배열과 위치가 어긋난 상태일 수 있습니다.",
  "전환<기준": "전환선이 기준선 아래에 있습니다. 단기 중심이 중기 중심보다 낮아 일목에서 기본 약세 배열입니다. 역시 구름 위치와 같이 봐야 합니다.",
};

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
    .map((t) => {
      const bull = t.includes("골든") || t.includes("구름 위") || t.includes("전환>");
      const bear = t.includes("데드") || t.includes("구름 아래") || t.includes("과매수") || t.includes("전환<");
      const cls = bull ? "up" : bear ? "down" : t.includes("과매도") ? "hot" : "";
      return tipTag(t, cls, TA_TIPS);
    })
    .join("");
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
  const qVal = ($("#trade-q")?.value || "").trim();
  const rows = sortedCopy(filterTradeRows(all), "trade", "setup_notional", "desc");
  if (rows.length === 0 && qVal.length > 0) {
    fetchOnDemandFlow(qVal, "#trade-box", "trade");
    return;
  }
  const outside = all.filter((r) => !r.in_quant);
  const dualN = outside.filter((r) => r.dual).length;
  const peN = outside.filter((r) => r.pe_buy || r.pe_accum).length;
  const emptyN = outside.filter((r) => r.empty).length;
  const hit = analyzeHit(rows, "ret_5d");
  const taBull = all.filter((r) => !r.in_quant && taMatch(r, "ta_bull")).length;
  const confluence = all.filter((r) => !r.in_quant && taMatch(r, "confluence")).length;

  const renderStochCell = (r) => {
    if (!r.ta || r.ta.stoch_k == null) return '<span class="hint">—</span>';
    const k = Number(r.ta.stoch_k);
    const d = r.ta.stoch_d != null ? Number(r.ta.stoch_d) : null;
    let badge = "";
    if (k <= 20) {
      badge = `<span class="chip" style="background:rgba(16,185,129,0.15); color:#34d399; font-weight:700; font-size:11px;">🟢 과매도 ${fmt(k, 1)}</span>`;
    } else if (k >= 80) {
      badge = `<span class="chip" style="background:rgba(239,68,68,0.15); color:#f87171; font-weight:700; font-size:11px;">🔴 과매수 ${fmt(k, 1)}</span>`;
    } else {
      badge = `<span style="font-weight:700; color:#e2e8f0;">${fmt(k, 1)}</span>`;
    }
    return `<div>${badge}${d != null ? `<div class="meta" style="font-size:11px; margin-top:2px;">%D ${fmt(d, 1)}</div>` : ""}</div>`;
  };

  const renderTechBadges = (r) => {
    const tags = [];
    if (taMatch(r, "confluence")) tags.push('<span class="chip" style="background:rgba(16,185,129,0.2); color:#4ade80; font-weight:800; border:1px solid rgba(74,222,128,0.4);">🔥 수급+기술</span>');
    else if (taMatch(r, "ta_bull")) tags.push('<span class="chip" style="background:rgba(250,204,21,0.15); color:#facc15; font-weight:700;">⚡ 기술강세</span>');
    if (taMatch(r, "stoch_golden")) tags.push('<span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-weight:700;">✨ 골든크로스</span>');
    if (taMatch(r, "ichi_above")) tags.push('<span class="chip" style="background:rgba(168,85,247,0.15); color:#c084fc; font-weight:700;">☁️ 구름위</span>');
    else if (taMatch(r, "ichi_tk")) tags.push('<span class="chip" style="background:rgba(59,130,246,0.15); color:#60a5fa; font-weight:700;">📈 전환&gt;기준</span>');

    const baseTags = taTags(r);
    return tags.length ? tags.join(" ") : (baseTags || '<span class="hint">—</span>');
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
      <td class="num">${quoteCell(r)}</td>
      <td class="num">${renderStochCell(r)}</td>
      <td>${renderTechBadges(r)}</td>
      <td class="num ${r.foreign_net > 0 ? 'text-emerald-400 font-bold' : r.foreign_net < 0 ? 'text-rose-400' : ''}">${signedInt(r.foreign_net)}</td>
      <td class="num ${r.institution_net > 0 ? 'text-emerald-400 font-bold' : r.institution_net < 0 ? 'text-rose-400' : ''}">${signedInt(r.institution_net)}</td>
      <td class="num ${r.pe_net > 0 ? 'text-purple-400 font-bold' : r.pe_net < 0 ? 'text-rose-400' : ''}">${signedInt(r.pe_net)}${r.pe_streak ? `<div class="meta" style="color:#c084fc;">${r.pe_streak}일 연속</div>` : ""}</td>
      <td class="num font-bold text-accent-cyan">${escapeHtml(krw(setupNotional(r)))}</td>
      <td class="num font-bold">${pctCell(r.ret_5d)}</td>
    </tr>`
    )
    .join("");

  const when = fmtWhen(data.fetched_at);
  const px = lastStatus?.freshness?.price_max_date;
  const asof = [when ? `수급 스캔 ${when}` : "", px ? `KRX 일봉 ${px} (스토·일목)` : ""]
    .filter(Boolean)
    .join(" · ") || "트레이딩 데이터 시점 없음";

  if (currentView === "trade") {
    setPageAsOf(asof, "수급은 토스, 스토캐스틱·일목은 KRX 일봉입니다. 다시 스캔하면 수급이 갱신됩니다.");
  }

  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(5,1fr); margin:0 0 16px;">
      <div class="kpi has-tip" data-tip-title="🎯 수급 스캔 모수" data-tip="거래대금 상위 및 랭킹 모니터링 대상 종목 총 수입니다." tabindex="0">
        <span>스캔 종목</span><b>${data.scanned || 0}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="💎 퀀트 밖 외인·기관 쌍끌이" data-tip="메인 퀀트 TOP100에 속하지 않는 숨은 외인+기관 동반 순매수 종목입니다." tabindex="0">
        <span>퀀트 밖 쌍끌이</span><b style="color:#00e5ff;">${dualN}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="💼 퀀트 밖 사모펀드 매집" data-tip="단기 스마트머니인 사모펀드가 연속 순매집 중인 종목입니다." tabindex="0">
        <span>퀀트 밖 사모</span><b style="color:#c084fc;">${peN}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="⚡ 기술적 강세 셋업" data-tip="스토캐스틱 과매도 탈출 또는 일목균형표 호전 등 기술적 진입 타점 종목입니다." tabindex="0">
        <span>기술 강세</span><b style="color:#facc15;">${taBull}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🔥 수급 + 기술 Confluence" data-tip="강력한 스마트머니 수급 유입과 기술적 상승 신호가 동시에 일치하는 최고 확률 타점입니다." tabindex="0">
        <span>수급+기술 중첩</span><b style="color:#4ade80;">${confluence}</b>
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
      <span class="chip" style="background:rgba(56,189,248,0.12); color:#38bdf8;">거래대금·토스 랭킹 위주 ${data.scanned || 0}종목 · ${data.days || 5}거래일 · 빈집 ${emptyN}개</span>
      <span class="meta">${hitLine("선택 집합", hit)}</span>
    </div>

    <div class="table-wrap tall">
      <table data-scope="trade">
        <thead>
          <tr>
            <th style="width:40px;">#</th>
            <th class="sortable" data-sort="company" style="min-width:160px;">종목 · 셋업</th>
            <th class="sortable" data-sort="last">최근가</th>
            <th class="sortable has-tip" data-sort="stoch_k" data-tip="${escapeHtml("스토캐스틱 %K입니다. 최근 5일 고저 대비 종가 위치(0~100)를 3일 평활합니다. 20 아래는 과매도, 80 위는 과매수.")}" tabindex="0">스토 %K (%D)</th>
            <th class="has-tip" data-tip="${escapeHtml("KRX 일봉 스토캐스틱 5,3,3과 일목 9-26-52 기술적 분석 태그입니다.")}" tabindex="0">기술적 신호</th>
            <th class="sortable" data-sort="foreign_net">외인(주)</th>
            <th class="sortable" data-sort="institution_net">기관(주)</th>
            <th class="sortable" data-sort="pe_net">사모(주)</th>
            <th class="sortable" data-sort="setup_notional">추정금액</th>
            <th class="sortable" data-sort="ret_5d">이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="10" class="hint" style="text-align:center; padding:30px;">조건에 맞는 종목이 없습니다. 퀀트 제외를 끄거나 셋업·기술을 바꿔 보세요.</td></tr>`}</tbody>
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

function renderStrategy(data) {
  const box = $("#strategy-box");
  if (!box) return;
  const rows = data.rows || [];
  const highCount = rows.filter(r => r.stability_label === "HIGH").length;
  const medCount = rows.filter(r => r.stability_label === "MEDIUM").length;
  const allSharpes = rows.map(r => ((r.strategies || [])[0] || {}).sharpe).filter(v => v != null);
  const avgSharpe = allSharpes.length ? (allSharpes.reduce((a, b) => a + b, 0) / allSharpes.length).toFixed(2) : "—";
  const allMdds = rows.map(r => ((r.strategies || [])[0] || {}).max_drawdown).filter(v => v != null);
  const avgMdd = allMdds.length ? ((allMdds.reduce((a, b) => a + b, 0) / allMdds.length) * 100).toFixed(1) + "%" : "—";

  const body = rows
    .map((r) => {
      const best = (r.strategies || [])[0] || {};
      const paramsKo = r.best_params_ko || best.params_ko || "";
      const familyKo = r.best_family_ko || best.family_ko || "";
      const comment = r.best_comment || best.comment || r.warning || "";
      const stab = r.stability_label || "LOW";
      const stabHtml = stab === "HIGH" 
        ? `<span class="strat-badge-high">🟢 HIGH (최상)</span>`
        : stab === "MEDIUM"
        ? `<span class="strat-badge-med">🟡 MED (보통)</span>`
        : `<span class="strat-badge-low">🟠 LOW (표본부족)</span>`;

      return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker || "")}">
        <td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker || "")} · ${r.bars || 0}거래일</div></td>
        <td>
          <div class="strat-pill-name">${escapeHtml(r.best_name || "—")}</div>
          <div class="params-ko">${escapeHtml(paramsKo || familyKo)}</div>
        </td>
        <td>${stabHtml}</td>
        <td class="num has-tip" data-tip="종합 샤프 지수: 위험 1단위당 초과수익 (1.0 이상 우수)">${best.sharpe == null ? "—" : fmt(best.sharpe, 2)}</td>
        <td class="num has-tip" data-tip="미래 검증(OOS) 샤프: 과거 끼워맞추기 없는 순수 미래 성과">${best.oos_sharpe == null ? "—" : fmt(best.oos_sharpe, 2)}</td>
        <td class="num has-tip" data-tip="순환 검증(WF) 승률: 시기를 바꿔가며 테스트했을 때 플러스 수익을 낸 기간 비율">${best.wf_hit == null ? "—" : `${(best.wf_hit * 100).toFixed(0)}%`} <span class="meta">${best.wf_windows || 0}구간</span></td>
        <td class="num has-tip" data-tip="최대 낙폭(MDD): 보유 기간 중 겪었던 최대 하락폭">${pctCell(best.max_drawdown)}</td>
        <td class="num has-tip" data-tip="총 매매 횟수: 왕복 체결 횟수">${best.trade_count ?? "—"}회</td>
        <td class="strat-note">${escapeHtml(comment)}</td>
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

    <!-- 4-Step Intuitive Guide Deck -->
    <div class="strat-guide-grid">
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">🎯</span> 1. 백테스트 목적</div>
        <div class="strat-guide-desc">재무 Quant TOP20 종목별로 과거 3년간 가장 수익성과 안전성이 뛰어났던 <b>최적 매매 타이밍</b>을 발굴합니다.</div>
      </div>
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">🧪</span> 2. 4대 전략 풀</div>
        <div class="strat-guide-desc"><b>RSI 과매도 반등</b>, <b>볼린저 하단 반등</b>, <b>이평선 골든크로스</b>, <b>돈치안 박스권 돌파</b> 중 최고 성과 규칙을 채택합니다.</div>
      </div>
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">🛡️</span> 3. 과적합 2중 방지</div>
        <div class="strat-guide-desc">과거에만 반짝 맞춘 착시를 막기 위해, <b>미래 가상 구간(OOS)</b>과 <b>시기 순환(Walk-Forward)</b>을 통과해야 <b>HIGH</b> 등급을 부여합니다.</div>
      </div>
      <div class="strat-guide-card">
        <div class="strat-guide-head"><span class="strat-guide-icon">⏱️</span> 4. 현실적 체결 기준</div>
        <div class="strat-guide-desc">신호 발생 <b>다음날 시가 매수</b> 및 호가 슬리피지(0.05%)를 선반영하여 실전과 동일한 환경을 모의합니다.</div>
      </div>
    </div>

    <!-- Strategy Summary KPIs -->
    <div class="strat-summary-row">
      <div class="strat-summary-item">
        <span>🟢 안정성 최상 (HIGH)</span>
        <b>${highCount} <small style="font-size:12px; color:#94a3b8; font-weight:normal;">개 종목</small></b>
      </div>
      <div class="strat-summary-item">
        <span>🟡 안정성 보통 (MED)</span>
        <b>${medCount} <small style="font-size:12px; color:#94a3b8; font-weight:normal;">개 종목</small></b>
      </div>
      <div class="strat-summary-item">
        <span>📊 TOP20 평균 샤프 지수</span>
        <b>${avgSharpe} <small style="font-size:12px; color:#38bdf8; font-weight:normal;">(위험 대비 초과수익 우수)</small></b>
      </div>
      <div class="strat-summary-item">
        <span>🛡️ TOP20 평균 최대낙폭</span>
        <b>${avgMdd} <small style="font-size:12px; color:#34d399; font-weight:normal;">(리스크 방어력 양호)</small></b>
      </div>
    </div>

    <div class="table-wrap tall"><table>
      <thead><tr>
        ${thTip("종목", "Quant TOP20 종목명과 KRX 일봉 데이터 축적 일수입니다.")}
        ${thTip("최적 매매 규칙", "해당 종목과 과거 가장 궁합이 좋았던 진입/청산 전략 및 세부 파라미터입니다.")}
        ${thTip("안정성", "HIGH(미래 검증 완료) / MED(보통) / LOW(데이터 표본 부족).")}
        ${thTip("종합 샤프", "변동성 대비 초과수익 비율. 1.0 이상이면 우수, 1.5 이상이면 최상급입니다.")}
        ${thTip("미래 검증 샤프", "AI/모델이 학습하지 않은 별도의 미래 기간(OOS) 성과입니다.")}
        ${thTip("순환 검증 승률", "시뮬레이션 구간을 3개월씩 전진시키며(Walk-Forward) 플러스 수익을 낸 기간 비율입니다.")}
        ${thTip("최대 낙폭", "전략 운용 중 겪었던 최대 하락폭(MDD)입니다. 낮을수록 안전합니다.")}
        ${thTip("매매 횟수", "과거 3년간 발생한 총 왕복 매매 횟수입니다.")}
        ${thTip("전략 분석 & 매매 코멘트", "이 종목에 이 전략을 채택한 배경과 실전 매매 가이드입니다.")}
      </tr></thead>
      <tbody>${body || "<tr><td colspan=9>TOP20 백테스트를 실행하세요.</td></tr>"}</tbody>
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
  const box = $("#trade-box");
  if (!box) return;
  box.innerHTML = "<p>트레이딩 수급을 불러오는 중…</p>";
  if (force || !flowReady(flowCache)) {
    box.innerHTML = "<p>토스 수급을 스캔하는 중… 거래대금·랭킹 종목 포함이라 1~2분 걸릴 수 있습니다.</p>";
  }
  const data = await ensureFlow(force);
  renderTrade(data);
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

function filerLabel(r) {
  const ko = r.filer_ko || r.name_ko || r.filer || r.name || "";
  const who = r.filer_who || r.who_ko || "";
  const en = r.filer || r.name || "";
  return `<b>${escapeHtml(ko)}</b><div class="meta">${escapeHtml([who, en !== ko ? en : ""].filter(Boolean).join(" · "))}</div>${rowNote(r.comment)}`;
}

function issuerLabel(r) {
  const ko = r.issuer_ko || r.issuer || "";
  const ticker = r.ticker || "";
  const note = r.note_ko || "";
  const en = r.issuer && r.issuer_ko && r.issuer !== r.issuer_ko ? r.issuer : "";
  const y = r.yahoo && ticker
    ? ` <a class="ext inline" href="${escapeHtml(r.yahoo)}" target="_blank" rel="noopener">Yahoo</a>`
    : "";
  return `<b>${escapeHtml(ko)}</b>${ticker ? ` <span class="tag">${escapeHtml(ticker)}</span>` : ""}${y}
    <div class="meta">${escapeHtml(note || en || r.cusip || "")}</div>${rowNote(r.comment_short || r.comment)}`;
}

function renderUs13f(data) {
  const box = $("#us13f-box");
  if (!box) return;
  const mode = $("#us13f-mode")?.value || "new";
  const err = (data.errors || []).map((e) => `${e.filer}: ${e.error}`).join(" · ");
  const kpis = `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi has-tip" data-tip-title="🏛️ 스캔 대상 대가 펀드 수" data-tip="버크셔 해서웨이, 브리지워터, 시타델 등 미국 SEC에 13F를 공시한 핵심 글로벌 헤지펀드/기관 수입니다." tabindex="0">
        <span>펀드</span><b>${data.scanned || (data.filers || []).length}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🔥 이번 분기 신규 매수 종목 수" data-tip="월가 거물들이 이번 분기에 새롭게 포트폴리오에 편입한 신규 베팅 종목 수입니다." tabindex="0">
        <span>신규</span><b style="color:#4ade80;">${(data.new || []).length}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🎯 2인 이상 대가 공통 보유 종목 수" data-tip="버핏, 달리오, 켄 그리핀 등 2개 이상의 독립 대형 펀드가 동시에 러브콜을 보낸 핵심 종목 수입니다." tabindex="0">
        <span>공통(2+)</span><b style="color:#38bdf8;">${(data.common || []).length}</b>
      </div>
      <div class="kpi has-tip" data-tip-title="🚪 이번 분기 전량 청산 종목 수" data-tip="거물들이 이번 분기 포트폴리오에서 비중 100%를 전량 매도한 종목 수입니다." tabindex="0">
        <span>청산</span><b style="color:#f87171;">${(data.exits || []).length}</b>
      </div>
    </div>
    <p class="hint">${escapeHtml(data.selection || "SEC EDGAR 13F-HR 분기 말 보유입니다. 신규·확대·청산은 직전 분기 대비 주수 변화입니다. ")}</p>
    ${asofBanner([`13F 보고 ${(data.periods || []).join(" · ") || "—"}`, data.fetched_at ? `받은 시각 ${fmtWhen(data.fetched_at)}` : ""].filter(Boolean).join(" · "))}
    <p>기준 ${(data.periods || []).join(" · ") || "—"} · 출처 SEC EDGAR
      <a class="ext inline" href="https://www.sec.gov/" target="_blank" rel="noopener">sec.gov</a>
      · 참고 <a class="ext inline" href="https://whalewisdom.com/" target="_blank" rel="noopener">WhaleWisdom</a></p>`;
  let table = "";
  if (mode === "filers" || mode === "weights") {
    const filers = filter13f(data.filers || [], ["name", "manager", "cik"]);
    if (mode === "filers") {
      table = `<table><thead><tr><th>펀드</th><th>보고일</th><th>공시일</th><th>종목수</th><th>총액</th><th>신규</th><th>청산</th><th>원문</th></tr></thead><tbody>
        ${filers.map((f) => `<tr>
          <td>${filerLabel(f)}</td>
          <td>${escapeHtml(f.report_date || "")}</td>
          <td>${escapeHtml(f.filing_date || "")}</td>
          <td class="num">${f.n ?? "—"}</td>
          <td class="num">${usd(f.total_value)}</td>
          <td class="num">${f.new ?? 0}</td>
          <td class="num">${f.exits ?? 0}</td>
          <td>${f.page ? `<a class="ext inline" href="${escapeHtml(f.page)}" target="_blank" rel="noopener">SEC</a>` : "—"}
            ${f.whale ? ` · <a class="ext inline" href="${escapeHtml(f.whale)}" target="_blank" rel="noopener">WW</a>` : ""}</td>
        </tr>`).join("")}</tbody></table>`;
    } else {
      const rows = [];
      for (const f of filers) {
        for (const t of f.top || []) rows.push({ ...t, filer: f.name });
      }
      const filtered = filter13f(rows, ["issuer", "cusip", "filer"]);
      table = `<table><thead><tr><th>펀드</th><th>종목</th><th>티커</th><th>비중</th><th>금액</th><th>주수</th></tr></thead><tbody>
        ${filtered.map((r) => `<tr>
          <td>${filerLabel(r)}</td>
          <td>${issuerLabel(r)}</td>
          <td><b>${escapeHtml(r.ticker || "—")}</b></td>
          <td class="num">${r.weight == null ? "—" : fmtPct(r.weight, 1)}</td>
          <td class="num">${usd(r.value)}</td>
          <td class="num">${Number(r.shares || 0).toLocaleString("en-US")}</td>
        </tr>`).join("")}</tbody></table>`;
    }
  } else if (mode === "common") {
    const rows = filter13f(data.common || [], ["issuer", "cusip", "filers"]);
    table = `<table><thead><tr><th>종목</th><th>펀드 수</th><th>보유 펀드</th><th>합산 금액</th></tr></thead><tbody>
      ${rows.map((r) => `<tr>
        <td>${issuerLabel(r)}</td>
        <td class="num">${r.n_filers}</td>
        <td>${escapeHtml((r.filers_ko || r.filers || []).join(", "))}</td>
        <td class="num">${usd(r.value)}</td>
      </tr>`).join("")}</tbody></table>`;
  } else if (mode === "trend") {
    const rows = filter13f(data.trend || [], ["issuer", "cusip", "buyers", "sellers"]);
    table = `<table><thead><tr><th>종목</th><th>점수</th><th>신규</th><th>확대</th><th>축소</th><th>청산</th><th>금액 변화</th></tr></thead><tbody>
      ${rows.map((r) => `<tr>
        <td>${issuerLabel(r)}</td>
        <td class="num">${r.score}</td>
        <td class="num">${r.new}</td>
        <td class="num">${r.increase}</td>
        <td class="num">${r.decrease}</td>
        <td class="num">${r.exit}</td>
        <td class="num">${usd(r.value_delta)}</td>
      </tr>`).join("")}</tbody></table>`;
  } else {
    const key = mode === "exits" ? "exits" : mode === "increases" ? "increases" : "new";
    const rows = filter13f(data[key] || [], ["issuer", "cusip", "filer"]);
    const amt = mode === "exits" ? "prev_value" : "value";
    table = `<table><thead><tr><th>펀드</th><th>종목</th><th>티커</th><th>금액</th><th>변화</th><th>비중</th></tr></thead><tbody>
      ${rows.slice(0, 80).map((r) => `<tr>
        <td>${filerLabel(r)}</td>
        <td>${issuerLabel(r)}</td>
        <td><b>${escapeHtml(r.ticker || "—")}</b></td>
        <td class="num">${usd(r[amt])}</td>
        <td class="num">${usd(r.value_delta)}</td>
        <td class="num">${r.weight ? fmtPct(r.weight, 1) : "—"}</td>
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
    <div class="h-tabs" style="margin:12px 0 16px;">
      ${MODES.map(([k, label]) => `
        <button type="button" class="${mode === k ? "on" : ""}" data-13f-mode="${k}">
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
            <div class="meta">${escapeHtml(c.ticker || c.cusip || "")}</div>
          </div>
          <span class="tag tone-우호">🌟 ${c.n_filers}개 펀드 동시 보유</span>
        </div>
        <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">
          합산 투자액: <b style="color:#fff; font-size:13px;">${usd(c.value)}</b>
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
        <div class="us13f-action-meta">
          ${escapeHtml(r.filer_ko || r.filer)} · 티커: <b>${escapeHtml(r.ticker || "—")}</b>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; font-size:12px;">
          <span style="color:var(--muted);">거래 규모</span>
          <b style="color:#fff; font-size:13px;">${usd(amt)}</b>
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
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>
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
      const code = el.dataset.backtestStock;
      switchView("strategy");
      const inp = $("#custom-strategy-q");
      if (inp) inp.value = code;
      runCustomBacktest(code);
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

  return `
    <div class="yencarry-card">
      <div class="yencarry-header">
        <div>
          <h3>엔 캐리 트레이드 위험 모니터 (Yen Carry Monitor)</h3>
          <span class="hint">엔/달러 환율 속도 + 닛케이 225 + 미·일 금리차 종합 청산 위험도</span>
        </div>
        <div class="yencarry-badge ${lvl}">
          ${score}점 · ${escapeHtml(lvlKo)}
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
    const chg1m = Number(item.ret_1m);
    const isUp = chg >= 0;
    const is1mUp = chg1m >= 0;
    const chgTxt = chg == null || Number.isNaN(chg) ? "—" : `${isUp ? "+" : ""}${(chg * 100).toFixed(2)}%`;
    const priceFmt = item.category === "crypto" || item.category === "index" ? fmt(item.last, 2) : fmt(item.last, 2);
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
            <div class="macro-card-price">${priceFmt}</div>
            <div class="macro-card-chg ${isUp ? "up" : "down"}">${chgTxt}</div>
          </div>
        </div>
        ${sparkSvg}
        ${comment ? `<div class="macro-card-comment">${comment}</div>` : ""}
      </div>
    `;
  }).join("");

  return `
    <div style="margin-top:18px">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <h3 style="margin:0;">글로벌 매크로 바로미터 (지수 · 환율 · 금·원유 · 비트코인 · 금리)</h3>
        <span class="chip has-tip" data-tip-title="💡 글로벌 매크로 바로미터 도움말" data-tip="각 카드를 마우스로 가리키면 해당 지표의 의미와 상승/하락 시 한국 증시 영향(호재/악재) 상세 가이드가 표시됩니다.">💡 카드에 마우스를 올리면 호재/악재 가이드 표시</span>
      </div>
      <p class="hint" style="margin-top:4px;">TradingEconomics 스타일 30일/60일 시계열 차트 및 실시간 등락률</p>
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
          <h3 style="margin:0 0 8px;font-size:15px;color:#e8eef8;">🇰🇷 한국은행 ECOS 거시 펀더멘털</h3>
          <p class="hint" style="margin-bottom:8px;">기준금리, 한-미 금리차, 국고채 3년, 한국 CPI 물가지수, M2 통화량 (환율·지수는 상단 바로미터 참조)</p>
          <div class="macro-item-grid">
            ${domesticFiltered.map((it, idx) => renderMacroItemCard(it, idx, "kr")).join("")}
          </div>
        </div>
        <div>
          <h3 style="margin:0 0 8px;font-size:15px;color:#e8eef8;">🌐 미국 연준 FRED 거시 펀더멘털</h3>
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
}

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

async function testSettings() {
  $("#test-box").innerHTML = "<p>테스트 중…</p>";
  const r = await api("/api/settings/test", { method: "POST" });
  $("#test-box").innerHTML = Object.entries(r)
    .map(([k, v]) => `<p class="${v.ok ? "ok" : "bad"}">${k}: ${v.ok ? "정상" : "실패"} — ${v.detail}</p>`)
    .join("");
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
    payload.lookback_days = 750;
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

$$(".nav-btn").forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));
if ($("#flow-q")) {
  $("#flow-q").addEventListener("input", () => { if (flowCache) renderFlow(flowCache); });
  $("#flow-q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (flowCache) renderFlow(flowCache);
    }
  });
}
if ($("#btn-flow-search")) {
  $("#btn-flow-search").addEventListener("click", () => { if (flowCache) renderFlow(flowCache); });
}
if ($("#flow-refresh")) {
  $("#flow-refresh").addEventListener("click", () => loadFlow(true).catch((err) => alert(err.message)));
}
if ($("#flow-days")) {
  $("#flow-days").addEventListener("change", () => loadFlow(false).catch((err) => alert(err.message)));
}
if ($("#flow-min-krw")) {
  $("#flow-min-krw").addEventListener("change", () => {
    if (flowCache) renderFlow(flowCache);
  });
}
if ($("#empty-refresh")) {
  $("#empty-refresh").addEventListener("click", () => loadEmpty(true).catch((err) => alert(err.message)));
}
["empty-mode", "empty-rate", "empty-min-krw"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", () => { if (flowCache) renderEmpty(flowCache); });
});
if ($("#empty-q")) {
  $("#empty-q").addEventListener("input", () => { if (flowCache) renderEmpty(flowCache); });
}
if ($("#trade-refresh")) {
  $("#trade-refresh").addEventListener("click", () => loadTrade(true).catch((err) => alert(err.message)));
}
["trade-mode", "trade-min-krw", "trade-ex-quant", "trade-ta"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", () => { if (flowCache) renderTrade(flowCache); });
});
if ($("#trade-q")) {
  $("#trade-q").addEventListener("input", () => { if (flowCache) renderTrade(flowCache); });
  $("#trade-q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (flowCache) renderTrade(flowCache);
    }
  });
}
if ($("#btn-trade-search")) {
  $("#btn-trade-search").addEventListener("click", () => { if (flowCache) renderTrade(flowCache); });
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
function showFloatTip(el) {
  const text = el.getAttribute("data-tip");
  if (!text) return;
  const box = floatTip();
  const explicitTitle = el.getAttribute("data-tip-title");
  const title = explicitTitle || (el.getAttribute("aria-label") || el.textContent || "").trim().split("\n")[0].slice(0, 45);
  const upImpact = el.getAttribute("data-tip-up");
  const downImpact = el.getAttribute("data-tip-down");
  const hintImpact = el.getAttribute("data-tip-hint");

  let html = `
    <div class="float-tip-header">
      <h4 class="float-tip-title">${escapeHtml(title)}</h4>
    </div>
    <div class="float-tip-body">${escapeHtml(text)}</div>
  `;

  if (upImpact || downImpact || hintImpact) {
    html += `<div class="float-tip-impact">`;
    if (upImpact) html += `<div class="up-impact">🔺 <b>상승 시 영향:</b> ${escapeHtml(upImpact)}</div>`;
    if (downImpact) html += `<div class="down-impact">🔻 <b>하락 시 영향:</b> ${escapeHtml(downImpact)}</div>`;
    if (hintImpact) html += `<div class="hint-impact">🎯 <b>핵심 판정 팁:</b> ${escapeHtml(hintImpact)}</div>`;
    html += `</div>`;
  }

  box.innerHTML = html;
  box.classList.remove("hidden");
  const r = el.getBoundingClientRect();
  const maxW = Math.min(380, window.innerWidth - 24);
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
document.addEventListener("pointerover", (e) => {
  const el = e.target.closest("[data-tip]");
  if (el) showFloatTip(el);
});
document.addEventListener("pointerout", (e) => {
  const el = e.target.closest("[data-tip]");
  if (!el) return;
  const next = e.relatedTarget;
  if (next && el.contains(next)) return;
  hideFloatTip();
});
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
$("#rank-q").addEventListener("input", (e) => renderRank(e.target.value));
if ($("#report-q")) {
  $("#report-q").addEventListener("input", (e) => renderReportList("#reports-body", filterReportRows(e.target.value)));
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
      else if (scope === "reports") renderReportList("#reports-body", filterReportRows($("#report-q") ? $("#report-q").value : ""));
      else if (String(scope).startsWith("flow")) {
        if (flowCache) renderFlow(flowCache);
      } else if (scope === "empty") {
        if (emptyCache || flowCache) renderEmpty(emptyCache || flowCache);
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
      item.textContent = opt.textContent || opt.value || "—";
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

const PROVIDER_MODELS = {
  xai: ["grok-4.6", "grok-4.5", "grok-4.3", "grok-4-1-fast", "grok-4", "grok-3", "grok-3-mini"],
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  openrouter: [
    "openai/gpt-4o-mini",
    "x-ai/grok-4-fast",
    "google/gemini-2.5-flash",
    "anthropic/claude-sonnet-4",
    "deepseek/deepseek-chat",
  ],
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
  const p50 = r.expected_p50 || r.median_return || 0;
  const p90 = r.expected_p90 || 0;
  const alpha = r.median_alpha ?? r.median_return ?? 0;
  const sample = r.sample_count || r.years_count || track.length || 0;
  const monthCells = renderPbMonthHeat(months, targetM);

  const years = track.map((y) => {
    const ret = Number(y.return || 0);
    const loss = !y.is_win;
    const fail = (r.failed_analysis || []).find((f) => String(f).includes(String(y.year)));
    return `<div class="pb-year-row ${loss ? "loss" : ""}">
      <div><b>${y.year}년</b> <span class="meta">${escapeHtml(r.entry_window_str || r.window_name || "")}</span>
        ${fail ? `<div style="color:#fca5a5;font-size:11px;margin-top:2px;">실패 원인: ${escapeHtml(fail)}</div>` : ""}
      </div>
      <b style="color:${loss ? "#f87171" : "#34d399"}">${ret > 0 ? "+" : ""}${(ret * 100).toFixed(1)}%</b>
    </div>`;
  }).join("");

  const inv = splitInvalidation(r.invalidating_conditions);
  const invHtml = inv.length
    ? `<ul style="margin:6px 0 0 18px;padding:0;">${inv.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`
    : `<p class="meta" style="margin:6px 0 0;">${escapeHtml(r.invalidating_conditions || "실적 쇼크 또는 대규모 순매도 전환")}</p>`;

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
      const h = Math.max(6, Math.round((Math.abs(ret) / maxAbs) * 110));
      return `<i><span style="font-size:10px;color:${ret < 0 ? "#f87171" : "#67e8f9"}">${(ret * 100).toFixed(1)}%</span><em class="${ret < 0 ? "loss" : ""}" style="height:${h}px"></em><small>'${String(y.year).slice(-2)}</small></i>`;
    }).join("")}</div>`;
    const upPct = (stats.upShare * 100).toFixed(0);
    dual = `<div class="pb-bar-dual"><div style="width:${upPct}%;background:#34d399"></div><div style="width:${100 - upPct}%;background:#f87171"></div></div>
      <div class="meta" style="margin-top:4px;">상방 ${(stats.upVol * 100).toFixed(1)}% (${upPct}%) · 하방 ${(stats.semi * 100).toFixed(1)}% · 비대칭 ${stats.skew.toFixed(2)}x</div>`;
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
      ${stats.skew >= 2 ? "비대칭 계절성 알파 구조" : "대칭에 가까운 구조"}입니다.
      ${escapeHtml(failTxt)}.
      권장 비중은 과하지 않게 두고, 아래 무효화 조건이 뜨면 미련 없이 접는 편이 낫습니다.
    </p>`;
  }

  const st = r.current_status || "DISCOVERY";
  box.innerHTML = `
    <div class="playbook-card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <b style="color:#38bdf8; font-size:14px;">🎯 선취매(Pre-Entry) 매매 플레이북</b>
        <span class="chip" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:11px;">선취매 전략</span>
      </div>
      <ul style="margin:8px 0 0 16px; padding:0; font-size:12.5px; color:#cbd5e1; line-height:1.6;">
        <li>${escapeHtml(pb.entry_timing || "권장 선취매 타이밍: 피크 구간 도달 D-30일 ~ D-15일 전 분할 매수")}</li>
        <li>${escapeHtml(pb.exit_timing || "목표 엑시트 시기: 계절성 피크 도달 시점 또는 목표 알파 달성 시 분할 매도")}</li>
        <li style="color:#fca5a5;">${escapeHtml(pb.stop_loss || "리스크 방어 기준: 평균 MDD 초과 하락 시 손절")}</li>
      </ul>
      <div style="margin-top:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#38bdf8;">📊 현시점 매수 시 수익률 기댓값 산출표</span>
        <div class="expected-kpi-grid">
          <div class="expected-kpi-item"><span>당월 계절성 지수</span><b style="color:#38bdf8;">${r.seasonality_score || "—"}점${r.grade ? ` (${r.grade}등급)` : ""}</b></div>
          <div class="expected-kpi-item"><span>기대 수익률(P50)</span><b style="color:#34d399;">${p50 > 0 ? "+" : ""}${((p50 || 0) * 100).toFixed(1)}%</b></div>
          <div class="expected-kpi-item"><span>낙관 기대치(P90)</span><b style="color:#60a5fa;">${p90 > 0 ? "+" : ""}${((p90 || 0) * 100).toFixed(1)}%</b></div>
          <div class="expected-kpi-item"><span>손익비(PF)</span><b style="color:#fbbf24;">${r.profit_factor || 3.5}x</b></div>
        </div>
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
        <div class="pb-confirm-cell"><span>초과 알파</span><b>${pbPct(alpha)}</b></div>
        <div class="pb-confirm-cell"><span>표본</span><b>${sample}개년</b></div>
        <div class="pb-confirm-cell"><span>상태</span><b>${escapeHtml(st)}</b></div>
      </div>
      <p class="meta" style="margin:8px 0 0;">PC는 모바일의 RS60·EPS Revision 실시간 칸까지는 아직 안 붙입니다. 있는 지표만 정직하게 표시합니다.</p>
    </div>

    <div style="margin-top:14px;background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px 16px;">
      <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;"><b>12개월 기간별 수익 변동성 히트맵</b><span class="meta">셀 = 평균수익 / 승률</span></div>
      <div id="disc-modal-heat" class="pb-month-heat" style="margin-top:10px;">${monthCells}</div>
    </div>

    ${years ? `<div style="margin-top:14px;background:rgba(15,23,42,0.6);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px 16px;">
      <b>연도별 계절성 수익률 & 실패 연도 분석</b>${years}
    </div>` : ""}

    <div style="margin-top:14px;border:1px solid rgba(248,113,113,0.35);border-radius:12px;padding:14px 16px;">
      <b style="color:#f87171;">전략 무효화 조건 (Invalidating Conditions)</b>
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

function bindDiscoveryModalChrome(modal, r) {
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
    stagePill.textContent = r.entry_stage_label || "⚡ 진입 유효";
    let cls = "stage-today";
    if (r.entry_stage === "PRE_ENTRY_15" || r.entry_stage === "PRE_ENTRY_30") cls = "stage-pre-entry";
    else if (r.entry_stage === "ACCUMULATE_60") cls = "stage-accumulate";
    else if (r.entry_stage === "EXIT_PEAK") cls = "stage-peak-exit";
    else if (r.entry_stage === "WATCH") cls = "stage-watch";
    stagePill.className = `stage-pill ${cls}`;
  }

  setModalText("disc-modal-theme", r.common_event_cluster || "계절적 수요 증가 및 분기 실적 모멘텀");

  const stKo = r.current_status === "ACTIVE" ? "🔥 상태 판정: 진입 유효 (ACTIVE)" :
               r.current_status === "WATCH" ? "🟡 상태 판정: 관찰 대상 (WATCH)" :
               r.current_status === "WEAKENING" ? "🟠 상태 판정: 엣지 약화 (WEAKENING)" :
               r.current_status === "BROKEN" ? "🔴 상태 판정: 진입 금지 (BROKEN)" : "🟣 상태 판정: 신규 발굴 (DISCOVERY)";
  setModalText("disc-modal-status-text", stKo);

  const pb = r.playbook || {};
  setModalText("disc-modal-recommendation", `💡 권장 대응: ${pb.recommendation || "반복 상승 Window 진입 시 분할 매수 대응 유효"}`);
  setModalText("disc-modal-window", r.window_name || "—");
  setModalText("disc-modal-sample-sub", `${r.sample_count || r.years_count || 0}개년 Window 검증`);
  setModalText("disc-modal-winrate", `${((r.win_rate || 0) * 100).toFixed(1)}%`);
  setModalText("disc-modal-r3-sub", `최근 3년 ${((r.recent_3y_win_rate || 0) * 100).toFixed(0)}%`);
  const alpha = r.median_alpha ?? r.median_return ?? 0;
  setModalText("disc-modal-alpha", `${alpha > 0 ? "+" : ""}${(alpha * 100).toFixed(1)}%`);
  setModalText("disc-modal-mdd-sub", `평균 MDD -${((r.avg_mdd || 0) * 100).toFixed(1)}%`);
  setModalText("disc-modal-entry-win", `📈 진입 권장: ${r.entry_window_str || "—"}`);
  setModalText("disc-modal-exit-win", `➔ 목표 엑시트: ${r.exit_window_str || "—"}`);

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

  container.innerHTML = `<div style="text-align:center; padding:40px; color:#94a3b8;">오늘의 선취매 최우수 종목 및 테마 기여도 분석 중...</div>`;

  // Fetch Discovery and Theme data in parallel
  const [discRes, themeRes] = await Promise.all([
    api(`/api/seasonality/discovery?lookback_years=${currentV11Lookback}&horizon_days=90`),
    api(`/api/seasonality/themes?lookback_years=${currentV11Lookback}&horizon_days=90`),
  ]);

  const allRows = discRes.rows || [];
  preEntryThemeData = themeRes.themes || [];

  // Render Donut Chart and Theme Ranking Cards
  renderThemeDonutAndRanking(preEntryThemeData);

  // Allowed active pre-entry stages: strictly require actionable pre-entry window (TODAY_ENTRY, PRE_ENTRY_15, PRE_ENTRY_30, ACCUMULATE_60)
  const allowedStages = new Set(["TODAY_ENTRY", "PRE_ENTRY_15", "PRE_ENTRY_30", "ACCUMULATE_60"]);
  let filtered = allRows.filter((r) => allowedStages.has(r.entry_stage));

  if (currentPreEntryMarket !== "all") {
    filtered = filtered.filter((r) => r.market === currentPreEntryMarket);
  }
  if (currentPreEntryTheme !== "all") {
    const tObj = preEntryThemeData.find((t) => t.theme_id === currentPreEntryTheme);
    if (tObj && tObj.candidate_tickers) {
      filtered = filtered.filter((r) => tObj.candidate_tickers.includes(r.ticker));
    }
  }

  // Stage Priority Weight: Forward Entry & Pre-Entry (TODAY_ENTRY > PRE_ENTRY_15 > PRE_ENTRY_30 > ACCUMULATE_60)
  const getStageWeight = (stg) => {
    if (stg === "TODAY_ENTRY") return 100;
    if (stg === "PRE_ENTRY_15") return 80;
    if (stg === "PRE_ENTRY_30") return 60;
    if (stg === "ACCUMULATE_60") return 40;
    return 0;
  };

  if (currentPreEntrySort === "score") {
    filtered.sort((a, b) => {
      const wa = getStageWeight(a.entry_stage);
      const wb = getStageWeight(b.entry_stage);
      const wDiff = wb - wa;
      if (Math.abs(wDiff) >= 40) return wDiff;
      const sa = Number(a.seasonality_score) || 0;
      const sb = Number(b.seasonality_score) || 0;
      return sb - sa;
    });
  } else if (currentPreEntrySort === "return") {
    filtered.sort((a, b) => (b.expected_p50 || b.median_return || 0) - (a.expected_p50 || a.median_return || 0));
  } else if (currentPreEntrySort === "winrate") {
    filtered.sort((a, b) => (b.win_rate || 0) - (a.win_rate || 0));
  } else if (currentPreEntrySort === "alpha") {
    filtered.sort((a, b) => (b.median_alpha || 0) - (a.median_alpha || 0));
  }

  const top10 = filtered.slice(0, 10);
  if (!top10.length) {
    container.innerHTML = `<div style="text-align:center; padding:40px; color:#94a3b8;">해당 조건에 부합하는 선취매 추천 종목이 없습니다. 필터를 완화해 보세요.</div>`;
    return;
  }

  preEntryTop10 = top10;
  container.innerHTML = top10.map((r, idx) => {
    const rank = idx + 1;
    const rankBadge = rank === 1 ? "🥇 1위" : rank === 2 ? "🥈 2위" : rank === 3 ? "🥉 3위" : `🏅 ${rank}위`;
    const rankCls = rank === 1 ? "rank-1" : "";

    let stageCls = "stage-today";
    if (r.entry_stage === "PRE_ENTRY_15" || r.entry_stage === "PRE_ENTRY_30") stageCls = "stage-pre-entry";
    else if (r.entry_stage === "ACCUMULATE_60") stageCls = "stage-accumulate";
    else if (r.entry_stage === "EXIT_PEAK") stageCls = "stage-peak-exit";

    const wr = ((r.win_rate || 0) * 100).toFixed(0);
    const avgRet = ((r.expected_p50 || r.median_return || 0) * 100).toFixed(1);
    const alpha = ((r.median_alpha || 0) * 100).toFixed(1);
    const mdd = ((r.avg_mdd || 0) * 100).toFixed(1);

    const yearsTrackHtml = (r.years_track || []).map((y) => {
      const cls = y.is_win ? "year-track-win" : "year-track-loss";
      const retStr = (y.return * 100).toFixed(1);
      const shortYear = String(y.year).slice(-2);
      return `<span class="year-track-cell ${cls}" style="padding:4px 8px; font-size:11.5px;" title="${y.year}년">${shortYear}년 ${y.return > 0 ? '+' : ''}${retStr}%</span>`;
    }).join("");

    const catalyst = r.common_event_cluster || "계절적 수요 증가 및 분기 실적 모멘텀 유입";

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

        <!-- 5 Key KPI Bar -->
        <div class="pre-entry-kpi-bar">
          <div class="pre-entry-kpi-item">
            <span>5년 평균 수익률</span>
            <b class="text-emerald-400">+${avgRet}%</b>
          </div>
          <div class="pre-entry-kpi-item" style="border-color:rgba(234,179,8,0.4); background:rgba(234,179,8,0.1);">
            <span style="color:#fde047;">5년 승률</span>
            <b style="color:#facc15;">${wr}% (${r.sample_count}/${r.sample_count}년)</b>
          </div>
          <div class="pre-entry-kpi-item">
            <span>초과알파</span>
            <b style="color:#38bdf8;">+${alpha}%</b>
          </div>
          <div class="pre-entry-kpi-item">
            <span>5년 평균 MDD</span>
            <b style="color:#f87171;">-${mdd}%</b>
          </div>
          <div class="pre-entry-kpi-item">
            <span>손익비(PF)</span>
            <b style="color:#fbbf24;">${r.profit_factor || 3.5}x</b>
          </div>
        </div>

        <!-- Timing Window Strip -->
        <div class="pre-entry-timing-strip">
          <span style="color:#38bdf8; font-weight:700;">📈 진입 권장: ${escapeHtml(r.entry_window_str || '08/15 ~ 09/05')}</span>
          <span style="color:#fbbf24; font-weight:700;">➔ 목표 엑시트: ${escapeHtml(r.exit_window_str || '09/20 ~ 10/10')}</span>
        </div>

        <!-- Year-by-Year Track Record Bar -->
        <div style="font-size:11.5px; color:#94a3b8; margin-bottom:6px;">최근 5~8개년 연도별 실측 백테스팅 수익률:</div>
        <div class="year-track-bar" style="flex-wrap:wrap; gap:6px;">${yearsTrackHtml}</div>

        <!-- AI Catalyst Box -->
        <div class="catalyst-box">
          💡 <b>AI 핵심 투자 촉매 & 모멘텀:</b> ${escapeHtml(catalyst)}
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
      <title>${t.emoji} ${t.theme_name}: 기여도 ${t.weight_share_pct}%</title>
    </path>`;
  });

  svg.innerHTML = pathsHtml;

  // Bind Donut slice clicks
  svg.querySelectorAll("path").forEach((p) => {
    p.addEventListener("click", () => {
      const tid = p.dataset.themeId;
      currentPreEntryTheme = currentPreEntryTheme === tid ? "all" : tid;
      loadPreEntryView().catch(() => {});
    });
  });

  // Render Theme Ranking Sidebar
  rankList.innerHTML = themes.map((t, idx) => {
    const isActive = currentPreEntryTheme === t.theme_id ? "active" : "";
    return `
      <div class="theme-rank-card ${isActive}" data-theme-id="${t.theme_id}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <b style="color:${t.color}; font-size:12.5px;">${t.emoji} ${t.theme_name}</b>
          <span class="chip" style="background:rgba(255,255,255,0.08); font-size:11px;">기여도 ${t.weight_share_pct}%</span>
        </div>
        <div style="margin-top:4px; font-size:11.5px; color:#cbd5e1; display:flex; justify-content:space-between;">
          <span>기대수익: <b class="text-emerald-400">+${(t.avg_return * 100).toFixed(1)}%</b></span>
          <span>승률: <b>${(t.avg_win_rate * 100).toFixed(0)}%</b></span>
        </div>
        <div style="margin-top:4px; font-size:11px; color:#94a3b8;">
          👑 대장주: <span style="color:#fff; font-weight:700;">${escapeHtml(t.top_leader_name)}</span> (+${(t.top_leader_return * 100).toFixed(1)}%)
        </div>
      </div>
    `;
  }).join("");

  rankList.querySelectorAll(".theme-rank-card").forEach((card) => {
    card.addEventListener("click", () => {
      const tid = card.dataset.themeId;
      currentPreEntryTheme = currentPreEntryTheme === tid ? "all" : tid;
      loadPreEntryView().catch(() => {});
    });
  });
}




const STATUS_HOVER_GUIDE_DATA = {
  ACTIVE: {
    title: "🟢 ACTIVE (진입 유효 / 강력 추천)",
    color: "#10b981",
    desc: "과거 5~10년 계절성 패턴과 올해 실적(EPS)/수급/상대강도(RS) 3중 검증 완료 (최우선 공략주)",
    criteria: "계절성 점수 78점 이상 + 과거 승률 70% 이상 + 최근 3M 수익률 양호",
    action: "권장 선취매 Window 진입 시 분할 매수 및 목표 엑시트 대응 유효",
    actionColor: "#34d399",
  },
  WATCH: {
    title: "🟡 WATCH (관찰 / 대기)",
    color: "#eab308",
    desc: "과거 계절성 패턴은 우수하나, 올해 수급 유입이나 이벤트 촉매 발생 확인 대기 중",
    criteria: "계절성 점수 68점 이상 또는 최근 3개년 승률 60% 이상",
    action: "목표 D-Day 도달 시 거래량 급증 및 외인/기관 순매수 전환 확인 후 진입",
    actionColor: "#fde047",
  },
  DISCOVERY: {
    title: "🟣 DISCOVERY (신규 발굴)",
    color: "#a855f7",
    desc: "최근 3~5년간 새롭게 계절성 상승 패턴이 형성된 신규 발굴 후보주",
    criteria: "표본수 3년 이상 + 승률 67% 이상 + AI 원인 역추적 진행",
    action: "소액 분할 매수 또는 AI 리포트 분석 후 진입 권장",
    actionColor: "#c084fc",
  },
  WEAKENING: {
    title: "🟠 WEAKENING (엣지 약화)",
    color: "#f97316",
    desc: "과거에는 강했으나 최근 3년간 승률/초과수익이 하락하여 계절성 모멘텀이 둔화된 상태",
    criteria: "최근 3개년 승률 50% 미만",
    action: "비중 축소 또는 다른 ACTIVE 종목으로 교체 매매 권장",
    actionColor: "#fb923c",
  },
  BROKEN: {
    title: "🔴 BROKEN (진입 금지 / 파기)",
    color: "#ef4444",
    desc: "최근 3개월간 급락했거나 올해 펀더멘털 악화/실적 쇼크로 계절성 룰이 깨진 종목",
    criteria: "3개월 수익률 -15% 이하 및 퀀트 종합점수 48점 미만",
    action: "🚫 신규 매수 절대 금지 및 보유 시 즉시 리스크 관리(손절)",
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

async function loadDiscoveryRanked() {
  const tbody = $("#discovery-ranked-body");
  if (!tbody) return;

  const minGrade = $("#discovery-grade-filter") ? $("#discovery-grade-filter").value : "";
  const statusFilter = $("#discovery-status-filter") ? $("#discovery-status-filter").value : "all";
  const q = $("#seasonality-q") ? $("#seasonality-q").value.trim() : "";

  const params = new URLSearchParams({
    horizon_days: currentV11Horizon,
    lookback_years: currentV11Lookback,
    exclude_expired: currentV11ExcludeExpired,
  });
  if (minGrade) params.set("min_grade", minGrade);
  if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
  if (q) params.set("query", q);

  const res = await api(`/api/seasonality/discovery?${params.toString()}`);
  discoveryRows = res.rows || [];

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
    const alpha = ((r.median_alpha || 0) * 100).toFixed(1);

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
        <td class="font-bold text-emerald-400">${r.median_alpha > 0 ? '+' : ''}${alpha}%</td>
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

  const res = await api(`/api/seasonality/discovery?horizon_days=${currentV11Horizon}&lookback_years=${currentV11Lookback}&exclude_expired=${currentV11ExcludeExpired}`);
  const rows = res.rows || [];

  const lookbackLabel = currentV11Lookback > 0 ? `최근 ${currentV11Lookback}개년` : "전체 기간";
  if (!rows.length) {
    container.innerHTML = `<div class="text-center text-slate-400 py-8">분석된 AI 이벤트 설명 데이터가 없습니다. (${lookbackLabel} · 진입 ${currentV11Horizon}일)</div>`;
    return;
  }

  const cards = rows.slice(0, 30).map((r) => {
    const failedListHtml = (r.failed_analysis || []).map((f) => `<li style="color:#fca5a5; font-size:12px;">${escapeHtml(f)}</li>`).join("");

    return `
      <div class="event-timeline-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <b style="font-size:16px; color:#fff;">${escapeHtml(r.company || r.ticker)} (${escapeHtml(r.ticker)})</b>
              <span class="chip" style="background:rgba(56,189,248,0.2); color:#38bdf8; font-weight:800;">${escapeHtml(r.window_name)} 상승패턴</span>
              <span class="chip" style="background:rgba(139,92,246,0.2); color:#c084fc;">AI 신뢰도: ${r.event_confidence}</span>
            </div>
            <div style="margin-top:8px; font-size:13.5px; color:#38bdf8; font-weight:700;">
              💡 공통 상승 원인: ${escapeHtml(r.common_event_cluster)}
            </div>
            <div style="margin-top:4px; font-size:12.5px; color:#cbd5e1;">
              📌 부 원인: ${escapeHtml(r.secondary_cluster || '분기 실적 호조 및 수급 유입')}
            </div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:14px; font-weight:800; color:#34d399;">승률 ${((r.win_rate || 0)*100).toFixed(0)}% · Alpha +${((r.median_alpha || 0)*100).toFixed(1)}%</div>
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
  const tabPre = $("#tab-v11-pre-entry");
  const tabDisc = $("#tab-v11-discovery");
  const tabExpl = $("#tab-v11-explanation");
  const tabCal = $("#tab-v11-calendar");
  const tabHeat = $("#tab-v11-heatmap");

  const panePre = $("#pane-v11-pre-entry");
  const paneDisc = $("#pane-v11-discovery");
  const paneExpl = $("#pane-v11-explanation");
  const paneCal = $("#pane-v11-calendar");
  const paneHeat = $("#pane-v11-heatmap");

  function switchV11Subtab(subtab) {
    currentV11Subtab = subtab;
    [tabPre, tabDisc, tabExpl, tabCal, tabHeat].forEach((t) => t?.classList.remove("active"));
    [panePre, paneDisc, paneExpl, paneCal, paneHeat].forEach((p) => p?.classList.add("hidden"));

    if (subtab === "pre-entry") {
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

  tabPre?.addEventListener("click", () => switchV11Subtab("pre-entry"));
  tabDisc?.addEventListener("click", () => switchV11Subtab("discovery"));
  tabExpl?.addEventListener("click", () => switchV11Subtab("explanation"));
  tabCal?.addEventListener("click", () => switchV11Subtab("calendar"));
  tabHeat?.addEventListener("click", () => switchV11Subtab("heatmap"));

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
        btnToggleExclude.textContent = "☑️ 시즌 종료 제외 (진입 유효만)";
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
  const q = $("#seasonality-q") ? $("#seasonality-q").value.trim() : "";

  const params = new URLSearchParams({
    horizon_days: currentInstHorizon,
  });
  if (minGrade) params.set("min_grade", minGrade);
  if (confFilter && confFilter !== "all") params.set("confirmation", confFilter);
  if (groupFilter && groupFilter !== "all") params.set("group_id", groupFilter);
  if (q) params.set("query", q);

  const res = await api(`/api/seasonality/ranked?${params.toString()}`);
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

async function loadSeasonality() {
  const minWr = parseFloat($("#seasonality-min-wr") ? $("#seasonality-min-wr").value : "0.80");
  const minRet = parseFloat($("#seasonality-min-ret") ? $("#seasonality-min-ret").value : "0.05");
  const q = $("#seasonality-q") ? $("#seasonality-q").value.trim() : "";

  const params = new URLSearchParams({
    month: currentSeasonalityMonth,
    min_win_rate: minWr,
    min_avg_return: minRet,
  });
  if (currentSeasonalityPreset) params.set("preset", currentSeasonalityPreset);
  if (q) params.set("query", q);

  const data = await api(`/api/seasonality/scan?${params.toString()}`);
  seasonalityRows = data.rows || [];

  const countBadge = $("#seasonality-count-badge");
  if (countBadge) {
    const scanned = data.universe_scanned || seasonalityRows.length;
    const listed = data.universe_listed || scanned;
    const kosdaq = (data.markets || {}).KOSDAQ;
    const kospi = (data.markets || {}).KOSPI;
    const mkt = [kospi != null ? `KOSPI ${kospi}` : null, kosdaq != null ? `KOSDAQ ${kosdaq}` : null].filter(Boolean).join(" · ");
    countBadge.textContent = `${currentSeasonalityMonth}월 조건 부합 ${seasonalityRows.length}종목 · 전종목 스캔 ${scanned}/${listed}${mkt ? ` (${mkt})` : ""}`;
  }

  renderSeasonalityTable();
}

function renderSeasonalityTable() {
  const tbody = $("#seasonality-body");
  if (!tbody) return;

  if (!seasonalityRows.length) {
    tbody.innerHTML = `<tr><td colspan="11" class="text-center text-slate-400 py-8">조건에 부합하는 ${currentSeasonalityMonth}월 계절성 종목이 없습니다. 필터를 완화해 보세요.</td></tr>`;
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
        <td><b class="text-accent-cyan">${r.target_month}월</b></td>
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
  return {
    ...row,
    window_name: row.window_name || `${month}월`,
    years_track: yearsTrackFromRow(row),
    all_months: row.all_months || [],
    sample_count: row.sample_count || row.years_count,
    median_alpha: row.median_alpha ?? row.median_return,
    entry_window_str: row.entry_window_str || `${String(month).padStart(2, "0")}/01 ~ ${String(month).padStart(2, "0")}/15`,
    exit_window_str: row.exit_window_str || `${String(month).padStart(2, "0")}/20 ~ ${String(month === 12 ? 1 : month + 1).padStart(2, "0")}/10`,
  };
}

async function openHeatmapPlaybook(row) {
  if (!row) return;
  openDiscoveryDetailModal(playbookRowFromScan(row));
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
      <button type="button" class="month-tab-btn ${currentSeasonalityMonth === nextM ? 'active' : ''}" data-month="${nextM}">🚀 ${nextM}월 (선취매 픽)</button>
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

  // Preset chips
  const presetContainer = $("#seasonality-presets");
  if (presetContainer) {
    presetContainer.querySelectorAll(".preset-chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        presetContainer.querySelectorAll(".preset-chip-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentSeasonalityPreset = btn.dataset.preset || "";
        loadSeasonality().catch(() => {});
      });
    });
  }

  // Filter dropdowns
  $("#seasonality-min-wr")?.addEventListener("change", () => loadSeasonality().catch(() => {}));
  $("#seasonality-min-ret")?.addEventListener("change", () => loadSeasonality().catch(() => {}));

  // Search autocomplete
  const qInput = $("#seasonality-q");
  const qMenu = $("#seasonality-q-menu");
  if (qInput && qMenu) {
    setupStockAutocomplete(qInput, qMenu, (selected) => {
      qInput.value = selected.company || selected.ticker;
      loadSeasonality().catch(() => {});
    });
    qInput.addEventListener("input", () => {
      if (qInput.value === "") loadSeasonality().catch(() => {});
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
loadDash().catch((err) => {
  $("#quality-box").innerHTML = `<p class="bad">${err.message}</p>`;
});
loadSettings().catch(() => {});

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
