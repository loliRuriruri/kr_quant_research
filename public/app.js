const $ = (s) => document.querySelector(s);
const tip = $("#tip");
let SNAP = null;
let sortKey = "quant_rank";
let sortDir = 1;

const KIND_KO = { official: "공식값", observed: "직접관측(공식 입력으로 계산)", model: "모델추정", exploration: "탐색 전용" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(v, d = 1) {
  if (v == null || v === "" || Number.isNaN(Number(v))) return "미수집";
  return Number(v).toLocaleString("ko-KR", { maximumFractionDigits: d, minimumFractionDigits: 0 });
}

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return "미수집";
  return `${(Number(v) * 100).toFixed(1)}%`;
}

function factText(f) {
  if (!f || f.missing || f.value == null) return `<span class="missing">미수집</span>`;
  if (typeof f.value === "number" && /yield|margin|roe|roic|return|yoy|cagr/i.test(f.formula || "")) return fmtPct(f.value);
  return esc(typeof f.value === "number" ? fmt(f.value, Math.abs(f.value) >= 20 ? 1 : 2) : f.value);
}

function factCard(title, f) {
  if (!f) f = { missing: true, display: "미수집" };
  const val = f.missing ? `<span class="missing">미수집</span>` : factText(f);
  return `<article class="fact" data-tip="${esc(tipPayload(title, f))}">
    <span class="meta">${esc(title)}</span>
    <b>${val}</b>
    <div class="meta">${esc(f.as_of || "기준일 미수집")} · ${esc(KIND_KO[f.kind] || f.kind || "")}</div>
  </article>`;
}

function tipPayload(title, f) {
  if (!f) return title;
  return [
    title,
    `값: ${f.missing ? "미수집" : f.value}`,
    `기준일: ${f.as_of || "미수집"}`,
    `출처: ${f.source || "미수집"}`,
    `최신성: ${f.freshness || f.as_of || "미수집"}`,
    `구분: ${KIND_KO[f.kind] || f.kind || "미수집"}`,
    `계산식: ${f.formula || "미수집"}`,
    `누락: ${f.missing ? "예" : "아니오"}`,
    `경고: ${f.warning || "없음"}`,
    `한계: ${f.limit || "투자 판단의 근거로만 참고"}`,
  ].join("\n");
}

function sparkHtml(arr) {
  if (!arr || !arr.length) return `<span class="missing">미수집</span>`;
  const min = Math.min(...arr);
  const max = Math.max(...arr);
  const span = max - min || 1;
  return `<div class="spark" aria-hidden="true">${arr.map((v) => {
    const h = 6 + ((v - min) / span) * 30;
    return `<i style="height:${h.toFixed(1)}px"></i>`;
  }).join("")}</div>`;
}

function bars(scorecard) {
  const factors = (scorecard && scorecard.factors) || [];
  if (!factors.length) return `<p class="muted">팩터 기여도 미수집</p>`;
  return `<div class="bars">${factors.map((f) => {
    const pct = Number(f.percentile || f.pct || 0);
    return `<div class="bar"><span>${esc(f.label || f.name)}</span><em><b style="width:${Math.max(0, Math.min(100, pct))}%"></b></em><span>${esc(f.grade || fmt(pct, 0))}</span></div>`;
  }).join("")}</div>`;
}

function setTip(e) {
  const node = e.target.closest("[data-tip]");
  if (!node) { tip.classList.add("hidden"); return; }
  tip.textContent = node.dataset.tip;
  tip.classList.remove("hidden");
  const x = Math.min(window.innerWidth - 340, e.clientX + 12);
  const y = Math.min(window.innerHeight - 12, e.clientY + 12);
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}

async function loadSnap() {
  const res = await fetch("./data/snapshot.json", { cache: "no-cache" });
  if (!res.ok) throw new Error("스냅샷을 찾지 못했습니다.");
  SNAP = await res.json();
  const meta = SNAP.meta || {};
  $("#asof-chip").textContent = `업데이트 기준 ${meta.as_of_date || "미수집"} · 모델 ${meta.model_version || "미수집"}`;
  $("#build-line").textContent = `생성 ${meta.generated_at || "미수집"} · 재검산 ${meta.recompute_pass || 0}/${meta.recompute_total || 0} · 해시 ${(meta.result_hash || "미수집").slice(0, 12)}`;
}

function route() {
  const hash = (location.hash || "#/market").replace(/^#/, "");
  const parts = hash.split("/").filter(Boolean);
  const page = parts[0] || "market";
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#/${page}`));
  if (page === "stock") renderStock(parts[1]);
  else if (page === "watch") renderWatch();
  else if (page === "rank") renderRank();
  else if (page === "flow") renderFlow();
  else if (page === "sources") renderSources();
  else if (page === "qa") renderQa();
  else renderMarket();
}

function renderMarket() {
  const m = SNAP.market || {};
  const q = SNAP.quality || {};
  const counts = m.counts || {};
  const fresh = m.freshness || {};
  $("#app").innerHTML = `
    <section class="stack">
      <div class="grid">
        <div class="card kpi"><h3>스크리닝 상태</h3><b>${esc(m.quality_status || "미수집")}</b><small>${esc((m.explain && m.explain.summary) || "")}</small></div>
        <div class="card kpi"><h3>유니버스</h3><b>${fmt(counts.universe_eligible, 0)}</b><small>스코어 ${fmt(counts.scored, 0)} · 제외 ${fmt(counts.excluded, 0)}</small></div>
        <div class="card kpi"><h3>TOP20 가능</h3><b>${fmt(counts.top20_eligible, 0)}</b><small>TOP100 ${fmt(counts.top100_eligible, 0)}</small></div>
        <div class="card kpi"><h3>가격 최신성</h3><b>${esc((fresh.price_max || fresh.prices_max || "미수집") + "")}</b><small>기대일 ${esc((fresh.expected_price_date || "미수집") + "")}</small></div>
      </div>
      <div class="two">
        <div class="card">
          <h2>TOP20</h2>
          <p class="meta">퀀트 점수 상위. 클릭하면 종목 상세로 이동합니다.</p>
          ${miniTable(m.top20 || [])}
        </div>
        <div class="card">
          <h2>경고</h2>
          ${(m.warnings || []).length ? (m.warnings || []).map((w) => `<p class="warn">${esc(w.label)} <span class="meta">${esc(w.fix)}</span></p>`).join("") : "<p class='muted'>운영 경고 없음</p>"}
          <h2 style="margin-top:16px;">데이터 원칙</h2>
          <p class="meta">KRX·OpenDART가 기본. KIS·ECOS·FRED는 오버레이. 네이버는 미수록. available_date ≤ run_date. 주문 없음.</p>
        </div>
      </div>
    </section>`;
}

function miniTable(rows) {
  if (!rows.length) return `<p class="missing">미수집</p>`;
  return `<div class="table-wrap"><table><thead><tr><th>#</th><th>종목</th><th>점수</th><th>시장</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td>${esc(r.quant_rank ?? "미수집")}</td><td><a class="ticker" href="#/stock/${esc(r.ticker)}">${esc(r.company)}</a> <span class="meta">${esc(r.ticker)}</span></td><td>${r.quant_score == null ? "미수집" : fmt(r.quant_score, 1)}</td><td>${esc(r.market)}</td></tr>`).join("")}
  </tbody></table></div>`;
}

function renderWatch() {
  const rows = SNAP.watchlist || [];
  $("#app").innerHTML = `<section class="card"><h2>관심 종목</h2>
    <p class="meta">로컬 관심 목록을 스냅샷에 복사했습니다. 점수가 없으면 미수집이며 0으로 채우지 않습니다.</p>
    ${!rows.length ? "<p class='missing'>관심 종목 미수집</p>" : `<div class="table-wrap"><table><thead><tr><th>종목</th><th>순위</th><th>점수</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td><a class="ticker" href="#/stock/${esc(r.ticker)}">${esc(r.company)}</a> <span class="meta">${esc(r.ticker)}</span></td>
        <td>${r.quant_rank ?? "<span class=missing>미수집</span>"}</td>
        <td>${r.quant_score == null ? "<span class=missing>미수집</span>" : fmt(r.quant_score, 1)}</td></tr>`).join("")}
    </tbody></table></div>`}
  </section>`;
}

function renderRank() {
  let rows = [...(SNAP.ranking || [])];
  const q = ($("#q") && $("#q").value || "").trim().toLowerCase();
  const mkt = $("#mkt") ? $("#mkt").value : "";
  if (q) rows = rows.filter((r) => `${r.company} ${r.ticker} ${r.industry}`.toLowerCase().includes(q));
  if (mkt) rows = rows.filter((r) => r.market === mkt);
  rows.sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return (va > vb ? 1 : va < vb ? -1 : 0) * sortDir;
  });
  $("#app").innerHTML = `<section>
    <div class="filters">
      <input id="q" placeholder="종목·코드·산업 검색" value="${esc(q)}" />
      <select id="mkt">
        <option value="">전체 시장</option>
        <option value="KOSPI" ${mkt === "KOSPI" ? "selected" : ""}>KOSPI</option>
        <option value="KOSDAQ" ${mkt === "KOSDAQ" ? "selected" : ""}>KOSDAQ</option>
      </select>
      <span class="meta">${rows.length}종목 · 정렬 ${esc(sortKey)}</span>
    </div>
    <div class="table-wrap"><table>
      <thead><tr>
        <th data-sort="quant_rank">순위</th><th>종목</th><th data-sort="quant_score">점수</th>
        <th data-sort="value_score">가치</th><th data-sort="quality_score">품질</th>
        <th data-sort="growth_score">성장</th><th data-sort="momentum_score">모멘텀</th>
        <th data-sort="financial_score">안정</th><th data-sort="data_confidence">신뢰</th>
      </tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td>${r.quant_rank ?? "미수집"}</td>
        <td><a class="ticker" href="#/stock/${esc(r.ticker)}">${esc(r.company)}</a> <span class="meta">${esc(r.ticker)} · ${esc(r.market)}</span></td>
        <td>${r.quant_score == null ? "미수집" : fmt(r.quant_score, 1)}</td>
        <td>${r.value_score == null ? "미수집" : fmt(r.value_score, 1)}</td>
        <td>${r.quality_score == null ? "미수집" : fmt(r.quality_score, 1)}</td>
        <td>${r.growth_score == null ? "미수집" : fmt(r.growth_score, 1)}</td>
        <td>${r.momentum_score == null ? "미수집" : fmt(r.momentum_score, 1)}</td>
        <td>${r.financial_score == null ? "미수집" : fmt(r.financial_score, 1)}</td>
        <td>${r.data_confidence == null ? "미수집" : fmt(r.data_confidence, 1)}</td>
      </tr>`).join("")}</tbody>
    </table></div>
  </section>`;
  $("#q").addEventListener("input", () => renderRank());
  $("#mkt").addEventListener("change", () => renderRank());
  document.querySelectorAll("th[data-sort]").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.sort;
    if (sortKey === k) sortDir *= -1; else { sortKey = k; sortDir = k === "quant_rank" ? 1 : -1; }
    renderRank();
  }));
}

function renderStock(ticker) {
  const code = String(ticker || "").padStart(6, "0");
  const s = (SNAP.stocks || {})[code];
  if (!s) {
    $("#app").innerHTML = `<section class="card"><h2>${esc(code)}</h2><p class="missing">이 종목의 상세 스냅샷이 없습니다. 유니버스 밖이거나 미수집입니다.</p><p><a class="ticker" href="#/rank">랭킹으로</a></p></section>`;
    return;
  }
  const rec = s.recompute || {};
  $("#app").innerHTML = `<section class="stack">
    <div class="card">
      <h2>${esc(s.company)} <span class="meta">${esc(s.ticker)} · ${esc(s.market)} · ${esc(s.industry)}</span></h2>
      <p class="meta">기준 ${esc(s.as_of)} · 컷오프 ${esc(s.cutoff_ts || "미수집")}</p>
      ${s.exclusions && s.exclusions.length ? s.exclusions.map((e) => `<span class="chip warn">${esc(e.label)}</span>`).join("") : '<span class="chip">유니버스 포함</span>'}
      ${(s.data_flags || []).map((f) => `<span class="chip">${esc(f)}</span>`).join("")}
      <div style="margin-top:10px">${sparkHtml(s.sparkline)}</div>
    </div>
    <div class="grid">
      ${factCard("퀀트 점수", s.scores && s.scores.quant)}
      ${factCard("순위", s.scores && s.scores.rank)}
      ${factCard("신뢰도", s.confidence)}
      ${factCard("순위 변화", s.scores && s.scores.rank_change)}
    </div>
    <div class="two">
      <div class="card"><h2>팩터 기여도</h2>${bars(s.scorecard)}
        <div class="grid" style="margin-top:10px">
          ${factCard("가치", s.scores && s.scores.value)}
          ${factCard("품질", s.scores && s.scores.quality)}
          ${factCard("성장", s.scores && s.scores.growth)}
          ${factCard("모멘텀", s.scores && s.scores.momentum)}
          ${factCard("안정", s.scores && s.scores.stability)}
        </div>
      </div>
      <div class="card">
        <h2>검증 · 재검산</h2>
        <p>팩터 합 ${rec.sum_of_factors ?? "미수집"} − 감점 ${rec.risk_penalty ?? "미수집"} = ${rec.expected ?? "미수집"}</p>
        <p>스냅샷 점수 ${rec.actual ?? "미수집"} · ${rec.match ? "<span class=good>일치</span>" : "<span class=warn>불일치 또는 입력 미수집</span>"}</p>
        <p class="meta">${esc(rec.formula || "")}</p>
      </div>
    </div>
    <div class="card"><h2>재무·밸류에이션</h2>
      <div class="grid">
        ${Object.entries(s.valuation || {}).map(([k, f]) => factCard(k, f)).join("")}
        ${Object.entries(s.financials || {}).map(([k, f]) => factCard(k, f)).join("")}
        ${Object.entries(s.growth || {}).map(([k, f]) => factCard(k, f)).join("")}
        ${Object.entries(s.leverage || {}).map(([k, f]) => factCard(k, f)).join("")}
      </div>
    </div>
    <div class="two">
      <div class="card"><h2>수급</h2><p class="missing">${esc((s.flow && s.flow.status) || "미수집")}</p><p class="meta">${esc((s.flow && s.flow.note) || "")}</p></div>
      <div class="card"><h2>공시·뉴스</h2>
        <p class="missing">${esc((s.filings && s.filings.status) || "미수집")}</p>
        <p class="meta">${esc((s.filings && s.filings.note) || "")} <a class="ticker" href="${esc((s.filings && s.filings.link) || "https://opendart.fss.or.kr")}" target="_blank" rel="noopener">OpenDART</a></p>
        <p class="meta">${esc((s.news && s.news.note) || "")}</p>
      </div>
    </div>
    <p class="meta">${esc((s.ai && s.ai.note) || "")}</p>
  </section>`;
}

function renderFlow() {
  const f = SNAP.flow || {};
  const table = (rows, title) => `<div class="card"><h2>${esc(title)}</h2>
    ${!rows || !rows.length ? "<p class='missing'>미수집</p>" : `<div class="table-wrap"><table><thead><tr><th>종목</th><th>외인</th><th>기관합계</th><th>기금</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td><a class="ticker" href="#/stock/${esc(r.ticker)}">${esc(r.company || r.ticker)}</a></td>
        <td>${r.foreign_net == null ? "미수집" : fmt(r.foreign_net, 0)}</td>
        <td>${r.institution_net == null ? "미수집" : fmt(r.institution_net, 0)}</td>
        <td>${r.fund_net == null ? "미수집" : fmt(r.fund_net, 0)}</td></tr>`).join("")}</tbody></table></div>
        <p class="meta">${esc((rows[0] && rows[0].fund_note) || "기금은 연기금으로 바꾸지 않았습니다.")}</p>`}
    </div>`;
  $("#app").innerHTML = `<section class="stack">
    <div class="card"><h2>수급 오버레이</h2>
      <p>${f.missing ? "<span class=missing>미수집</span>" : esc(f.disclaimer || "")}</p>
      <p class="meta">출처 ${esc(f.source || "KIS")} · Quant 미사용 · 가격만으로 수급을 만들지 않음</p>
    </div>
    ${table(f.dual, "외인+기관 동반")}
    ${table(f.fund, "기금 순매수 (FUND, 연기금 아님)")}
  </section>`;
}

function renderSources() {
  const rows = SNAP.sources || [];
  $("#app").innerHTML = `<section class="card"><h2>데이터 출처와 신뢰등급</h2>
    <div class="table-wrap"><table><thead><tr><th>출처</th><th>역할</th><th>범위</th><th>구분</th><th>Quant</th><th>링크</th></tr></thead><tbody>
      ${rows.map((s) => `<tr>
        <td>${esc(s.id)}</td><td>${esc(s.role)}</td><td>${esc(s.covers)}</td>
        <td>${esc(KIND_KO[s.kind] || s.kind)}</td>
        <td>${s.used_in_quant ? "사용" : "오버레이"}</td>
        <td>${s.link ? `<a class="ticker" href="${esc(s.link)}" target="_blank" rel="noopener">원문</a>` : "미수집"}</td>
      </tr>`).join("")}
    </tbody></table></div>
    <p class="meta">재무는 available_date ≤ run_date 조건을 지킨 로컬 파이프라인 결과입니다. 공개 사이트는 그 결과만 보여 줍니다.</p>
  </section>`;
}

function renderQa() {
  const q = SNAP.quality || {};
  const meta = SNAP.meta || {};
  const excl = q.exclusion_reason_counts || {};
  $("#app").innerHTML = `<section class="stack">
    <div class="grid">
      <div class="card kpi"><h3>실행 상태</h3><b>${esc(q.status || "미수집")}</b></div>
      <div class="card kpi"><h3>재검산 통과</h3><b>${esc(meta.recompute_pass)}/${esc(meta.recompute_total)}</b></div>
      <div class="card kpi"><h3>결과 해시</h3><b style="font-size:14px">${esc((q.result_hash || "미수집").slice(0, 16))}</b></div>
    </div>
    <div class="card"><h2>제외 사유</h2>
      ${Object.keys(excl).length ? Object.entries(excl).map(([k, v]) => `<p><span class="chip">${esc(k)}</span> ${fmt(v, 0)}</p>`).join("") : "<p class='missing'>미수집</p>"}
    </div>
    <div class="card"><h2>누락 지표</h2>
      ${q.missing_metric_counts ? Object.entries(q.missing_metric_counts).map(([k, v]) => `<span class="chip">${esc(k)} ${fmt(v, 0)}</span>`).join("") : "<p class='missing'>미수집</p>"}
    </div>
  </section>`;
}

document.addEventListener("mousemove", setTip);
window.addEventListener("hashchange", () => { if (SNAP) route(); });
loadSnap().then(route).catch((err) => {
  $("#app").innerHTML = `<p class="missing">스냅샷 미수집 — ${esc(err.message)}</p>`;
});
