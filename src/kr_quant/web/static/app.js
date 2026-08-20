const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const titles = {
  dash: ["대시보드", "재무 점수 후보 · 시장·전략은 합산하지 않습니다"],
  market: ["시장 국면", "조사 맥락입니다. Quant 점수를 바꾸지 않습니다"],
  rank: ["점수 랭킹", "시총·거래대금 조건을 통과한 종목을 점수순으로 봅니다"],
  screens: ["골라보기", "토스 목록 이름이 아니라 우리 규칙입니다"],
  sector: ["업종", "업종 상대강도 · Quant 미합산"],
  toss: ["토스 랭킹", "급상승·급하락·거래대금 · Quant와 무관"],
  watch: ["관심종목", "메모 저장 · 점수와 무관"],
  reports: ["리포트 보관", "발간한 AI 분석 리포트와 간단 검증"],
  run: ["실행", "데모·재계산·실데이터 수집"],
  settings: ["API 설정", "키는 이 PC의 .env에만 저장됩니다"],
  flow: ["수급", "기관·외인 쌍끌이 · 사모 순매수 · Quant 미합산"],
  empty: ["빈집", "기관·외인 이탈 · 낮은 외인 지분 · 복귀 조짐"],
  trade: ["트레이딩", "퀀트 밖 쌍끌이 · 사모 매집 · 빈집 수급"],
  us13f: ["미국 13F", "SEC 기관 보유 · 신규·공통·매도 · Quant 미합산"],
  strategy: ["전략", "일봉 백테스트 · next-bar · Quant 미합산"],
};

let rankRows = [];
let guideCache = null;
let reportRows = [];

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
  closeDrawer();
  $$(".view").forEach((el) => el.classList.add("hidden"));
  $(`#view-${name}`).classList.remove("hidden");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $("#page-title").textContent = titles[name][0];
  $("#page-sub").textContent = titles[name][1];
  startLiveSync(name);
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
      loadMarket().catch(() => {});
      loadMacro().catch(() => {});
    }, 60000);
  } else if (name === "toss") {
    liveTimer = setInterval(() => loadTossRankings().catch(() => {}), 30000);
  }
}

function closeDrawer() {
  $("#drawer")?.classList.add("hidden");
  $("#drawer-back")?.classList.add("hidden");
}

function openDrawerUi() {
  $("#drawer-back")?.classList.remove("hidden");
  $("#drawer")?.classList.remove("hidden");
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

function setChip(el, text, tip) {
  if (!el) return;
  el.textContent = text;
  if (tip) {
    el.setAttribute("data-tip", tip);
    el.classList.add("has-tip");
    el.tabIndex = 0;
  }
}

function renderTop20(rows) {
  const body = $("#top20-body");
  body.innerHTML = rows
    .slice(0, 20)
    .map(
      (r) => `<tr class="clickable" data-ticker="${padTicker(r.ticker)}">
      <td class="num">${r.quant_rank ?? ""}</td>
      <td class="name-cell"><b>${r.company || r.ticker}</b><div class="meta">${padTicker(r.ticker)} · ${r.market || ""}
        <a class="ext inline" href="${naverUrl(r.ticker)}" target="_blank" rel="noopener">네이버</a>
        ${reportBadge(r.ticker)}</div>${rowNote(r.comment_short || r.comment)}</td>
      <td class="num"><span class="score">${fmt(r.quant_score)}</span></td>
      <td>${factorBars(r)}</td>
      <td class="num">${penCell(r.risk_penalty)}</td>
      <td class="num">${confCell(r.data_confidence)}</td>
    </tr>`
    )
    .join("");
}

function renderRank(q = "") {
  const needle = q.trim().toLowerCase();
  const rows = rankRows.filter((r) => {
    if (!needle) return true;
    return String(r.ticker).toLowerCase().includes(needle) || String(r.company || "").toLowerCase().includes(needle);
  });
  $("#rank-body").innerHTML = rows
    .map(
      (r) => `<tr class="clickable" data-ticker="${padTicker(r.ticker)}">
      <td class="num">${r.quant_rank ?? ""}</td>
      <td>${padTicker(r.ticker)} <a class="ext inline" href="${naverUrl(r.ticker)}" target="_blank" rel="noopener">네이버</a></td>
      <td class="name-cell">${r.company || ""}${rowNote(r.comment_short || r.comment)}</td>
      <td>${r.market || ""}</td>
      <td>${r.industry || r.sector || ""}</td>
      <td class="num"><span class="score">${fmt(r.quant_score)}</span></td>
      <td>${factorBars(r)}</td>
      <td class="num">${penCell(r.risk_penalty)}</td>
      <td class="num">${fmt((r.weighted_metric_coverage || 0) * 100, 0)}%</td>
      <td class="num">${confCell(r.data_confidence)}</td>
      <td>${reportBadge(r.ticker)}</td>
    </tr>`
    )
    .join("");
}

function reportBadge(ticker) {
  const hit = reportRows.find((x) => padTicker(x.ticker) === padTicker(ticker) && x.kind === "AI 분석 리포트");
  return hit ? `<span class="chip ok">리포트</span>` : "";
}

function renderReportList(target, rows, limit) {
  const body = $(target);
  if (!body) return;
  const show = limit ? rows.slice(0, limit) : rows;
  const wide = target === "#reports-body";
  if (!show.length) {
    body.innerHTML = `<tr><td colspan="${wide ? 8 : 5}">아직 보관한 리포트가 없습니다. 종목 상세에서 AI 분석 리포트를 발간하세요.</td></tr>`;
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
    </tr>`
    )
    .join("");
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
}

function renderFreshChip(fresh) {
  const el = $("#chip-fresh");
  if (!el) return;
  const btn = $("#btn-krx-now");
  if (!fresh) {
    setChip(el, "시세", "시세 정보가 없습니다.");
    return;
  }
  const px = fresh.price_max_date || "시세 없음";
  const lag = Number(fresh.lag_days);
  const hist = Number(fresh.price_days);
  const histTxt = hist > 0 ? ` · ${hist}일` : "";
  const stale = Boolean(fresh.stale_price || fresh.stale_screen);
  const label = stale
    ? `시세 ${px} · ${lag > 0 ? lag + "일 지연" : statusKo(fresh.status)}`
    : `시세 ${px}${histTxt}`;
  const tip = stale
    ? `받은 시세 ${px}, 기대 날짜 ${fresh.expected_price_date || "—"}. ${fresh.label || "지연"}. 오른쪽 위 시세 받기로 최근 일봉만 받으면 됩니다. 점수는 안 바뀝니다.`
    : `받은 시세 ${px}. 이력 ${hist || "—"}거래일. 기대 날짜 ${fresh.expected_price_date || "—"}.`;
  setChip(el, label, tip);
  el.classList.toggle("stale", stale);
  el.classList.toggle("fresh", fresh.status === "fresh");
  if (btn) btn.classList.toggle("primary", Boolean(fresh.stale_price));
}

function renderSchedLine(sched) {
  const el = $("#sched-line");
  if (!el || !sched) return;
  if (!sched.enabled) {
    el.textContent = "자동 시세 갱신: 꺼짐 또는 KRX 키 없음. 실행 탭에서 수동으로 받을 수 있습니다.";
    return;
  }
  const nxt = sched.next_fire ? String(sched.next_fire).replace("T", " ").slice(0, 16) : "대기";
  el.textContent = `자동 시세 갱신: 평일 ${sched.hour}:${String(sched.minute).padStart(2, "0")} KST · 다음 ${nxt} · OpenDART는 돌리지 않습니다.`;
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

function renderKpis(status, top) {
  const q = status.quality || {};
  const c = q.counts || {};
  const st = q.status || "no-run";
  $("#kpis").innerHTML = [
    ["점수 기준일", q.as_of_date || "—", "이 날짜 기준으로 재무 Quant를 계산했습니다."],
    ["조건 통과", c.universe_eligible ?? 0, "시총·거래대금·보통주 등 스크리닝 조건을 통과한 종목 수입니다. 예전 표현은 적격 유니버스입니다."],
    ["TOP20", top.length || c.top20_eligible || 0, "조건과 커버리지·신뢰도 게이트를 통과한 상위 20종목입니다."],
    ["실행 상태", statusKo(st), STATUS_TIP[st] || ""],
    ["보관 리포트", reportRows.filter((x) => x.kind === "AI 분석 리포트").length, "버튼을 눌러 저장한 AI 분석 리포트 수입니다."],
  ]
    .map(
      ([k, v, tip]) =>
        `<div class="kpi"><span class="has-tip" data-tip="${escapeHtml(tip)}" tabindex="0">${k}</span><b class="${k === "실행 상태" && st !== "success" ? "warn" : ""}">${v}</b></div>`
    )
    .join("");
}

async function openStock(ticker) {
  const data = await api(`/api/results/stock/${padTicker(ticker)}`);
  const r = data.row;
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
    .slice(0, 6)
    .map(
      (n) => `<li><a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>
        <div class="meta">${escapeHtml((n.pubDate || "").slice(0, 16))} · ${escapeHtml((n.description || "").slice(0, 90))}</div></li>`
    )
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
  const ta = data.ta || {};
  let taBlock = "";
  if (ta.ok) {
    const k = ta.stoch_k == null ? "—" : fmt(ta.stoch_k, 1);
    const d = ta.stoch_d == null ? "—" : fmt(ta.stoch_d, 1);
    const cloud = ta.ichi_cloud === "above" ? "구름 위" : ta.ichi_cloud === "below" ? "구름 아래" : ta.ichi_cloud === "inside" ? "구름 안" : "—";
    const tags = (ta.labels || []).map((t) => {
      const bull = t.includes("골든") || t.includes("구름 위") || t.includes("전환>");
      const bear = t.includes("데드") || t.includes("구름 아래") || t.includes("과매수") || t.includes("전환<");
      const cls = bull ? "up" : bear ? "down" : t.includes("과매도") ? "hot" : "";
      return tipTag(t, cls, TA_TIPS);
    }).join(" ");
    taBlock = `<article class="intro"><h3>기술적 (트레이딩)</h3>
      <p>스토캐스틱 %K <b>${k}</b> / %D <b>${d}</b> · 일목 ${escapeHtml(cloud)} · 전환 ${ta.ichi_tenkan == null ? "—" : fmt(ta.ichi_tenkan)} / 기준 ${ta.ichi_kijun == null ? "—" : fmt(ta.ichi_kijun)}</p>
      <p>${tags || ""}</p>
      <p class="hint">KRX 일봉 기준. Quant 점수에 넣지 않습니다.</p>
    </article>`;
  } else if (ta.error) {
    taBlock = `<article class="intro"><h3>기술적 (트레이딩)</h3><p class="hint">${escapeHtml(ta.error)}</p></article>`;
  }
  let yahooBlock = "";
  if (yahoo.error) {
    yahooBlock = `<article class="intro"><h3>Yahoo / yfinance (연구)</h3><p class="hint">${escapeHtml(yahoo.error)}</p></article>`;
  } else if (yahoo.last != null) {
    const rel = yahoo.vs_kospi && yahoo.vs_kospi.relative_6m;
    yahooBlock = `<article class="intro"><h3>Yahoo / yfinance (연구)</h3>
      <p>${escapeHtml(yahoo.symbol || "")} 종가 <b>${fmt(yahoo.last)}</b> · 1일 ${fmtPct(yahoo.ret_1d)} · 6개월 ${fmtPct(yahoo.ret_6m)} · 1년 ${fmtPct(yahoo.ret_1y)}</p>
      <p>52주 고점 대비 ${fmtPct(yahoo.high_52w_distance)} · MA50 ${fmt(yahoo.ma50)} · MA200 ${fmt(yahoo.ma200)}</p>
      ${rel != null ? `<p>KOSPI 대비 6개월 ${fmtPct(rel)}</p>` : ""}
      <p class="hint">${escapeHtml(yahoo.disclaimer || "Quant 점수와 KRX 공식 시세를 대체하지 않습니다.")}</p>
      ${yahoo.page ? `<p><a class="ext" href="${escapeHtml(yahoo.page)}" target="_blank" rel="noopener">Yahoo Finance</a></p>` : ""}
    </article>`;
  }
  const exp = data.explain || {};
  const expPos = (exp.positives || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const expCau = (exp.cautions || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const explainBlock = `<article class="intro">
      <h3>왜 나왔는가</h3>
      <p><b>${escapeHtml(exp.conclusion || "")}</b></p>
      <p class="hint">${escapeHtml(exp.selection_reason || "")}</p>
      ${data.comment ? `<p>${escapeHtml(data.comment)}</p>` : ""}
      ${expPos ? `<p>긍정</p><ul>${expPos}</ul>` : ""}
      ${expCau ? `<p>주의</p><ul>${expCau}</ul>` : ""}
    </article>`;
  const intro = `
    ${explainBlock}
    <article class="intro">
      <h3>종목 소개</h3>
      <p>${escapeHtml(brief.headline || `${r.company || ticker} · ${r.market || ""} ${r.industry || ""}`)}</p>
      ${encyc}
      ${(brief.paragraphs || []).map((p) => `<p>${escapeHtml(p)}</p>`).join("")}
      ${facts ? `<div class="kv">${facts}</div>` : ""}
    </article>
    ${locBlock}
    ${tossBlock}
    ${yahooBlock}
    ${taBlock}
    ${newsBlock}`;
  $("#drawer-title").textContent = `${r.company || ticker} (${padTicker(r.ticker || ticker)})`;
  $("#drawer-body").innerHTML = `
    ${intro}
    <div class="ext-links">
      ${links.map((l) => `<a class="ext" href="${l.url}" target="_blank" rel="noopener">${l.label}</a>`).join("")}
    </div>
    <p>점수 <b>${fmt(r.quant_score)}</b> / 원점수 ${fmt(r.quant_score_raw)} / penalty ${fmt(r.risk_penalty, 1)}</p>
    <p>커버리지 ${fmt((gates.coverage || r.weighted_metric_coverage || 0) * 100, 0)}% · 신뢰도 ${fmt(gates.data_confidence || r.data_confidence, 1)}</p>
    <p>${gateLine}</p>
    ${excl ? `<ul>${excl}</ul>` : ""}
    <div class="bars">
      ${factors
        .map(
          ([name, val, max]) =>
            `<div><span>${name} ${fmt(val)} / ${max}</span><div class="bar"><i style="width:${Math.max(0, Math.min(100, ((val || 0) / max) * 100))}%"></i></div></div>`
        )
        .join("")}
    </div>
    <div class="kv">
      <span>PER</span><b>${fmt(r.per)}</b>
      <span>PBR</span><b>${fmt(r.pbr)}</b>
      <span>EV/EBIT</span><b>${fmt(r.ev_ebit)}</b>
      <span>FCF yield</span><b>${fmt(r.fcf_yield, 3)}</b>
      <span>ROIC</span><b>${fmt(r.roic, 3)}</b>
      <span>ROE</span><b>${fmt(r.roe, 3)}</b>
      <span>매출 YoY</span><b>${fmt((r.revenue_yoy || 0) * 100, 1)}%</b>
      <span>영업이익 YoY</span><b>${fmt((r.op_yoy || 0) * 100, 1)}%</b>
      <span>리스크</span><b>${escapeHtml(riskNotes.join(" · ") || "해당 없음")}</b>
      <span>데이터</span><b>${escapeHtml(dataNotes.join(" · ") || "해당 없음")}</b>
    </div>
    <div class="actions">
      <button id="btn-analyze" data-ticker="${ticker}">간단 검증</button>
      <button class="primary" id="btn-report" data-ticker="${ticker}">AI 분석 리포트</button>
      <button id="btn-watch" data-ticker="${ticker}" data-company="${escapeHtml(r.company || "")}">관심종목</button>
    </div>
    <p class="hint">간단 검증은 짧은 점검입니다. AI 분석 리포트는 VER4 양식의 긴 분석입니다. 둘 다 버튼을 누를 때만 과금되고 Quant 점수는 바뀌지 않습니다.</p>
    <div id="research-box"><p>저장된 간단 검증을 불러오는 중…</p></div>
    <div id="report-box"><p>저장된 AI 분석 리포트를 불러오는 중…</p></div>
  `;
  openDrawerUi();
  const code = padTicker(r.ticker || ticker);
  $("#btn-analyze").addEventListener("click", () => runAnalyze(code).catch((err) => alert(err.message)));
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
  return `<div class="factors">${FACTOR_SPEC.map(([ch, key, max, name]) => {
    const v = Number(r[key] || 0);
    const pct = Math.max(0, Math.min(100, (v / max) * 100));
    return `<span title="${name} ${v.toFixed(1)} / ${max}"><em>${ch}</em><i><b style="width:${pct.toFixed(0)}%"></b></i></span>`;
  }).join("")}</div>`;
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

function openReportModal(rec, title) {
  modalTicker = padTicker(rec && rec.ticker);
  $("#report-modal-title").textContent = title || `${(rec && rec.company) || modalTicker || "리포트"}`;
  $("#report-modal-body").innerHTML = reportArticleHtml(rec);
  $("#report-modal").classList.remove("hidden");
  document.body.classList.add("modal-open");
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

async function runReport(ticker) {
  openReportModal({ ticker, report_markdown: "AI 분석 리포트 작성 중… 1~3분 걸릴 수 있습니다." }, "리포트 작성 중");
  if ($("#report-box")) $("#report-box").innerHTML = "<p>AI 분석 리포트 작성 중…</p>";
  const data = await api("/api/research/report", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
  renderReport(data.row);
  openReportModal(data.row);
  loadReportArchive().catch(() => {});
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
  const ver = String(status.model_version || "");
  const shortVer = (ver.match(/^(\d+\.\d+\.\d+)/) || [ver])[0];
  setChip($("#chip-model"), `모델 ${shortVer}`, `내부 버전 ${ver}. 점수 공식 식별자이며 매매 신호가 아닙니다.`);
  const qst = status.quality?.status || "no-run";
  setChip($("#chip-status"), statusKo(qst), STATUS_TIP[qst] || ver);
  setChip($("#chip-asof"), status.quality?.as_of_date ? `점수일 ${status.quality.as_of_date}` : "점수일 없음", "이 날짜 기준으로 Quant 점수를 계산했습니다.");
  renderFreshChip(status.freshness);
  renderSchedLine(status.scheduler);
  if (!$("#chip-llm")) {
    const chip = document.createElement("span");
    chip.className = "chip has-tip";
    chip.id = "chip-llm";
    chip.tabIndex = 0;
    $(".chips").appendChild(chip);
  }
  const llmName = status.llm_label || status.llm_provider || "xai";
  setChip($("#chip-llm"), `AI ${llmName}`, `리포트용 모델 ${status.llm_model || ""}. Quant 점수 계산에는 쓰지 않습니다.`);
  renderKpis(status, top.rows || []);
  renderTop20(top.rows || []);
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

async function loadMarket() {
  const box = $("#market-box");
  if (!box) return;
  const data = await api("/api/market");
  const fgHtml = renderFearGreed(data.fear_greed);
  if (!data.configured) {
    stampLive("#market-live");
    box.innerHTML = `${fgHtml}<p class="hint">${escapeHtml(data.error || "시세 없음")}</p>`;
    return;
  }
  const rows = (data.components || [])
    .map((c) => `<li>${escapeHtml(c.label)} <b>${c.value == null ? "미연결" : fmt(c.value, 1)}</b> · ${escapeHtml(c.tone)}</li>`)
    .join("");
  const ecos = data.ecos || {};
  const ecosRows = (ecos.series || [])
    .map((s) => {
      if (s.error) return `<li>${escapeHtml(s.alias || "")} — ${escapeHtml(s.error)}</li>`;
      return `<li>${escapeHtml(s.alias || s.name || "")} <b>${fmt(s.value, 2)}</b> ${escapeHtml(s.unit || "")} · ${escapeHtml(s.time || "")}</li>`;
    })
    .join("");
  box.innerHTML = `
    ${fgHtml}
    <p>내부 국면 <b>${escapeHtml(data.label || data.regime || "")}</b> · 점수 ${fmt(data.regime_score, 1)} <span class="hint">(KRX 가격 기반, 점수 미합산)</span></p>
    ${data.freshness ? `<p class="hint">시세 ${escapeHtml(data.freshness.price_max_date || "—")} · ${escapeHtml(data.freshness.label || "")}${data.freshness.stale_price ? " · 위쪽 시세 받기로 최근 일봉을 받으면 됩니다." : ""}</p>` : ""}
    <ul>${rows}</ul>
    <h3>한국은행 ECOS</h3>
    ${ecosRows ? `<ul>${ecosRows}</ul>` : `<p class="hint">${escapeHtml(ecos.error || "조회 없음")}</p>`}
    <p class="hint">${escapeHtml(ecos.disclaimer || data.disclaimer || "")}${ecos.demo_key ? " (데모 키 sample, 호출당 10행)" : ""}</p>
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

function flowTable(title, rows, amountKey) {
  if (!rows.length) return `<div class="rank-card" style="grid-column:1 / -1"><h3>${escapeHtml(title)}</h3><p class="hint">조건에 맞는 종목이 없습니다.</p></div>`;
  const body = rows
    .map((r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
      <td class="num">${i + 1}</td>
      <td class="name-cell"><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker || "")}</div>${rowNote(amountKey === "pe_krw" ? (r.comment_pe_short || r.comment_pe) : (r.comment_flow_short || r.comment_flow))}</td>
      <td class="num">${quoteCell(r)}</td>
      <td class="num">${signedInt(r.foreign_net)}</td>
      <td class="num">${signedInt(r.institution_net)}</td>
      <td class="num">${signedInt(r.pe_net)}</td>
      <td class="num">${escapeHtml(krw(r[amountKey]))}</td>
      <td class="num">${pctCell(r.ret_5d)}</td>
      <td class="num">${pctCell(r.ret_20d)}</td>
    </tr>`)
    .join("");
  return `<div class="rank-card" style="grid-column:1 / -1"><h3>${escapeHtml(title)} ${rows.length}</h3>
    <table class="rank-table"><thead><tr>
      <th>#</th><th>종목</th><th>최근가</th><th>외인(주)</th><th>기관(주)</th><th>사모(주)</th><th>추정금액</th><th>이후 5일</th><th>이후 20일</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
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
  const dual = analyzeHit(dualRows, "ret_5d");
  const pe = analyzeHit(peRows, "ret_5d");
  const dual20 = analyzeHit(dualRows, "ret_20d");
  const pe20 = analyzeHit(peRows, "ret_20d");
  const sameHorizon = dual.n && dual.avg != null && dual20.avg != null && Math.abs(dual.avg - dual20.avg) < 1e-9;
  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi"><span>쌍끌이</span><b>${dual.n}</b></div>
      <div class="kpi"><span>쌍끌이 5일 히트</span><b>${dual.hit == null ? "—" : `${(dual.hit * 100).toFixed(0)}%`}</b></div>
      <div class="kpi"><span>사모 순매수</span><b>${pe.n}</b></div>
      <div class="kpi"><span>사모 5일 히트</span><b>${pe.hit == null ? "—" : `${(pe.hit * 100).toFixed(0)}%`}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection || "토스 순매수(주수) 합산입니다. 쌍끌이는 외인·기관 동시 순매수, 사모는 토스 사모펀드 항목입니다. Quant와 무관합니다.")}</p>
    <p>스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 순매수 합산${minKrw ? ` · ${krw(minKrw)} 이상만 표시` : ""}</p>
    <p>${hitLine("쌍끌이", dual)} · 20일 평균 ${pctCell(dual20.avg)}</p>
    <p>${hitLine("사모", pe)} · 20일 평균 ${pctCell(pe20.avg)}</p>
    <div class="rank-grid">
      ${bucketTable("쌍끌이 금액구간 히트율", data.dual || [], "dual_krw")}
      ${bucketTable("사모 금액구간 히트율", data.private_equity || [], "pe_krw")}
      ${flowTable("쌍끌이 (외인·기관 동시 순매수)", dualRows, "dual_krw")}
      ${flowTable("사모펀드 순매수", peRows, "pe_krw")}
    </div>
    <p class="hint">${escapeHtml(data.disclaimer || "")} ${escapeHtml(data.quote_note || "최근가는 토스, 수급은 일별입니다.")} 추정금액·기술은 KRX 종가 기준입니다.${sameHorizon ? " 가격 이력이 짧으면 이후 20일이 5일과 같아 보일 수 있습니다." : ""}</p>
  `;
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

async function loadFlow(force) {
  const box = $("#flow-box");
  if (!box) return;
  box.innerHTML = "<p>수급 데이터를 불러오는 중…</p>";
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
    if (q && !hay.includes(q)) return false;
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
  rows.sort((a, b) => {
    if (mode === "low_foreign") return (a.foreign_holding_rate ?? 99) - (b.foreign_holding_rate ?? 99);
    return Number(b.empty_krw || 0) - Number(a.empty_krw || 0);
  });
  const hit = analyzeHit(rows, "ret_5d");
  const body = rows
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
      <td class="num">${escapeHtml(krw(r.empty_krw))}</td>
      <td class="num">${r.sell_streak || 0}</td>
      <td class="num">${pctCell(r.ret_5d)}</td>
    </tr>`
    )
    .join("");
  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(4,1fr);margin:8px 0 16px">
      <div class="kpi"><span>조건 종목</span><b>${rows.length}</b></div>
      <div class="kpi"><span>쌍매도</span><b>${(data.empty || []).length}</b></div>
      <div class="kpi"><span>복귀 조짐</span><b>${(data.comeback || []).length}</b></div>
      <div class="kpi"><span>외인 5%↓</span><b>${(data.low_foreign || []).length}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection_empty || "쌍매도는 외인·기관 동시 순매도, 지분은 토스 외인 보유비율, 복귀는 최근 1~2일 재매수입니다. Quant에 넣지 않습니다.")}</p>
    <p>스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 · ${hitLine("선택 집합", hit)}</p>
    <div class="table-wrap tall">
      <table>
        <thead>
          <tr>
            <th>#</th><th>종목</th><th>최근가</th><th>외인 지분</th><th>지분 변화</th><th>외인(주)</th><th>기관(주)</th><th>개인(주)</th><th>이탈 추정</th><th>연속매도</th><th>이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="11" class="hint">조건에 맞는 종목이 없습니다. 유형을 바꾸거나 다시 스캔해 보세요.</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">${escapeHtml(data.disclaimer || "")} 이탈 추정은 (외인+기관 순매도 주수)×종가입니다. 외인 지분은 토스 holdingRate입니다. 기관 보유비율은 이 API에 없어서 순매수로 봅니다.</p>
  `;
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
    if (q && !hay.includes(q)) return false;
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
  "구름 위": "일목균형표에서 종가가 선행스팬 A·B가 만든 구름대 위에 있습니다. 중기 지지가 발밑에 있어 추세가 강한 쪽으로 봅니다. 9-26-52 일봉이며 Quant 점수와 무관합니다.",
  "구름 아래": "종가가 일목 구름대 아래에 있습니다. 구름이 위에 저항으로 남아서, 단기 반등이 나와도 구름을 뚫기 전에는 중기 추세가 약한 구간으로 봅니다. ‘당장 나쁘다’기보다 중기 약세 배열입니다. 매도 지시가 아닙니다.",
  "구름 안": "종가가 구름 두께 안에 있습니다. 지지·저항이 겹쳐 방향이 정해지지 않은 혼조로 봅니다. 돌파 전까지는 추세 신호로 쓰지 않는 편이 낫습니다.",
  "전환 골든": "일목 전환선(9일)이 기준선(26일)을 아래에서 위로 돌파한 날입니다. 단기 중심이 중기 중심을 앞지른 교차입니다. 구름 위치와 같이 봐야 하고, 단독 매수 신호가 아닙니다.",
  "전환 데드": "일목 전환선이 기준선을 위에서 아래로 뚫은 날입니다. 단기 중심이 중기 중심 아래로 내려온 교차입니다. 데드는 데드 크로스(약세 교차)이지 종목 자체의 위험이 아닙니다.",
  "전환>기준": "전환선(9일 중심)이 이미 기준선(26일 중심) 위에 있습니다. 골든 크로스가 ‘뚫는 순간’이라면, 이것은 ‘이미 강세 배열’입니다. 단기 추세가 중기보다 위에 있다는 뜻이고, 구름 아래면 배열과 위치가 어긋난 상태일 수 있습니다.",
  "전환<기준": "전환선이 기준선 아래에 있습니다. 단기 중심이 중기 중심보다 낮아 일목에서 기본 약세 배열입니다. 역시 구름 위치와 같이 봐야 합니다.",
};

const SETUP_TIPS = {
  쌍끌이: "같은 기간 외국인과 기관이 둘 다 순매수한 종목입니다. 토스 투자자 매매의 주수 합산이며 Quant 점수와 무관합니다.",
  사모매집: "토스 분류의 사모펀드가 이틀 이상 연속 순매수했습니다. 기관 전체와 다를 수 있습니다.",
  사모순매수: "토스 분류 사모펀드가 기간 합산으로 순매수입니다. 연속 매수는 아직 짧습니다.",
  "쌍끌이+사모": "외인·기관 쌍끌이와 사모 순매수가 겹칩니다. 수급이 한쪽으로 몰린 연구 필터입니다.",
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
  const rows = filterTradeRows(all).sort((a, b) => setupNotional(b) - setupNotional(a));
  const outside = all.filter((r) => !r.in_quant);
  const dualN = outside.filter((r) => r.dual).length;
  const peN = outside.filter((r) => r.pe_buy || r.pe_accum).length;
  const emptyN = outside.filter((r) => r.empty).length;
  const hit = analyzeHit(rows, "ret_5d");
  const taBull = all.filter((r) => !r.in_quant && taMatch(r, "ta_bull")).length;
  const confluence = all.filter((r) => !r.in_quant && taMatch(r, "confluence")).length;
  const body = rows
    .map(
      (r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
      <td class="num">${i + 1}</td>
      <td class="name-cell"><b>${escapeHtml(r.company || "")}</b>
        <div class="meta">${escapeHtml(r.ticker || "")} ${setupTags(r)}
          ${r.in_quant ? `<span class="tag">Q${r.quant_rank ?? ""}</span>` : tipTag("퀀트 밖", "hot", SETUP_TIPS)}</div>${rowNote(r.comment_trade_short || r.comment_trade)}</td>
      <td class="num">${quoteCell(r)}</td>
      <td class="num">${r.ta && r.ta.stoch_k != null ? fmt(r.ta.stoch_k, 1) : "—"}
        <div class="meta">${r.ta && r.ta.stoch_d != null ? "D " + fmt(r.ta.stoch_d, 1) : ""}</div></td>
      <td>${taTags(r) || '<span class="hint">—</span>'}</td>
      <td class="num">${signedInt(r.foreign_net)}</td>
      <td class="num">${signedInt(r.institution_net)}</td>
      <td class="num">${signedInt(r.pe_net)}${r.pe_streak ? `<div class="meta">${r.pe_streak}일</div>` : ""}</td>
      <td class="num">${escapeHtml(krw(setupNotional(r)))}</td>
      <td class="num">${pctCell(r.ret_5d)}</td>
    </tr>`
    )
    .join("");
  box.innerHTML = `
    <div class="kpis" style="grid-template-columns:repeat(5,1fr);margin:8px 0 16px">
      <div class="kpi"><span>스캔</span><b>${data.scanned || 0}</b></div>
      <div class="kpi"><span>퀀트 밖 쌍끌이</span><b>${dualN}</b></div>
      <div class="kpi"><span>퀀트 밖 사모</span><b>${peN}</b></div>
      <div class="kpi"><span>기술 강세</span><b>${taBull}</b></div>
      <div class="kpi"><span>수급+기술</span><b>${confluence}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection_trade || "수급 셋업에 일봉 스토캐스틱·일목을 붙입니다. 기본은 퀀트 TOP100 밖입니다. 매수 지시가 아닙니다.")}</p>
    <p>거래대금·토스 랭킹 위주 ${data.scanned || 0}종목 · ${data.days || 5}거래일 · 빈집 ${emptyN} · ${hitLine("선택 집합", hit)}</p>
    <div class="table-wrap tall">
      <table>
        <thead>
          <tr>
            <th>#</th><th>종목 · 셋업</th><th>최근가</th><th class="has-tip" data-tip="${escapeHtml("스토캐스틱 %K입니다. 최근 5일 고저 대비 종가 위치(0~100)를 3일 평활합니다. 20 아래는 과매도, 80 위는 과매수. %D는 그 선의 3일 평균입니다. 일봉이며 Quant와 무관합니다.")}" tabindex="0">스토 %K</th><th class="has-tip" data-tip="${escapeHtml("KRX 일봉 스토캐스틱 5,3,3과 일목 9-26-52 태그입니다. 태그에 마우스를 올리면 뜻을 볼 수 있습니다. 매수·매도 지시가 아닙니다.")}" tabindex="0">기술</th><th>외인(주)</th><th>기관(주)</th><th>사모(주)</th><th>추정금액</th><th>이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="10" class="hint">조건에 맞는 종목이 없습니다. 퀀트 제외를 끄거나 셋업·기술을 바꿔 보세요.</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">${escapeHtml(data.disclaimer || "")} ${escapeHtml(data.quote_note || "최근가는 토스, 수급·기술은 일봉입니다.")} 스토캐스틱 5,3,3 · 일목 9-26-52. 파란·노란 기술 태그에 마우스를 올리면 뜻을 볼 수 있습니다. 매수 지시가 아닙니다.</p>
  `;
}

let screenId = "value_growth";

function renderSectors(data) {
  const box = $("#sector-box");
  if (!box) return;
  if (data.error && !(data.rows || []).length) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error)}</p>`;
    return;
  }
  const body = (data.rows || [])
    .map(
      (r) => `<tr class="clickable" data-ticker="${escapeHtml((r.names && r.names[0] && r.names[0].ticker) || "")}">
        <td class="num">${r.rank}</td>
        <td><b>${escapeHtml(r.name)}</b><div class="meta">${r.n}종목</div>${rowNote(r.comment)}</td>
        <td><span class="sector-score">${fmt(r.score, 1)}</span>
          <div class="meta">${r.delta == null ? "" : (r.delta >= 0 ? "+" : "") + fmt(r.delta, 1)}</div></td>
        <td><span class="tag has-tip" data-tip="${escapeHtml(r.comment || "")}">${escapeHtml(r.state_ko || r.state)}</span></td>
        <td class="num">${r.rs ?? "—"}</td>
        <td class="num">${r.breadth ?? "—"}</td>
        <td class="num">${r.earnings ?? "—"}</td>
        <td>${(r.names || []).map((n) => escapeHtml(n.company || n.ticker)).join(" · ")}</td>
      </tr>`
    )
    .join("");
  box.innerHTML = `
    <p class="hint">${escapeHtml(data.selection || "")}</p>
    <div class="table-wrap tall"><table>
      <thead><tr>
        ${thTip("순위", "업종 연구 점수 순위입니다. 재무 Quant 순위가 아닙니다.")}
        ${thTip("업종", "조건 통과 종목의 산업 분류입니다.")}
        ${thTip("점수", "상대강도 25 · 확산 20 · 실적 20 · 구성 15 · 가치 10 · 가속 10. Quant에 넣지 않습니다.")}
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
  const body = (data.rows || [])
    .map(
      (r, i) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
        <td class="num">${i + 1}</td>
        <td class="name-cell"><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)} · ${escapeHtml(r.industry || "")}</div>${rowNote(r.comment_short)}</td>
        <td class="num"><span class="score">${fmt(r.quant_score)}</span></td>
        <td class="num">${r.quant_rank ?? "—"}</td>
        <td>${factorBars(r)}</td>
      </tr>`
    )
    .join("");
  box.innerHTML = `
    <h3>${escapeHtml(data.name || "")} ${data.n ?? 0}종목</h3>
    <p class="hint">${escapeHtml(data.how || "")}</p>
    <div class="table-wrap tall"><table>
      <thead><tr><th>#</th><th>종목</th><th>점수</th><th>순위</th><th>구성</th></tr></thead>
      <tbody>${body || "<tr><td colspan=5>조건에 맞는 종목이 없습니다. 수급 목록이면 수급 탭을 먼저 스캔하세요.</td></tr>"}</tbody>
    </table></div>
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>
  `;
}

async function loadScreens(id) {
  if (id) screenId = id;
  const box = $("#screen-box");
  if (box) box.innerHTML = "<p>목록을 걸러 보는 중…</p>";
  renderScreens(await api(`/api/screens?id=${encodeURIComponent(screenId)}`));
}

let strategyCache = null;
let portfolioCache = null;

function renderStrategy(data) {
  const box = $("#strategy-box");
  if (!box) return;
  const rows = data.rows || [];
  const catalog = (data.catalog || [])
    .map((c) => (typeof c === "string" ? c : c.name || c.id))
    .filter(Boolean)
    .join(" · ");
  const body = rows
    .map((r) => {
      const best = (r.strategies || [])[0] || {};
      const paramsKo = r.best_params_ko || best.params_ko || "";
      const familyKo = r.best_family_ko || best.family_ko || "";
      const comment = r.best_comment || best.comment || r.warning || "";
      return `<tr class="clickable" data-ticker="${escapeHtml(r.ticker || "")}">
        <td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker || "")} · ${r.bars || 0}일</div></td>
        <td>${tipTag(r.best_name || "—", "", TERM_TIPS)}${familyKo ? tipTag(familyKo, "", TERM_TIPS) : ""}
          <div class="params-ko">${escapeHtml(paramsKo)}</div></td>
        <td>${tipTag(r.stability_label || "—", r.stability_label === "HIGH" ? "up" : r.stability_label === "LOW" ? "down" : "hot", TERM_TIPS)}</td>
        <td class="num has-tip" data-tip="${escapeHtml(TERM_TIPS["샤프"])}">${best.sharpe == null ? "—" : fmt(best.sharpe, 2)}</td>
        <td class="num has-tip" data-tip="${escapeHtml(TERM_TIPS.OOS + " " + TERM_TIPS["샤프"])}">${best.oos_sharpe == null ? "—" : fmt(best.oos_sharpe, 2)}</td>
        <td class="num has-tip" data-tip="${escapeHtml(TERM_TIPS.WF + " 양수는 그 창에서 이후 구간 수익이 플러스인 비율입니다.")}">${best.wf_hit == null ? "—" : `${(best.wf_hit * 100).toFixed(0)}%`} <span class="meta">${best.wf_windows || 0}창</span></td>
        <td class="num has-tip" data-tip="${escapeHtml(TERM_TIPS.MDD)}">${pctCell(best.max_drawdown)}</td>
        <td class="num has-tip" data-tip="${escapeHtml("신호 다음날 시가로 들어가 청산까지 간 왕복 횟수입니다. 너무 적으면 숫자 하나가 성과를 좌우합니다.")}">${best.trade_count ?? "—"}</td>
        <td class="strat-note">${escapeHtml(comment)}</td>
      </tr>`;
    })
    .join("");
  box.innerHTML = `
    <p>실행 <span${tipAttr("신호가 나온 날 종가가 아니라, 다음 거래일 시가에 사거나 팝니다. 같은 날 종가 체결을 가정하지 않습니다.")}>${escapeHtml(data.execution || "next-bar")}</span>
      · 슬리피지 <span${tipAttr("체결을 0.05%(5bp) 불리하게 가정합니다. 실제 호가·수수료가 아닙니다.")}>${data.slippage_bps ?? 5}bp</span>
      · 전략 ${escapeHtml(catalog)}</p>
    <p class="hint">${escapeHtml(data.selection || "파라미터는 학습 구간에서만 고릅니다. 이후 구간 샤프와 walk-forward는 검증용입니다.")} 열 이름·LOW·평균회귀에 마우스를 올리면 뜻을 볼 수 있습니다.</p>
    <div class="table-wrap tall"><table>
      <thead><tr>
        ${thTip("종목", "Quant TOP20입니다. 일봉 개수는 이 종목에 쌓인 KRX 가격 이력입니다. 80일 전후면 창이 짧아 LOW가 나기 쉽습니다.")}
        ${thTip("연구 후보 전략", "학습 구간 점수가 가장 높은 단순 규칙입니다. 평균회귀는 되돌아오길 기대하고, 추세는 방향을 따라갑니다. 태그에 마우스를 올리세요.")}
        ${thTip("안정성", "HIGH/MEDIUM/LOW. 학습 밖 샤프·매매 횟수·walk-forward를 같이 봅니다. LOW는 순위가 아닙니다.")}
        ${thTip("전체 샤프", TERM_TIPS["샤프"] + " 전 구간이라 학습에 맞춘 값이 섞여 낙관적일 수 있습니다.")}
        ${thTip("OOS 샤프", TERM_TIPS.OOS + " " + TERM_TIPS["샤프"])}
        ${thTip("WF 양수", TERM_TIPS.WF + " 양수는 창마다 이후 구간 수익이 플러스인 비율입니다. 0%면 창을 밀 때마다 검증 구간이 마이너스였다는 뜻입니다.")}
        ${thTip("MDD", TERM_TIPS.MDD)}
        ${thTip("매매수", "왕복 횟수입니다. 0~2회면 숫자 하나로 샤프가 출렁입니다.")}
        ${thTip("분석", "이 후보를 고른 이유와 설정, 학습/검증 숫자를 한글로 풀어 쓴 칸입니다.")}
      </tr></thead>
      <tbody>${body || "<tr><td colspan=9>TOP20 백테스트를 실행하세요.</td></tr>"}</tbody>
    </table></div>
    <p class="hint">${escapeHtml(data.disclaimer || "")} LOW는 순위처럼 쓰지 않습니다. 파라미터 탐색은 학습 구간에만 하고 walk-forward로 다시 봅니다.</p>
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
    box.innerHTML = "<p>TOP20 일봉 백테스트 중… Quant 점수는 바꾸지 않습니다.</p>";
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
      <div class="kpi"><span>펀드</span><b>${data.scanned || (data.filers || []).length}</b></div>
      <div class="kpi"><span>신규</span><b>${(data.new || []).length}</b></div>
      <div class="kpi"><span>공통(2+)</span><b>${(data.common || []).length}</b></div>
      <div class="kpi"><span>청산</span><b>${(data.exits || []).length}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection || "SEC EDGAR 13F-HR 분기 말 보유입니다. 신규·확대·청산은 직전 분기 대비 주수 변화입니다. Quant에 넣지 않습니다.")}</p>
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
  box.innerHTML = `${kpis}
    <div class="table-wrap tall">${table}</div>
    ${err ? `<p class="hint">일부 실패: ${escapeHtml(err)}</p>` : ""}
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>`;
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
  renderUs13f(data);
}

async function loadWatch() {
  const box = $("#watch-box");
  if (!box) return;
  const data = await api("/api/watchlist");
  const rows = data.rows || [];
  if (!rows.length) {
    box.innerHTML = "<p class='hint'>관심종목이 없습니다. 종목 상세에서 추가하세요.</p>";
    return;
  }
  box.innerHTML = `<ul>${rows
    .map(
      (r) =>
        `<li><a class="ext inline" href="#" data-open="${padTicker(r.ticker)}">${escapeHtml(r.company || "")} ${padTicker(r.ticker)}</a>
         ${r.note ? `<div class="meta">${escapeHtml(r.note)}</div>` : ""}
         <button class="ghost" data-unwatch="${padTicker(r.ticker)}">삭제</button></li>`
    )
    .join("")}</ul>`;
  box.querySelectorAll("[data-open]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      openStock(el.dataset.open).catch((err) => alert(err.message));
    });
  });
  box.querySelectorAll("[data-unwatch]").forEach((el) => {
    el.addEventListener("click", () => removeWatch(el.dataset.unwatch).catch((err) => alert(err.message)));
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

async function loadMacro() {
  const box = $("#macro-box");
  if (!box) return;
  const data = await api("/api/macro");
  const fred = data.fred || {};
  const yahoo = data.yahoo || {};
  const fredRows = (fred.series || [])
    .map((s) => {
      if (s.error) return `<li>${escapeHtml(s.label)} — ${escapeHtml(s.error)}</li>`;
      const delta = s.delta == null ? "" : ` (${s.delta >= 0 ? "+" : ""}${fmt(s.delta, 2)})`;
      return `<li>${escapeHtml(s.label)} <b>${fmt(s.value, 2)}</b> ${escapeHtml(s.unit || "")} · ${escapeHtml(s.date || "")}${escapeHtml(delta)}</li>`;
    })
    .join("");
  const idxRows = (yahoo.indexes || [])
    .map((s) => {
      if (s.error) return `<li>${escapeHtml(s.label)} — ${escapeHtml(s.error)}</li>`;
      return `<li>${escapeHtml(s.label)} <b>${fmt(s.last, 2)}</b> · 1일 ${fmtPct(s.ret_1d)} · 1년 ${fmtPct(s.ret_1y)}</li>`;
    })
    .join("");
  const idxViz = (yahoo.indexes || [])
    .filter((s) => !s.error && s.last != null)
    .map((s) => {
      const chg = Number(s.ret_1d);
      const pct = Number.isNaN(chg) ? 0 : chg * (Math.abs(chg) <= 1 ? 100 : 1);
      const cls = pct > 0 ? "up" : pct < 0 ? "down" : "";
      const width = Math.max(4, Math.min(100, Math.abs(pct) * 12));
      return `<div class="macro-row"><span>${escapeHtml(s.label)}</span><i><em class="${cls}" style="width:${width}%"></em></i><b class="${cls}">${fmt(s.last, 2)} · ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%</b></div>`;
    })
    .join("");
  const fredViz = (fred.series || [])
    .filter((s) => !s.error && s.value != null)
    .map((s) => {
      const d = Number(s.delta);
      const cls = Number.isNaN(d) ? "" : d > 0 ? "up" : d < 0 ? "down" : "";
      const width = Number.isNaN(d) ? 8 : Math.max(6, Math.min(100, Math.abs(d) * 40));
      const delta = Number.isNaN(d) ? "" : ` · ${d >= 0 ? "+" : ""}${fmt(d, 2)}`;
      return `<div class="macro-row"><span>${escapeHtml(s.label)}</span><i><em class="${cls}" style="width:${width}%"></em></i><b>${fmt(s.value, 2)} ${escapeHtml(s.unit || "")}${escapeHtml(delta)}</b></div>`;
    })
    .join("");
  box.innerHTML = `
    <h3>비교지수 (1일)</h3>
    ${idxViz || (yahoo.error ? `<p class="hint">${escapeHtml(yahoo.error)}</p>` : "<p class='hint'>지수 없음</p>")}
    <h3>금리 · 물가</h3>
    ${fred.configured ? fredViz || "<p class='hint'>관측치 없음</p>" : `<p class="hint">${escapeHtml(fred.error || "설정에서 FRED 키를 넣으세요.")}</p>`}
    <p class="hint">막대는 최근 변화 크기입니다. Quant 점수에 들어가지 않습니다. 한국 공식 시세는 KRX입니다.</p>
  `;
}

function metaLine(el, info) {
  el.textContent = info.configured ? `${info.masked} (${info.length}자)` : "미설정";
  el.className = "meta " + (info.configured ? "ok" : "warn");
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

function renderJob(job) {
  if (!job) return;
  const kinds = {
    demo: "데모",
    screen: "재계산",
    live: "실데이터",
    "krx-prices": "시세 받기",
    "krx-history": "시세 이력",
  };
  $("#job-chip").textContent = `${statusKo(job.status)}${job.kind ? " · " + (kinds[job.kind] || job.kind) : ""}`;
  $("#job-log").textContent = (job.logs || []).join("\n");
  $("#job-log").scrollTop = $("#job-log").scrollHeight;
}

async function pollJob() {
  const job = await api("/api/jobs");
  renderJob(job);
  if (job.status === "running") {
    setTimeout(pollJob, 1500);
  } else if (job.status === "success") {
    await loadDash();
  }
}

async function startJob(kind) {
  const payload = {
    kind: kind.startsWith("live") ? "live" : kind,
    as_of: $("#run-asof").value.trim() || "auto",
    source: "live",
    lookback_days: Number($("#run-lookback").value),
    max_corps: Number($("#run-max").value),
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
  await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
  pollJob();
}

$$(".nav-btn").forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));
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
  const title = (el.textContent || "").trim().split("\n")[0];
  box.innerHTML = `<b>${escapeHtml(title)}</b><p>${escapeHtml(text)}</p>`;
  box.classList.remove("hidden");
  const r = el.getBoundingClientRect();
  const maxW = Math.min(340, window.innerWidth - 24);
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
  if (e.key === "Escape") closeDrawer();
});
if ($("#btn-krx-now")) {
  $("#btn-krx-now").addEventListener("click", () => startJob("krx-prices").catch((err) => alert(err.message)));
}
if ($("#btn-dash-reload")) {
  $("#btn-dash-reload").addEventListener("click", () => loadDash().catch((err) => alert(err.message)));
}
if ($("#market-refresh")) {
  $("#market-refresh").addEventListener("click", () => {
    loadMarket().catch((err) => alert(err.message));
    loadMacro().catch(() => {});
  });
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
  if (e.target.closest("a.ext")) return;
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

loadDash().catch((err) => {
  $("#quality-box").innerHTML = `<p class="bad">${err.message}</p>`;
});
loadSettings().catch(() => {});
