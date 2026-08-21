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
  sunzi: ["손자 五事", "道·天·地·將·法 다각도 심층 기업 분석"],
  nps: ["국민연금 5%", "OpenDART 국민연금 5% 이상 대량보유 공시 추적"],
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
  $("#page-title").textContent = titles[name][0];
  $("#page-sub").textContent = titles[name][1];
  const modeBadge = $("#top-mode-badge");
  if (modeBadge) {
    if (name === "dash" || name === "rank" || name === "screens") {
      modeBadge.className = "top-mode-badge quant-active";
      modeBadge.innerHTML = "⭐ <b>재무 Quant 엔진 적용</b>";
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
    loadMarket(true).catch((err) => alert(err.message));
    loadMacro(true).catch(() => {});
  }
  if (name === "strategy") {
    loadStrategy().catch((err) => alert(err.message));
    loadPortfolio().catch(() => {});
  }
  if (name === "watch") loadWatch().catch((err) => alert(err.message));
  if (name === "reports") loadReportArchive().catch(() => {});
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
        ${reportBadge(r.ticker)} ${faChip(r)}</div>${rowNote(r.comment_short || r.comment)}</td>
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
    return String(r.ticker).toLowerCase().includes(needle) || String(r.company || "").toLowerCase().includes(needle);
  });
  const ordered = sortedCopy(rows, "rank", "quant_rank", "asc");
  $("#rank-body").innerHTML = ordered
    .map(
      (r) => `<tr class="clickable" data-ticker="${padTicker(r.ticker)}">
      <td class="num">${rankMedal(r.quant_rank)}</td>
      <td>${padTicker(r.ticker)} <a class="ext inline" href="${naverUrl(r.ticker)}" target="_blank" rel="noopener">네이버</a></td>
      <td class="name-cell"><b>${r.company || ""}</b> ${faChip(r)}${rowNote(r.comment_short || r.comment)}</td>
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
  applyPriceChrome(currentView);
}

function renderSchedLine(sched) {
  const el = $("#sched-line");
  if (!el || !sched) return;
  if (!sched.enabled) {
    el.textContent = "자동 시세 갱신: 꺼짐 또는 KRX 키 없음. 실행 탭에서 수동으로 받을 수 있습니다.";
    return;
  }
  const nxt = sched.next_fire ? String(sched.next_fire).replace("T", " ").slice(0, 16) : "대기";
  el.textContent = `자동 시세 갱신: 평일 ${sched.hour}:${String(sched.minute).padStart(2, "0")} KST · 다음 ${nxt} · 시세 10일 뒤 관심종목 공식수급. Quant·OpenDART 전량은 안 돌립니다.`;
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
  const statusTip = statusExplainTip(lastStatusExplain, STATUS_TIP[st] || "");
  $("#kpis").innerHTML = [
    ["점수 기준일", q.as_of_date || "—", "이 날짜 기준으로 재무 Quant를 계산했습니다."],
    ["조건 통과", c.universe_eligible ?? 0, "시총·거래대금·보통주 등 스크리닝 조건을 통과한 종목 수입니다. 예전 표현은 적격 유니버스입니다."],
    ["TOP20", top.length || c.top20_eligible || 0, "조건과 커버리지·신뢰도 게이트를 통과한 상위 20종목입니다."],
    ["실행 상태", statusKo(st), statusTip, true],
    ["보관 리포트", reportRows.filter((x) => x.kind === "AI 분석 리포트").length, "버튼을 눌러 저장한 AI 분석 리포트 수입니다."],
  ]
    .map(
      ([k, v, tip, open]) =>
        `<div class="kpi${open ? " clickable-kpi" : ""}"${open ? ' data-open-status="1"' : ""}><span class="has-tip" data-tip="${escapeHtml(tip)}" tabindex="0">${k}</span><b class="${k === "실행 상태" && st !== "success" ? "warn" : ""}">${v}</b></div>`
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
  const timing = data.timing || {};
  let timingBlock = "";
  if (timing.ok) {
    const tfs = timing.timeframes || {};
    const cards = ["short", "mid", "long"]
      .map((k) => {
        const b = tfs[k] || {};
        const ret = b.return == null ? "—" : `${(Number(b.return) * 100).toFixed(1)}%`;
        return `<div class="tf-card ${escapeHtml(b.trend || "")}"><span>${escapeHtml(b.label || k)}</span>
          <b>${escapeHtml(b.trend_ko || "—")}</b>
          <div class="meta">${b.ok ? `수익률 ${ret} · 거래량 ${escapeHtml(b.volume_state_ko || "—")}` : "표본 부족"}</div></div>`;
      })
      .join("");
    const conf = Number(timing.confidence || 0);
    timingBlock = `<article class="intro">
      <h3>타이밍 신뢰도</h3>
      <p>상태 <b>${escapeHtml(timing.state_ko || "")}</b> · 신뢰 <b>${fmt(conf, 0)}</b>
        ${timing.volume_state_ko ? ` · 거래량 ${escapeHtml(timing.volume_state_ko)}` : ""}
        ${timing.as_of ? ` · 시세 ${escapeHtml(timing.as_of)}` : ""}</p>
      <div class="conf-meter"><i style="width:${Math.max(0, Math.min(100, conf))}%"></i></div>
      <div class="tf-grid">${cards}</div>
      <p>${escapeHtml(timing.comment || "")}</p>
    </article>`;
  } else {
    timingBlock = `<article class="intro"><h3>타이밍 신뢰도</h3><p class="hint">${escapeHtml(timing.error || "가격 이력이 짧거나 없어 단기·중기·장기를 못 그렸습니다.")}</p></article>`;
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
  $("#drawer-title").textContent = `${r.company || ticker} (${padTicker(r.ticker || ticker)})`;
  $("#drawer-body").innerHTML = `
    <div class="stock-grid">
      <div>
        ${explainBlock}
        <article class="intro">
          <h3>종목 소개</h3>
          <p>${escapeHtml(brief.headline || `${r.company || ticker} · ${r.market || ""} ${r.industry || ""}`)}</p>
          ${encyc}
          ${(brief.paragraphs || []).map((p) => `<p>${escapeHtml(p)}</p>`).join("")}
          ${facts ? `<div class="kv">${facts}</div>` : ""}
        </article>
        ${locBlock}
        <p>점수 <b>${fmt(r.quant_score)}</b> / 원점수 ${fmt(r.quant_score_raw)} / penalty ${fmt(r.risk_penalty, 1)}</p>
        <p>커버리지 ${fmt((gates.coverage || r.weighted_metric_coverage || 0) * 100, 0)}% · 신뢰도 ${fmt(gates.data_confidence || r.data_confidence, 1)}</p>
        ${data.fa && data.fa.fa_label ? `<p>${faChip({ fa_gate_pass: data.fa.fa_gate_pass, fa_comment: data.fa.comment, fa_reasons_ko: data.fa.fa_reasons_ko })} <span class="meta">법 점수 ${fmt(data.fa.fa_score, 0)}</span></p>
        <p class="hint">${escapeHtml(data.fa.comment || "")}</p>` : ""}
        ${renderSeekingAlphaScorecard(data.scorecard)}
        ${fiveStrip(data)}
        ${criticCard(data.sunzi && data.sunzi.critic)}
        ${sunziCard(data.tian)}
        ${sunziCard(data.di)}
        ${sunziCard(data.dao)}
        ${sunziCard(data.jiang)}
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
      </div>
      <div>
        ${timingBlock}
        ${flow90Block(data.flow90)}
        ${eventsBlock(data.events)}
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
  return `<article class="intro">
    <h3>전략 검토 ${escapeHtml(panel.posture_ko || panel.posture)} · ${fmt(panel.score, 0)}</h3>
    <p>${escapeHtml(panel.comment || "")}</p>
    <p class="meta">${escapeHtml(axisLine)}</p>
    <p>합의된 이야기: ${escapeHtml(panel.consensus || "")}</p>
    <p>다른 보기: ${escapeHtml(panel.variant || "")}</p>
    ${panel.no_action_required ? "<p><b>지금은 움직이지 않는 쪽이 낫습니다.</b></p>" : ""}
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
    return `<span class="tag up has-tip" data-tip="${escapeHtml(r.fa_comment || "법 통과. Quant 점수는 그대로입니다.")}">法 통과</span>`;
  }
  if (r.fa_gate_pass === false) {
    const why = (r.fa_reasons_ko || []).join(" ") || r.fa_comment || "법 미달";
    return `<span class="tag down has-tip" data-tip="${escapeHtml(why)}">法 미달</span>`;
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
  setChip($("#chip-llm"), `AI ${llmName}`, `리포트용 모델 ${status.llm_model || ""}. Quant 점수 계산에는 쓰지 않습니다.`);
  dashRows = top.rows || [];
  renderKpis(status, dashRows);
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

function renderKrSentiment(sent) {
  if (!sent || !sent.components) return "";
  const st = sent.state || "NEUTRAL";
  const stKo = sent.state_ko || "중립";
  const score = fmt(sent.score, 1);
  const comps = Object.entries(sent.components || {}).map(([, c]) => {
    return `<div class="sentiment-item">
      <span>${escapeHtml(c.label)} (비중 ${c.weight}%)</span>
      <b>${fmt(c.score, 1)}점</b>
    </div>`;
  }).join("");

  return `
    <div class="sentiment-box">
      <div class="sentiment-head">
        <div>
          <h3>자체 한국 시장 공포·탐욕 지수 (KR Market Sentiment)</h3>
          <span class="hint">KRX 일봉 + 외인 5일 수급 기반 100점 만점 자체 감성 지수 · Quant 점수 미포함</span>
        </div>
        <div class="sentiment-score-badge ${st}">
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
    ${krSentHtml}
    ${fgHtml}
    <p>내부 국면 <b>${escapeHtml(data.label || data.regime || "")}</b> · 점수 ${fmt(data.regime_score, 1)} <span class="hint">(KRX 일봉 · 장 마감 후 시세 받기 · 점수 미합산)</span></p>
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

function flowTable(title, rows, amountKey, tabId) {
  const scope = tabId || (amountKey === "pe_krw" ? "flowPe" : "flowDual");
  if (!rows.length) {
    return `<div class="rank-card"><h3>${escapeHtml(title)}</h3><p class="hint">조건에 맞는 종목이 없습니다.</p></div>`;
  }
  const ordered = sortedCopy(rows, scope, amountKey, "desc");
  const vis = flowLimit[scope] || FLOW_FIRST;
  const shown = ordered.slice(0, vis);
  const left = ordered.length - shown.length;
  const body = shown
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
  const more = left > 0
    ? `<p class="more-line"><button type="button" class="ghost" data-flow-more="${escapeHtml(scope)}">더보기 ${Math.min(FLOW_STEP, left)}종목 (${shown.length}/${ordered.length})</button></p>`
    : `<p class="hint">${ordered.length}종목 전부입니다.</p>`;
  return `<div class="rank-card"><h3>${escapeHtml(title)} ${ordered.length}</h3>
    <table class="rank-table" data-scope="${scope}"><thead><tr>
      <th>#</th>
      <th class="sortable" data-sort="company">종목</th>
      <th class="sortable" data-sort="last">최근가</th>
      <th class="sortable" data-sort="foreign_net">외인(주)</th>
      <th class="sortable" data-sort="institution_net">기관(주)</th>
      <th class="sortable" data-sort="pe_net">사모(주)</th>
      <th class="sortable" data-sort="${amountKey}">추정금액</th>
      <th class="sortable" data-sort="ret_5d">이후 5일</th>
      <th class="sortable" data-sort="ret_20d">이후 20일</th>
    </tr></thead><tbody>${body}</tbody></table>${more}</div>`;
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
    { id: "dual", name: "쌍끌이", rows: dualRows, key: "dual_krw", title: "쌍끌이 (외인·기관 동시 순매수)" },
    { id: "pe", name: "사모", rows: peRows, key: "pe_krw", title: "사모펀드 순매수" },
    { id: "dual_pe", name: "쌍끌이+사모", rows: filterAmount(data.dual_pe || [], "dual_krw", minKrw), key: "dual_krw", title: "쌍끌이+사모" },
    { id: "dual_pe_retail", name: "+개인이탈", rows: filterAmount(data.dual_pe_retail || [], "dual_krw", minKrw), key: "dual_krw", title: "쌍끌이+사모+개인이탈" },
    { id: "other_corp", name: "기타법인", rows: data.other_corp || [], key: "other_corp_krw", title: "기타법인 순매수" },
    { id: "pension", name: "기금 가세", rows: data.pension || [], key: "pension_krw", title: "기금 가세 (쌍끌이·사모와 겹침)" },
    { id: "summary", name: "요약", rows: [], key: "", title: "금액구간 히트율" },
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
        `<button type="button" class="${t.id === flowTab ? "on" : ""}" data-flow-tab="${t.id}">${escapeHtml(t.name)}${t.id === "summary" ? "" : ` ${t.rows.length}`}</button>`
    )
    .join("");
  const active = tabs.find((t) => t.id === flowTab) || tabs[0];
  let panel = "";
  if (active.id === "summary") {
    panel = `<div class="rank-grid">${bucketTable("쌍끌이 금액구간 히트율", data.dual || [], "dual_krw")}${bucketTable("사모 금액구간 히트율", data.private_equity || [], "pe_krw")}</div>
      <p>${hitLine("쌍끌이", dual)} · 20일 평균 ${pctCell(dual20.avg)}</p>
      <p>${hitLine("사모", pe)} · 20일 평균 ${pctCell(pe20.avg)}</p>`;
  } else if (active.id === "other_corp" && !active.rows.length) {
    panel = `<p class="hint">토스 응답에 기타법인 항목이 없거나 순매수가 없습니다. 키가 있으면 이 탭에 붙습니다.</p>`;
  } else {
    panel = flowTable(active.title, active.rows, active.key, `flow-${active.id}`);
  }
  box.innerHTML = `
    ${asofBanner(asof)}
    <div class="kpis" style="grid-template-columns:repeat(6,1fr);margin:8px 0 16px">
      <div class="kpi clickable-kpi" data-flow-tab="dual"><span>쌍끌이</span><b>${dual.n}</b></div>
      <div class="kpi"><span>쌍끌이 5일 히트</span><b>${dual.hit == null ? "—" : `${(dual.hit * 100).toFixed(0)}%`}</b></div>
      <div class="kpi clickable-kpi" data-flow-tab="pe"><span>사모 순매수</span><b>${pe.n}</b></div>
      <div class="kpi clickable-kpi" data-flow-tab="dual_pe"><span>쌍끌이+사모</span><b>${(data.dual_pe || []).length}</b></div>
      <div class="kpi clickable-kpi" data-flow-tab="dual_pe_retail"><span>+개인이탈</span><b>${(data.dual_pe_retail || []).length}</b></div>
      <div class="kpi clickable-kpi" data-flow-tab="other_corp"><span>기타법인</span><b>${(data.other_corp || []).length}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection || "토스 순매수(주수) 합산입니다. 쌍끌이의 기관은 기관합계이며 연기금이 아닙니다.")}</p>
    <p>스캔 ${data.scanned || 0}종목 · ${data.days || 5}거래일 순매수 합산${minKrw ? ` · ${krw(minKrw)} 이상만 표시` : ""} · 탭마다 처음 12종목, 더보기는 10종목씩입니다.</p>
    <div class="h-tabs">${tabBtns}</div>
    <div class="flow-panel">${panel}</div>
    <p class="hint">${escapeHtml(data.disclaimer || "")} ${escapeHtml(data.quote_note || "최근가는 토스, 수급은 일별입니다.")} 추정금액·기술은 KRX 종가 기준입니다.${sameHorizon ? " 가격 이력이 짧으면 이후 20일이 5일과 같아 보일 수 있습니다." : ""} 열 이름을 누르면 오름/내림 정렬합니다.</p>
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

function sunziTone(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return "";
  if (n >= 70) return "ok";
  if (n >= 45) return "warn";
  return "bad";
}

async function loadSunzi() {
  const box = $("#sunzi-box");
  if (!box) return;
  box.innerHTML = "<p>五事 오버레이를 계산하는 중…</p>";
  const data = await api("/api/sunzi?n=40");
  if (!data.configured) {
    box.innerHTML = `<p class="hint">${escapeHtml(data.error || "결과가 없습니다.")}</p>`;
    return;
  }
  const tian = data.tian || {};
  const legend = (data.legend || [])
    .map((x) => `<li><b>${escapeHtml(x.han)} ${escapeHtml(x.ko)}</b> — ${escapeHtml(x.where)}</li>`)
    .join("");
  const rows = data.rows || [];
  if (currentView === "sunzi") {
    setPageAsOf(
      `天 ${tian.regime_ko || "—"} · 法통과 ${data.fa_pass_n || 0}/${data.n || 0}종목`,
      "五事는 조사 오버레이입니다. Quant 순위를 바꾸지 않습니다."
    );
  }
  box.innerHTML = `
    <div class="five-grid">
      <div class="five-card"><span>天 시장</span><b>${fmt(tian.score, 0)}</b><p>${escapeHtml(tian.regime_ko || "")}</p></div>
      <div class="five-card"><span>법 통과</span><b>${data.fa_pass_n || 0}</b><p>A-후보 / ${data.n || 0}종목</p></div>
      <div class="five-card"><span>조사 종목</span><b>${data.n || 0}</b><p>Quant 순위 상위</p></div>
    </div>
    <p class="hint">${escapeHtml(data.disclaimer || "")}</p>
    <ul>${legend}</ul>
    <div class="table-wrap">
      <table data-scope="sunzi">
        <thead>
          <tr>
            <th class="sortable" data-sort="quant_rank">#</th>
            <th class="sortable" data-sort="company">종목</th>
            <th class="sortable" data-sort="quant_score">Quant</th>
            <th class="sortable" data-sort="dao">道</th>
            <th class="sortable" data-sort="tian">天</th>
            <th class="sortable" data-sort="di">地</th>
            <th class="sortable" data-sort="jiang">將</th>
            <th class="sortable" data-sort="fa">法</th>
            <th>법</th>
          </tr>
        </thead>
        <tbody>
          ${sortedCopy(rows, "sunzi", "quant_rank", "asc")
            .map(
              (r) => `<tr class="clickable" data-ticker="${escapeHtml(r.ticker)}">
            <td class="num">${r.quant_rank ?? "—"}</td>
            <td><b>${escapeHtml(r.company || "")}</b><div class="meta">${escapeHtml(r.ticker)} · ${escapeHtml(r.industry || "")}</div></td>
            <td class="num">${fmt(r.quant_score, 1)}</td>
            <td class="num ${sunziTone(r.dao)}">${fmt(r.dao, 0)}</td>
            <td class="num ${sunziTone(r.tian)}">${fmt(r.tian, 0)}</td>
            <td class="num ${sunziTone(r.di)}">${fmt(r.di, 0)}</td>
            <td class="num ${sunziTone(r.jiang)}">${fmt(r.jiang, 0)}</td>
            <td class="num ${sunziTone(r.fa)}">${fmt(r.fa, 0)}</td>
            <td>${faChip(r)}</td>
          </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  paintSortHeaders("sunzi");
  box.querySelectorAll("tr.clickable[data-ticker]").forEach((tr) =>
    tr.addEventListener("click", () => openStock(tr.dataset.ticker).catch((err) => alert(err.message)))
  );
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
    <p class="hint">${escapeHtml(data.selection_empty || "쌍매도는 외인·기관 동시 순매도, 지분은 토스 외인 보유비율, 복귀는 최근 1~2일 재매수입니다. Quant에 넣지 않습니다.")}</p>
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
  const rows = sortedCopy(filterTradeRows(all), "trade", "setup_notional", "desc");
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
  const when = fmtWhen(data.fetched_at);
  const px = lastStatus?.freshness?.price_max_date;
  const asof = [when ? `수급 스캔 ${when}` : "", px ? `KRX 일봉 ${px} (스토·일목)` : ""]
    .filter(Boolean)
    .join(" · ") || "트레이딩 데이터 시점 없음";
  if (currentView === "trade") {
    setPageAsOf(asof, "수급은 토스, 스토캐스틱·일목은 KRX 일봉입니다. 다시 스캔하면 수급이 갱신됩니다.");
  }
  box.innerHTML = `
    ${asofBanner(asof)}
    <div class="kpis" style="grid-template-columns:repeat(5,1fr);margin:8px 0 16px">
      <div class="kpi"><span>스캔</span><b>${data.scanned || 0}</b></div>
      <div class="kpi"><span>퀀트 밖 쌍끌이</span><b>${dualN}</b></div>
      <div class="kpi"><span>퀀트 밖 사모</span><b>${peN}</b></div>
      <div class="kpi"><span>기술 강세</span><b>${taBull}</b></div>
      <div class="kpi"><span>수급+기술</span><b>${confluence}</b></div>
    </div>
    <p class="hint">${escapeHtml(data.selection_trade || "수급 셋업에 일봉 스토캐스틱·일목 기술 지표를 결합한 스캔입니다.")}</p>
    <p>거래대금·토스 랭킹 위주 ${data.scanned || 0}종목 · ${data.days || 5}거래일 · 빈집 ${emptyN} · ${hitLine("선택 집합", hit)}</p>
    <div class="table-wrap tall">
      <table data-scope="trade">
        <thead>
          <tr>
            <th>#</th>
            <th class="sortable" data-sort="company">종목 · 셋업</th>
            <th class="sortable" data-sort="last">최근가</th>
            <th class="sortable has-tip" data-sort="stoch_k" data-tip="${escapeHtml("스토캐스틱 %K입니다. 최근 5일 고저 대비 종가 위치(0~100)를 3일 평활합니다. 20 아래는 과매도, 80 위는 과매수.")}" tabindex="0">스토 %K</th>
            <th class="has-tip" data-tip="${escapeHtml("KRX 일봉 스토캐스틱 5,3,3과 일목 9-26-52 기술적 분석 태그입니다.")}" tabindex="0">기술</th>
            <th class="sortable" data-sort="foreign_net">외인(주)</th>
            <th class="sortable" data-sort="institution_net">기관(주)</th>
            <th class="sortable" data-sort="pe_net">사모(주)</th>
            <th class="sortable" data-sort="setup_notional">추정금액</th>
            <th class="sortable" data-sort="ret_5d">이후 5일</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="10" class="hint">조건에 맞는 종목이 없습니다. 퀀트 제외를 끄거나 셋업·기술을 바꿔 보세요.</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">${escapeHtml(data.quote_note || "최근가는 토스, 수급·기술은 일봉입니다.")} 스토캐스틱 5,3,3 · 일목 9-26-52. 열 이름을 누르면 최근가·수급 금액으로 정렬할 수 있습니다.</p>
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
      <div class="sector-phase-box leading">
        <div class="sector-phase-header">
          <span>🌟 선행 (Leading)</span>
          <span>${leadingRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(leadingRows)}</div>
      </div>
      <div class="sector-phase-box improving">
        <div class="sector-phase-header">
          <span>📈 개선 (Improving)</span>
          <span>${improvingRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(improvingRows)}</div>
      </div>
      <div class="sector-phase-box weakening">
        <div class="sector-phase-header">
          <span>⚠️ 보통/약화 (Neutral)</span>
          <span>${weakeningRows.length}개</span>
        </div>
        <div class="sector-phase-chips">${renderPhaseChips(weakeningRows)}</div>
      </div>
      <div class="sector-phase-box lagging">
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
  const when = fmtWhen(data.fetched_at);
  const bars = (data.rows || []).map((r) => Number(r.bars || 0)).filter((n) => n > 0);
  const minBars = bars.length ? Math.min(...bars) : 0;
  const asof = [when ? `백테스트 ${when}` : "", minBars ? `종목당 ${minBars}일+` : "", lastStatus?.freshness?.price_max_date ? `KRX 시세 ${lastStatus.freshness.price_max_date}` : ""]
    .filter(Boolean)
    .join(" · ") || "전략 결과 시점 없음";
  if (currentView === "strategy") {
    setPageAsOf(asof, "KRX 일봉으로 돌린 시각입니다. 이력이 짧으면 LOW가 나옵니다. TOP20 백테스트로 다시 돌리세요.");
  }
  box.innerHTML = `
    ${asofBanner(asof)}
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

async function loadWatch() {
  const box = $("#watch-box");
  if (!box) return;
  const data = await api("/api/watchlist");
  const rows = data.rows || [];
  if (!rows.length) {
    box.innerHTML = "<p class='hint'>관심종목이 없습니다. 종목 상세에서 추가하세요.</p>";
    setPageAsOf("관심종목은 로컬 메모입니다. 시세 시점이 없습니다.", "직접 저장한 목록입니다.");
    return;
  }
  if (currentView === "watch") {
    setPageAsOf(`관심종목 ${rows.length}개 · 로컬 메모`, "시세·수급을 받지 않습니다. 종목 상세에서 추가·삭제합니다.");
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

    return `
      <div class="macro-card">
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
      <h3>글로벌 매크로 바로미터 (지수 · 환율 · 금·원유 · 비트코인 · 금리)</h3>
      <p class="hint">TradingEconomics 스타일 30일/60일 시계열 차트 및 실시간 등락률 · Quant 점수 미합산</p>
      <div class="macro-card-grid">
        ${cards}
      </div>
    </div>
  `;
}

function renderSeekingAlphaScorecard(card) {
  if (!card || !card.factors || !card.factors.length) return "";
  const dec = card.decision || "HOLD";
  const decKo = card.decision_ko || "보유 관망";
  const rows = (card.factors || []).map((f) => {
    const gradeClean = String(f.grade || "").replace("+", "_PLUS").replace("-", "_MINUS");
    const sub = (f.submetrics || []).map((s) => `${escapeHtml(s.name)} ${escapeHtml(s.display)}`).join(" · ");
    return `<div class="sa-factor-row">
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
        <div class="sa-decision ${dec}">
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
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div>
          <h3 style="margin:0;font-size:15px;color:#fff;">📅 주식시장 역사적 계절성 분석 & 월별 전략 가이드 (Market Seasonality Playbook)</h3>
          <span class="hint">코스피 30개년 1~12월 역사적 월별 수익률, 상승 승률, 강세/약세 섹터 및 포트폴리오 비중 전략</span>
        </div>
      </div>

      <div class="season-diag-box">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
          <div class="season-diag-badge ${toneCls}">
            ${season.current_month_name} 계절성: ${escapeHtml(cur.theme || cur.tone || "")} (${strat.tone || ""})
          </div>
          <div class="season-diag-cycle">
            <span style="color:#60a5fa;font-weight:700;">${escapeHtml(strat.cycle_name || "")}</span>
            <span class="meta" style="margin-left:6px;">${escapeHtml(strat.cycle_comment || "")}</span>
          </div>
        </div>

        <div class="season-diag-desc" style="margin-bottom:12px;">
          <b>전략 총평:</b> ${escapeHtml(strat.desc || "")}
        </div>

        <!-- Strategy & Sector Playbook Grid -->
        <div class="season-playbook-grid">
          <div class="season-playbook-box">
            <span class="season-playbook-title">⚖️ 권장 포트폴리오 비중</span>
            <div style="display:flex; justify-content:space-between; font-size:12px; margin:6px 0 4px;">
              <span>주식 <b style="color:#34d399;">${stockRatio}%</b></span>
              <span>현금 <b style="color:#fbbf24;">${cashRatio}%</b></span>
            </div>
            <div style="height:8px; background:#1e293b; border-radius:99px; display:flex; overflow:hidden;">
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
          <div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e293b; font-size:12px;">
            <b style="color:#60a5fa;">💡 이 달의 핵심 실전 트레이딩 체크리스트:</b>
            <ul style="margin:4px 0 0; padding-left:18px; color:#cbd5e1;">
              ${tactics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}
            </ul>
          </div>
        ` : ""}
      </div>

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

async function loadMacro(refresh) {
  const briefBox = $("#brief-box");
  if (!briefBox && !$("#news-box")) return;
  const data = await api(`/api/macro${refresh ? "?refresh=true" : ""}`);
  const brief = data.brief || {};
  const news = data.news || {};
  const fred = data.fred || {};
  const yahoo = data.yahoo || {};
  const yencarry = data.yencarry || {};
  const grouped = data.grouped_assets || {};
  const cc = data.commodities_crypto || {};
  const seasonality = data.seasonality;

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
      ${renderYenCarryCard(yencarry)}
      <div class="brief-head">
        ${renderStanceCard({ ...overall, title: "종합" })}
        ${renderStanceCard({ ...kr, title: "국내" })}
        ${renderStanceCard({ ...us, title: "국제" })}
      </div>
      ${renderTradingEconomicsMacroCards(grouped, cc)}
      ${renderSeasonalitySection(seasonality)}
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
            .slice(0, 5)
            .map(
              (n) => `<li><a class="ext inline" href="${escapeHtml(n.link)}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>
                <div class="meta">${escapeHtml((n.pubDate || "").slice(0, 22))} · ${escapeHtml((n.description || "").slice(0, 90))}</div></li>`
            )
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
        <p class="hint">${escapeHtml(news.disclaimer || "네이버 검색 헤드라인입니다. Quant에 넣지 않습니다.")}</p>
      `;
    }
  }
  const asofBits = [];
  const dates = brief.as_of || {};
  if (lastStatus?.freshness?.price_max_date) asofBits.push(`국면 시세 ${lastStatus.freshness.price_max_date}`);
  if (dates.ecos) asofBits.push(`한은 ${dates.ecos}`);
  if (dates.fred) asofBits.push(`FRED ${dates.fred}`);
  if (dates.yahoo) asofBits.push(`지수 ${dates.yahoo}`);
  if (news.fetched_at) asofBits.push(`뉴스 ${fmtWhen(news.fetched_at)}`);
  if (currentView === "market") {
    setPageAsOf(asofBits.join(" · ") || `매크로 수신 ${fmtWhen(data.fetched_at) || ""}`, "국내 금리는 한국은행, 국제는 FRED, 뉴스는 네이버 검색입니다. Quant와 합산하지 않습니다.");
  }
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
  $("#job-chip").textContent = `${statusKo(job.status)}${job.kind ? " · " + (JOB_KINDS[job.kind] || job.kind) : ""}`;
  $("#job-log").textContent = (job.logs || []).join("\n");
  $("#job-log").scrollTop = $("#job-log").scrollHeight;
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
  if (e.key === "Escape") {
    closeDrawer();
    closeStatusModal();
  }
});
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
      await loadMacro(true);
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
      await loadMacro(true);
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
}

applyPriceChrome("dash");
setupInvestorSubtabs();
loadDash().catch((err) => {
  $("#quality-box").innerHTML = `<p class="bad">${err.message}</p>`;
});
loadSettings().catch(() => {});

function reloadCurrentView() {
  const name = currentView || "dash";
  const p = [loadDash()];
  if (name === "market") {
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
  else if (name === "watch") p.push(loadWatch());
  else if (name === "reports") p.push(loadReportArchive());
  return Promise.all(p);
}
