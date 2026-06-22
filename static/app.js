const gradeClass = (grade) => `grade-${String(grade || "d").toLowerCase()}`;

const fmt = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value).toFixed(digits);
};

const metric = (label, value) => `
  <div class="metric">
    <span>${label}</span>
    <strong>${value ?? ""}</strong>
  </div>
`;

function renderMetrics(payload) {
  const report = payload.report || {};
  const metrics = payload.metrics || {};
  document.querySelector("#metrics").innerHTML = [
    metric("基准日", report.basis_date || "-"),
    metric("顶部主线", report.top_theme || "-"),
    metric("ETF候选", metrics.etf_candidate_count ?? 0),
    metric("A股候选", metrics.stock_candidate_count ?? 0),
    metric("证据确认", metrics.evidence_confirmed_stock_count ?? 0),
  ].join("");
  document.querySelector("#report-meta").textContent = `${report.report_id || ""} · ${report.generated_at || ""}`;
  document.querySelector("#candidate-count").textContent =
    `${metrics.theme_count ?? 0} 条主线 · 缺口 ${report.data_gap_count ?? 0}`;
}

function linkCard(title, subtitle, href, variant = "default") {
  if (!href) {
    return `
      <div class="doc-card doc-card-disabled">
        <strong>${title}</strong>
        <span>${subtitle || "暂无"}</span>
      </div>
    `;
  }
  return `
    <a class="doc-card doc-card-${variant}" href="${href}" target="_blank" rel="noreferrer">
      <strong>${title}</strong>
      <span>${subtitle || href}</span>
    </a>
  `;
}

function renderDocumentLinks(payload) {
  const report = payload.report || {};
  const stockDeep = payload.stock_deep_research || {};
  const stockReport = stockDeep.report || {};
  const leaderId = report.report_id;
  const stockId = stockReport.report_id;
  document.querySelector("#document-meta").textContent = leaderId ? "Markdown / JSON" : "暂无研究文档";
  document.querySelector("#document-links").innerHTML = [
    linkCard("主线龙头研究文档", leaderId || "暂无主线龙头研究", leaderId ? `/api/reports/${leaderId}/markdown` : "", "leader"),
    linkCard("主线龙头研究 JSON", leaderId || "暂无主线龙头研究", leaderId ? "/api/latest" : "", "json"),
    linkCard("龙头股深研文档", stockId || "暂无龙头股深研", stockId ? `/api/stocks/deep/reports/${stockId}/markdown` : "", "stock"),
    linkCard("龙头股深研 JSON", stockId || "暂无龙头股深研", stockId ? "/api/stocks/deep/latest" : "", "json"),
  ].join("");
}

function renderChart(themes) {
  const chart = document.querySelector("#score-chart");
  if (!themes.length) {
    chart.innerHTML = '<div class="empty">暂无研究数据</div>';
    return;
  }
  const width = 860;
  const height = 330;
  const left = 210;
  const right = 36;
  const top = 26;
  const barH = 22;
  const gap = 15;
  const maxScore = Math.max(100, ...themes.map((row) => Number(row.leader_score || 0)));
  const rows = themes.map((row, index) => {
    const y = top + index * (barH + gap);
    const score = Number(row.leader_score || 0);
    const w = ((width - left - right) * score) / maxScore;
    const cls = gradeClass(row.leader_grade).replace("grade-", "");
    const color = { a: "#0f766e", b: "#2563eb", c: "#b7791f", d: "#b42318" }[cls] || "#667085";
    return `
      <text x="12" y="${y + 16}" font-size="13" fill="#172033">${row.rank}. ${row.theme || ""}</text>
      <rect x="${left}" y="${y}" width="${w}" height="${barH}" rx="4" fill="${color}"></rect>
      <text x="${left + w + 8}" y="${y + 16}" font-size="12" fill="#667085">${fmt(score)} · ${row.leader_grade || ""}</text>
    `;
  });
  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="主线龙头分布">${rows.join("")}</svg>`;
}

function candidateList(items) {
  if (!items || !items.length) return '<span class="muted">无</span>';
  return `<div class="compact-list">${items
    .slice(0, 3)
    .map(
      (row) => `
        <div class="candidate">
          <code>${row.code || ""}</code>
          <span>
            ${row.name || ""}
            <br><span class="muted">${row.leader_tier || row.binding_source || ""}</span>
            <br><span class="muted">${row.leader_claim || row.leader_role || ""}</span>
            <br><span class="muted">${fmt(row.leader_score)} 分 · 证据 ${row.evidence_count ?? 0}/${row.hard_evidence_count ?? 0}</span>
          </span>
          <b class="pill ${gradeClass(row.grade)}">${row.grade || ""}</b>
        </div>
      `,
    )
    .join("")}</div>`;
}

function renderThemes(themes) {
  document.querySelector("#theme-rows").innerHTML = themes
    .map(
      (row) => `
        <tr>
          <td class="theme-cell">${row.rank}. ${row.theme || ""}</td>
          <td>${row.stage || ""}<br><span class="muted">${row.lifecycle_state || ""}</span></td>
          <td>${fmt(row.leader_score)}</td>
          <td><span class="pill ${gradeClass(row.leader_grade)}">${row.leader_label || row.leader_grade || ""}</span></td>
          <td>${candidateList(row.etf_leaders)}</td>
          <td>${candidateList(row.stock_leaders)}</td>
          <td>${(row.data_gaps || []).join("<br>") || '<span class="muted">无</span>'}</td>
        </tr>
      `,
    )
    .join("");
}

function renderShadow(payload) {
  const contract = payload.shadow_contract || {};
  const constraints = contract.constraints || {};
  document.querySelector("#shadow-state").textContent = contract.schema_version || "";
  document.querySelector("#shadow-contract").innerHTML = [
    ["模式", contract.mode],
    ["只读", constraints.read_only ? "是" : "否"],
    ["比例化", constraints.ratio_only ? "是" : "否"],
    ["交易指令", constraints.contains_trade_orders ? "有" : "无"],
    ["信号数", (contract.leader_signals || []).length],
    ["接口", "/api/shadow/latest"],
  ]
    .map(([label, value]) => `<div class="contract-row"><span>${label}</span><strong>${value ?? ""}</strong></div>`)
    .join("");
}

function renderGaps(gaps) {
  document.querySelector("#gap-count").textContent = `${gaps.length} 项`;
  document.querySelector("#data-gaps").innerHTML = gaps.length
    ? gaps.map((gap) => `<li>${gap}</li>`).join("")
    : '<li class="empty">无</li>';
}

function ratingClass(rating) {
  const normalized = String(rating || "c").toLowerCase();
  if (normalized === "s") return "grade-a";
  if (normalized === "a") return "grade-b";
  if (normalized === "b") return "grade-c";
  return "grade-d";
}

function scoreParts(scores) {
  if (!scores) return "";
  return [
    ["主题", scores.theme_binding],
    ["证据", scores.evidence_quality],
    ["财务", scores.financial_quality],
    ["估值", scores.valuation_safety],
    ["交易", scores.trading_structure],
    ["数据", scores.data_quality],
  ]
    .map(([label, value]) => `${label} ${fmt(value)}`)
    .join("<br>");
}

function renderStockDeep(stockDeep) {
  const meta = document.querySelector("#stock-deep-meta");
  const rows = document.querySelector("#stock-deep-rows");
  if (!stockDeep || !stockDeep.report) {
    meta.textContent = "暂无深研报告";
    rows.innerHTML = '<tr><td colspan="8" class="empty">请先运行单股深研生成脚本。</td></tr>';
    return;
  }
  const summary = stockDeep.summary || {};
  const stocks = stockDeep.stocks || [];
  meta.textContent = `${stockDeep.report.report_id || ""} · ${summary.stock_count || 0} 只 · 证据确认 ${summary.evidence_confirmed_count || 0} 只 · 影子池入选 ${summary.eligible_count || 0} 只`;
  if (!stocks.length) {
    rows.innerHTML = '<tr><td colspan="8" class="empty">本次深研队列为空：只有 A/B 主线的前排个股会进入深研。</td></tr>';
    return;
  }
  rows.innerHTML = stocks
    .map((row) => {
      const market = row.market || {};
      const risk = [...(row.risk_flags || []), ...(row.data_gaps || [])].join("<br>") || '<span class="muted">无</span>';
      return `
        <tr>
          <td class="theme-cell">${row.code || ""}<br><span class="muted">${row.name || ""}</span></td>
          <td>${row.theme || ""}<br><span class="muted">${row.theme_grade || ""} · ${row.theme_stage || ""}</span></td>
          <td>${row.candidate_leader_tier || ""}<br><span class="muted">${row.candidate_leader_claim || ""}</span><br><span class="muted">证据 ${row.candidate_evidence_count ?? 0}/${row.candidate_hard_evidence_count ?? 0} · ${fmt(row.candidate_evidence_score)}</span></td>
          <td><span class="pill ${ratingClass(row.deep_rating)}">${row.deep_rating || ""} ${row.deep_label || ""}</span><br><span class="muted">${row.shadow_observation_eligible ? "影子池入选" : "未入影子池"}</span></td>
          <td>${fmt(row.deep_score)}</td>
          <td>${scoreParts(row.scores)}</td>
          <td>1日 ${fmt(market.pct_chg)}%<br>5日 ${fmt(market.r5)}%<br>20日 ${fmt(market.r20)}%<br>PE ${fmt(market.pe_ttm)} · PB ${fmt(market.pb)}</td>
          <td>${risk}</td>
        </tr>
      `;
    })
    .join("");
}

async function load() {
  const response = await fetch("/api/index");
  if (!response.ok) {
    document.querySelector("main").innerHTML = `<section class="panel"><h2>暂无研究结果</h2><p class="muted">请先运行生成脚本。</p></section>`;
    return;
  }
  const payload = await response.json();
  const themes = payload.themes || [];
  renderMetrics(payload);
  renderDocumentLinks(payload);
  renderChart(themes);
  renderThemes(themes);
  renderShadow(payload);
  renderGaps(payload.data_gaps || []);
  renderStockDeep(payload.stock_deep_research);
}

load().catch((error) => {
  document.querySelector("main").innerHTML = `<section class="panel"><h2>页面加载失败</h2><p class="muted">${error}</p></section>`;
});
