---
title: "Coding 知识库总控工作台 (Home MOC & Academic Workbench)"
created: 2026-08-28
updated: 2026-09-09
type: moc
tags:
  - category/moc
  - category/dashboard
cssclasses:
  - vault-workbench
status: stable
audience: both
authority: synthetic
claim_risk: none
review_status: unreviewed
---

<div class="top-ticker">
  <div class="topbar-inner">
    <span><b>CODING VAULT · 2026</b> · Vol. 02 / MOC Nº 01</span>
    <span>Filed under <b class="coral">CS Fundamentals · Systems · Multi-Language (×5) · Projects · Academics</b></span>
    <span><span class="pulse"></span>System · v3.0.0 Online</span>
  </div>
</div>

<div class="home-hero-box">
  <div class="hero-eyebrow">
    <span>● LLM-NATIVE KNOWLEDGE WORKBENCH · CS CORE & ENGINEERING STANDARDS</span>
  </div>
  <h1 class="home-hero-title">
    Coding 知识库<br><span class="accent-word">学术工程工作台</span>
  </h1>
  <p class="home-hero-desc">
    计算机核心基石 · 现代系统架构与中间件 · 多领域规范与课程实验区（待自建） · 自动化运维控制舱。0ms 离线本地检索与全生命周期开发资产。
  </p>
  <div class="cefr-legend">
    <strong>学科矩阵：</strong>
    <span class="hl-pill hl-A1">01 通用准则</span>
    <span class="hl-pill hl-A2">02 CS四大件</span>
    <span class="hl-pill hl-B1">03 语言矩阵</span>
    <span class="hl-pill hl-B2">04 系统架构</span>
    <span class="hl-pill hl-C1">07 顶校实验</span>
    <span class="hl-pill hl-A1">08 落地工程</span>
    <span class="hl-pill hl-B1">09 职业战备</span>
    <span class="hl-pill hl-B2">99 待加工区</span>
  </div>
</div>

```dataviewjs
// ── 1. 工作台自动化运维控制舱 (Tactile Command Console v2) ─────────────────
const vaultPath = app.vault.adapter.basePath || "{{VAULT_ROOT}}";
const container = dv.container;

// 环境探测：Obsidian 未开放 Node 集成时 require 不存在，按钮退化为「复制命令」
const CAN_EXEC = typeof require !== "undefined";

// 只读诊断：点了不会改库（与 nightly 门禁同口径）
const READONLY = [
  { id: "health",  label: "全库健康体检",   cmd: "python scripts/vault-healthcheck.py",                  hint: "Check 1-10 全量巡检" },
  { id: "quality", label: "规范质量门禁",   cmd: "python scripts/vault-quality-check.py --strict",        hint: "--strict，与门禁同口径" },
  { id: "drift",   label: "能力漂移检查",   cmd: "python scripts/capability-check.py --check-drift",      hint: "capabilities.json ↔ 矩阵" },
  { id: "ledger",  label: "可信度账本校验", cmd: "python scripts/vault-claim-ledger.py --check",          hint: "枚举合法性 + 回填收敛" },
  { id: "triage",  label: "Inbox 体检报告", cmd: "python scripts/vault-inbox-triage.py",                  hint: "只出报告，不归档" },
];

// 写盘维护：会修改文件，点击需二次确认
const WRITE = [
  // risk: 影响面说明，写盘按钮的确认框会显式展示（全库扫写类必须写清代价）
  { id: "linker",  label: "拓扑自动链接",   cmd: "python scripts/vault-auto-linker.py --apply",           hint: "全库扫描并写入 wikilink（裸跑=预览）",
    risk: "会对**全库所有笔记**扫描并写入 wikilink，命中即改文件（历史证实：会在已含链接的行上重复插入）。建议先 `git commit` 再执行；只想看影响面请先在终端跑 `python scripts/vault-auto-linker.py`（默认 dry-run 预览）。" },
  { id: "compact", label: "长记忆压缩整理", cmd: "python scripts/vault-memory-compactor.py",              hint: "压缩 99-Inbox 草稿（无 dry-run）" },
  { id: "promote", label: "草稿一键晋级",   cmd: "python scripts/vault-inbox-consolidate.py --apply",     hint: "按路由归档并删除原件" },
  { id: "boards",  label: "仪表盘再生成",   cmd: "python scripts/vault-dashboards.py --apply",            hint: "重写 dashboards/ 六页" },
  { id: "sights",  label: "会话洞察刷新",   cmd: "python scripts/vault-insights.py --apply",              hint: "重写 dashboards/sessions.md" },
];

const deckEl = container.createEl("div");
deckEl.className = "deck-card";

const btnHtml = (o, kind) => `
  <button class="dl-btn" data-act="${o.id}" data-kind="${kind}" data-cmd="${o.cmd}" data-label="${o.label}" data-risk="${o.risk || ""}" title="${o.hint}">
    <div class="dl-btn-top"><span>${kind === "write" ? "⚠️ " : ""}${o.label}</span></div>
    <div class="dl-btn-sub">${o.cmd.replace("python scripts/", "")}</div>
  </button>`;

// 分组标题：栅格容器里 flex-basis 无效，必须用 grid-column 跨整行（见 CSS .dl-group-title）
const groupTitle = t => `<div class="dl-group-title">${t}</div>`;

deckEl.innerHTML = `
  <div class="section-bar" style="margin-top:0;">
    <span class="section-title">⚡ 自动化运维控制舱 · SCHALTTAFEL</span>
    <span class="section-tag">${CAN_EXEC ? "点击即执行 · 写盘项需确认" : "复制模式 · 当前环境无法直接执行"}</span>
  </div>
  <div class="btn-grid-deck">
    <button class="dl-btn" data-act="audit-all" data-kind="read" data-cmd="（串联下列只读命令）" data-label="一键全量只读巡检" title="依次执行 5 个只读诊断命令">
      <div class="dl-btn-top"><span>🛡️ 一键全量只读巡检</span></div>
      <div class="dl-btn-sub">healthcheck → quality --strict → drift → ledger → triage</div>
    </button>
    ${groupTitle("只读诊断（安全）")}
    ${READONLY.map(o => btnHtml(o, "read")).join("")}
    ${groupTitle("写盘维护（需确认 · 建议先 git 提交）")}
    ${WRITE.map(o => btnHtml(o, "write")).join("")}
  </div>

  <div class="letterpress-terminal">
    <div class="terminal-header">
      <span>WERKBANK TERMINAL AUSGABE</span>
      <button class="terminal-clear-btn" id="dl-term-clear">CLEAR</button>
    </div>
    <pre class="terminal-content" id="dl-term-stream">❯ Ready. ${CAN_EXEC ? "点击上方按钮直接触发运维任务…" : "当前环境不支持直接执行，点击按钮将复制命令到剪贴板。"}</pre>
  </div>
`;

const termOut = deckEl.querySelector("#dl-term-stream");
const clearBtn = deckEl.querySelector("#dl-term-clear");
const stamp = () => new Date().toLocaleTimeString();

function out(text) {
  if (termOut.textContent === "" || termOut.textContent.startsWith("❯ Ready")) {
    termOut.textContent = "";
  }
  termOut.textContent += (termOut.textContent ? "\n" : "") + text;
  termOut.scrollTop = termOut.scrollHeight;
}

if (clearBtn) {
  clearBtn.onclick = () => { termOut.textContent = "❯ Ready."; };
}

// exec 显式 encoding: 'utf8' —— Windows 默认 GBK 会把中文输出解码成乱码
function execOne(cmd) {
  return new Promise(resolve => {
    const { exec } = require("child_process");
    exec(cmd, { cwd: vaultPath, maxBuffer: 1024 * 1024 * 8, encoding: "utf8" }, (error, stdout, stderr) => {
      if (error) {
        out((stdout || "") + `❌ 退出码 ${error.code}` + (stderr ? "\n" + stderr : ""));
      } else {
        out((stdout || "✅ 完成（无标准输出）") + (stderr ? "\n[stderr]\n" + stderr : ""));
      }
      resolve();
    });
  });
}

deckEl.querySelectorAll(".dl-btn").forEach(btn => {
  btn.addEventListener("click", async () => {
    const { act, kind, cmd, label, risk } = btn.dataset;

    if (!CAN_EXEC) {
      try { navigator.clipboard.writeText(cmd); } catch (e) { /* 忽略剪贴板失败 */ }
      out(`[${stamp()}] 📋 ${label}：环境不支持直接执行，命令已复制\n$ ${cmd}`);
      return;
    }

    if (kind === "write") {
      // 影响面显式告知：全库扫写类按钮必须让用户在点之前看清代价
      const detail = risk ? `\n\n⚠️ 影响面：${String(risk).replace(/\*\*/g, "")}` : "";
      const ok = window.confirm(
        `⚠️「${label}」会写入/修改文件。\n\n$ ${cmd}${detail}\n\n确认执行？（建议先 git 提交当前改动）`
      );
      if (!ok) { out(`[${stamp()}] 已取消：${label}`); return; }
    }

    btn.classList.add("is-running");
    out(`[${stamp()}] ❯ ${label}\n$ ${cmd}\n────────────────────────────────────────────`);
    try {
      if (act === "audit-all") {
        for (const o of READONLY) {
          out(`\n▶ ${o.label}`);
          await execOne(o.cmd);
        }
        out("\n✅ 全量只读巡检结束");
      } else {
        await execOne(cmd);
      }
    } catch (e) {
      out(`❌ 执行异常：${e && e.message ? e.message : e}`);
    }
    btn.classList.remove("is-running");
  });
});
```

```dataviewjs
// ── 2. 知识沉淀矩阵 (Activity Heatmap · 52 周 · GitHub 风格) ───────────────
const container = dv.container;
const allPages = dv.pages();

// 1) 采集：以 file.mtime 为「沉淀」信号，按日聚合（保留清单以便点击下钻）
// 注意：p.file.name 在部分 Dataview 版本取不到（渲染成 undefined），
// 显示名一律由 path 推导，绝不直接信任 file.name。
const titleOf = path => String(path).split("/").pop().replace(/\.md$/i, "");
const byDate = {};
allPages.forEach(p => {
  if (!p || !p.file || !p.file.mtime) return;
  const path = p.file.path || "";
  if (path.startsWith(".obsidian") || path.startsWith("copilot") || path === "00-MOC/Home.md") return;
  const key = p.file.mtime.toISODate
    ? p.file.mtime.toISODate()
    : moment(p.file.mtime.ts || p.file.mtime).format("YYYY-MM-DD");
  (byDate[key] = byDate[key] || []).push({ path, name: titleOf(path) });
});
const countOf = k => (byDate[k] ? byDate[k].length : 0);

// 2) 窗口：日历年（1 月 → 12 月，GitHub 视角）；当年只画到今天
const TODAY = moment();
let curYear = TODAY.year();
let selected = TODAY.format("YYYY-MM-DD");

function buildDays(y) {
  const start = moment([y, 0, 1]);
  const last = moment.min(moment([y, 11, 31]).endOf("day"), TODAY.clone());
  const out = [];
  const d = start.clone();
  while (d.isSameOrBefore(last, "day")) {
    const key = d.format("YYYY-MM-DD");
    out.push({ date: key, count: countOf(key), moment: d.clone(), monthIdx: d.month(), dow: d.day() });
    d.add(1, "day");
  }
  return out;
}

// 3) 统计（成就感三件套：连续 / 峰值 / 覆盖率）
const levelOf = c => (c === 0 ? 0 : c <= 1 ? 1 : c <= 3 ? 2 : c <= 6 ? 3 : 4);

function statsOf(days) {
  const total = days.reduce((s, d) => s + d.count, 0);
  let current = 0;
  for (let i = days.length - 1; i >= 0; i--) {
    if (days[i].count > 0) current++; else break;
  }
  let longest = 0, run = 0;
  days.forEach(d => { if (d.count > 0) { run++; longest = Math.max(longest, run); } else run = 0; });
  const best = days.reduce((a, b) => (b.count > a.count ? b : a), days[0] || { count: 0, date: "-" });
  return {
    total, current, longest, best,
    active: days.filter(d => d.count > 0).length,
    span: days.length,
    week7: days.slice(-7).reduce((s, d) => s + d.count, 0),
  };
}

// 4) 绘制参数（GitHub 规格：10px 方块 / 3px 间距 / 圆角 2）
const CELL = 10, GAP = 3, LEFT = 30, TOP = 20;
const EMPTY = "var(--background-modifier-border, rgba(128,128,128,0.22))";
const PALETTE = [EMPTY, "#9be9a8", "#40c463", "#30a14e", "#216e39"];
const MONTHS = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];

const chip = (icon, label, value) =>
  `<span class="hm-stat" style="display:inline-flex;align-items:center;gap:.25rem;padding:.18rem .55rem;border:1px solid var(--background-modifier-border,rgba(128,128,128,.3));border-radius:999px;font-size:.72rem;color:var(--text-muted,#5C554B);white-space:nowrap;">${icon} ${label} <b style="color:var(--text-normal);">${value}</b></span>`;

const legend = `<span style="display:inline-flex;align-items:center;gap:.3rem;font-size:.68rem;color:var(--text-faint,#8C8477);margin-left:auto;">少 ${PALETTE.map(c => `<i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${c};"></i>`).join("")} 多</span>`;

const itemLink = it => {
  const name = it.name || titleOf(it.path);
  try {
    const el = dv.fileLink(it.path);
    const html = el && el.outerHTML;
    if (html) return html;
  } catch (e) { /* fall through to manual anchor */ }
  // 兜底：Obsidian 靠 .internal-link + data-href 识别站内跳转
  return `<a class="internal-link" data-href="${it.path}" href="${it.path}" target="_blank" rel="noopener">${name}</a>`;
};

const heatCard = container.createEl("div");
heatCard.className = "heatmap-dossier";

function badgeOf(cur) {
  if (cur >= 100) return "🏆 百日不断更";
  if (cur >= 30) return "🥇 满月连续";
  if (cur >= 7) return "🔥 周更达成";
  if (cur > 0) return "🌱 连续进行中";
  return "💤 今日尚未开张";
}

function renderYear(y) {
  const days = buildDays(y);
  const st = statsOf(days);
  const firstDow = days.length ? days[0].dow : 0;

  let rectsSvg = "", monthsSvg = "", lastMonthIdx = -1, curMonthX = null;
  days.forEach((d, idx) => {
    const weekIdx = Math.floor((idx + firstDow) / 7);
    const x = LEFT + weekIdx * (CELL + GAP);
    const yRow = TOP + d.dow * (CELL + GAP);
    const lv = levelOf(d.count);
    const isToday = d.date === TODAY.format("YYYY-MM-DD");
    const isSel = d.date === selected;
    const stroke = (isToday || isSel)
      ? ` stroke="${isSel ? "var(--text-normal,#15140F)" : "var(--text-faint,#8C8477)"}" stroke-width="${isSel ? 1.8 : 1.3}"`
      : "";
    const tip = d.count === 0 ? `${d.date} · 无沉淀` : `${d.date} · ${d.count} 项沉淀（点击查看）`;
    rectsSvg += `<rect class="hm-cell${isSel ? " is-active" : ""}" data-date="${d.date}" data-level="${lv}" x="${x}" y="${yRow}" width="${CELL}" height="${CELL}" rx="2" fill="${PALETTE[lv]}"${stroke} style="animation-delay:${(idx * 1.1).toFixed(0)}ms"><title>${tip}</title></rect>`;

    if (d.monthIdx !== lastMonthIdx && d.moment.date() <= 7) {
      monthsSvg += `<text x="${x}" y="12" font-size="9" fill="var(--pencil,#5C554B)" font-family="var(--mono,monospace)">${MONTHS[d.monthIdx]}</text>`;
      lastMonthIdx = d.monthIdx;
    }
    // 当年：记录当前月首列 x，用于把「当前月」滚到视野中央
    if (y === TODAY.year() && d.monthIdx === TODAY.month() && curMonthX === null) curMonthX = x;
  });

  const dayLabels = [["一", 1], ["三", 3], ["五", 5]].map(([label, row]) =>
    `<text x="2" y="${TOP + row * (CELL + GAP) + 8}" font-size="8" fill="var(--muted,#8C8477)" font-family="var(--mono,monospace)">${label}</text>`
  ).join("");

  const weeks = Math.ceil((days.length + firstDow) / 7);
  const svgW = LEFT + weeks * (CELL + GAP) + 8;
  const svgH = TOP + 7 * (CELL + GAP) + 4;

  heatCard.innerHTML = `
    <div class="section-bar" style="margin-top:0;">
      <span class="section-title">🟩 知识沉淀矩阵 · AKTIVITÄTSMATRIX</span>
      <span class="section-tag">${badgeOf(st.current)}</span>
    </div>
    <div class="hm-stats" style="display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin:.5rem 0 .55rem;">
      <span class="hm-nav" style="display:inline-flex;align-items:center;gap:.2rem;">
        <button class="hm-nav-btn" data-nav="-1" title="上一年">‹</button>
        <b style="font-size:.78rem;min-width:2.6rem;text-align:center;">${y}</b>
        <button class="hm-nav-btn" data-nav="1" title="下一年" ${y >= TODAY.year() ? "disabled" : ""}>›</button>
      </span>
      ${chip("📚", "年度", st.total + " 项")}
      ${chip("🔥", "当前连续", st.current + " 天")}
      ${chip("🏅", "最长连续", st.longest + " 天")}
      ${chip("⚡", "最佳单日", st.best.count + " 项")}
      ${chip("📅", "活跃", st.active + "/" + st.span + " 天")}
      ${chip("🗓️", "近 7 天", st.week7 + " 项")}
      ${legend}
    </div>
    <div class="heatmap-svg-scroll" id="hm-scroll">
      <svg width="${svgW}" height="${svgH}" style="display:block;margin:0 auto;overflow:visible;">
        ${monthsSvg}
        ${dayLabels}
        ${rectsSvg}
      </svg>
    </div>
    <div class="hm-detail" id="hm-detail"></div>
  `;

  // 点击格子 → 当日清单（GitHub「N contributions on <date>」的下钻版）
  // 注意：SVG <rect> 是 SVGElement，没有 HTMLElement.click()，
  // 因此选中逻辑抽成函数复用，绝不调用 .click()。
  function showDay(dateKey, rect) {
    selected = dateKey;
    const box = heatCard.querySelector("#hm-detail");
    if (!box) return;
    heatCard.querySelectorAll(".hm-cell.is-active").forEach(n => n.classList.remove("is-active"));
    if (rect) rect.classList.add("is-active");
    const items = byDate[dateKey] || [];
    if (!items.length) {
      box.innerHTML = `<div style="font-size:.75rem;color:var(--text-faint,#8C8477);">${dateKey} · 当日无沉淀记录</div>`;
      return;
    }
    box.innerHTML = `<div style="font-size:.76rem;margin-bottom:.25rem;color:var(--text-muted,#5C554B);"><b>${dateKey}</b> · ${items.length} 项沉淀</div>`
      + `<ul style="margin:0;padding-left:1.1rem;font-size:.74rem;line-height:1.65;">`
      + items.map(it => `<li>${itemLink(it)}</li>`).join("")
      + `</ul>`;
  }

  heatCard.querySelectorAll(".hm-cell").forEach(rect => {
    rect.addEventListener("click", () => showDay(rect.getAttribute("data-date"), rect));
  });

  // 年份切换
  heatCard.querySelectorAll(".hm-nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const next = y + parseInt(btn.getAttribute("data-nav"), 10);
      if (next > TODAY.year()) return;
      renderYear(next);
    });
  });

  // 当年：把「当前月」滚到可视区中央
  const sc = heatCard.querySelector("#hm-scroll");
  if (sc && curMonthX !== null) {
    const target = curMonthX - sc.clientWidth / 2 + 40;
    sc.scrollLeft = Math.max(0, target);
  }

  // 默认收起：仅高亮今天所在的格子，不展开清单（点击才展开）
  const todayCell = heatCard.querySelector(`.hm-cell[data-date="${TODAY.format("YYYY-MM-DD")}"]`);
  if (todayCell) todayCell.classList.add("is-active");
}

renderYear(curYear);
```

<div class="two-column-dossier">

<div class="dossier-card">
  <div class="section-bar" style="margin-top:0;">
    <span class="section-title">📁 工程项目与实验档案 · PROJEKTE & LABS</span>
  </div>

  <!-- ↓ 两张示例占位卡（原为作者个人项目卡，已去个人化）：复制任一卡片，替换标题 / 标签 / 描述即可改成你的项目 -->
  <div class="article-row-dossier">
    <div class="dossier-header-line">
      <span class="dossier-title">示例：项目档案卡</span>
      <span class="dossier-tag" style="background:#F0F1F3;color:#5A6472;">占位 · 项目</span>
    </div>
    <div class="dossier-desc">示例：真实项目的名称、一句话定位与技术栈（Web / Desktop / Mobile 均可）。复制此卡改成你的项目。</div>
  </div>

  <div class="article-row-dossier">
    <div class="dossier-header-line">
      <span class="dossier-title">分布式课程实验 分布式实验</span>
      <span class="dossier-tag" style="background:#FFFBE6;color:#825C00;">RAFT 共识</span>
    </div>
    <div class="dossier-desc">MapReduce 调度、Raft 领导选举、日志复制、KV 容错状态机与分片集群</div>
  </div>

  <div class="article-row-dossier">
    <div class="dossier-header-line">
      <span class="dossier-title">示例：项目档案卡</span>
      <span class="dossier-tag" style="background:#F0F1F3;color:#5A6472;">占位 · 实验</span>
    </div>
    <div class="dossier-desc">示例：课程或实验系列的名称、进度要点与产出（如分布式 / 数据库 / 网络实验）。</div>
  </div>
</div>

<div class="dossier-card">
  <div class="section-bar" style="margin-top:0;">
    <span class="section-title">🤖 特战专家名册 · SPEZIALISTEN</span>
  </div>

  <div class="starfleet-grid">
    <div class="starfleet-cell">
      <div class="starfleet-name">DBA 调优师</div>
      <div class="starfleet-spec">MySQL/Redis 索引并发</div>
      <div class="starfleet-cmd">/vault-review --dba</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">代码审查官</div>
      <div class="starfleet-spec">RFC 2119 7语言规则反谄媚</div>
      <div class="starfleet-cmd">/vault-review</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">压测剖析官</div>
      <div class="starfleet-spec">Go Benchmark 内存排查</div>
      <div class="starfleet-cmd">/vault-perf</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">根因排障官</div>
      <div class="starfleet-spec">4步根因铁律与最小复现</div>
      <div class="starfleet-cmd">/vault-debug</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">求职面试官</div>
      <div class="starfleet-spec">高频考点深度口试与系统答辩</div>
      <div class="starfleet-cmd">/vault-interview</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">重构架构师</div>
      <div class="starfleet-spec">复用阶梯与卫语句重构</div>
      <div class="starfleet-cmd">/vault-refactor</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">代码调研官</div>
      <div class="starfleet-spec">符号图谱与陌生代码接手</div>
      <div class="starfleet-cmd">/vault-onboard</div>
    </div>
    <div class="starfleet-cell">
      <div class="starfleet-name">SRE 记录官</div>
      <div class="starfleet-spec">踩坑沉淀与跨会话交接</div>
      <div class="starfleet-cmd">/vault-save</div>
    </div>
  </div>
</div>

</div>

<div class="section-bar">
  <span class="section-title">🗺️ 十大核心知识星系导航 · WISSENS-SPHÄREN (CS DOMAINS)</span>
</div>

| 模块目录                   | 模块名称与定位                       | 核心资产代表                                                                                                                                                                                              | 导航入口                                                         |
| ---------------------- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **`01-Rules/`**        | 跨语言通用工程规范与 Agent 行为准则         | 开发者画像, 通用准则, Agent行为准则         | 规范中枢                           |
| **`02-Fundamentals/`** | 计算机核心底层基石 (OS / 网络 / 体系 / 编译) | 操作系统, 计算机网络, 体系结构              | 基石中枢                           |
| **`03-Languages/`**    | 多语言（当前 5）双版本工程规范与代码模板矩阵    | Go规范, Python规范, Rust规范       | 语言中枢                           |
| **`04-Systems/`**      | 架构设计、数据库、分布式与中间件              | 数据库原理, Redis/Kafka, 分布式共识         | 系统中枢                           |
| **`05-Tools/`**        | 智能体工作流、子 Agent 与工具指南          | 全生命周期SOP, DBA调优师                                                                        | 工具中枢 |
| **`06-Sources/`**      | 经典书籍、顶会论文与架构博客研读              | 《DDIA》研读, Raft论文                                                                       | 研读中枢 |
| **`07-Academics/`**    | 硬核课程实验（待自建）、课程大作业与毕业设计             | 课程实验组合（待自建） | 学术中枢                           |
| **`08-Projects/`**     | 真实项目架构设计、ADR 与故障复盘            | 项目总览, 项目模板, 技术债看板     | 项目中心                           |
| **`09-Career/`**       | 技术求职高频考点、系统设计与真实答辩              | 秒杀高并发设计, MySQL锁高频考点                                                                        | 求职中枢 |
| **`10-Daily/`**        | 每日流水台账与学习进度打卡                 | 每日学习日志、开发工作流水                                                                                                                                                                                       | 10-Daily/                                                    |
| **`99-Inbox/`**        | 对话即沉淀的 A-MAC 准入待加工区           | 零碎排障复盘、灵感记录、Workaround 沉淀                                                                                                                                                                           | 99-Inbox/                                                    |

<div class="section-bar">
  <span class="section-title">📊 实时动态监控列表 · ECHTZEIT-MONITORING</span>
</div>

### 📥 待加工 Landing Zone (`99-Inbox`)

```dataview
TABLE created AS "创建日期", tags AS "标签", source AS "知识来源"
FROM "99-Inbox"
WHERE status = "draft"
SORT file.mtime DESC
LIMIT 5
```

### 🌟 最近 7 天精进资产 (Recent Updates)

<!-- ⚠️ clone 首日须知：git 检出会把所有文件 mtime 重置为检出时刻，下方"最近 7 天"列表在 clone 后第一天会虚高（几乎所有笔记都入选），属正常现象并非数据损坏，运行几天后自然回落。 -->

```dataview
TABLE type AS "类型", tags AS "标签", file.mtime AS "最近更新"
FROM ""
WHERE file.mtime >= date(today) - dur(7 days) AND !contains(file.path, ".obsidian") AND !contains(file.path, "copilot")
SORT file.mtime DESC
LIMIT 8
```

<div class="section-bar">
  <span class="section-title">🎨 可视化白板与拓扑图谱 · CANVAS & GRAPH</span>
</div>

- 📐 **全库架构 JSON Canvas**：知识架构白板（自建）
- 🌌 **算法聚类关系图谱**：知识图谱白板（自动生成）

<div class="section-bar">
  <span class="section-title">📈 知识仪表盘 · DASHBOARDS</span>
</div>

- 📈 **自动化知识仪表盘索引**：仪表盘索引（最近来源 / 时间线 / 矛盾候选 / 开放问题 / 会话洞察 · nightly 自动再生成，勿手动编辑页面）
