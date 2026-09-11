---
title: "ADR-0004: 德语背词工作台采用 iframe 嵌入而非代码合并"
created: 2026-08-29
updated: 2026-08-29
type: notes
tags:
  - category/project
  - topic/adr
  - project/demo-project
status: stable
audience: both
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# ADR-0004: 德语背词工作台采用 iframe 嵌入而非代码合并

## 1. 背景与问题陈述

示例项目 v4.6.0 集成了"德语背词工作台"——一个独立开发的单文件 HTML 应用（`workbench.html`，约 3300 行），包含 FSRS-6 卡片复习、自测、介词矩阵、统计、词库导入导出等功能。它原本是独立运行的（直接打开 HTML 文件），现在要嵌入到 示例项目 主应用的"德语"Tab 里。

关键约束：
- 工作台是外部项目（`D:\Ran\German\workbench.html`），有自己的独立迭代节奏
- 工作台内部 JS 大量使用全局变量和 DOM 直接操作，与 示例项目 的模块化 JS（`main.js`、`player.js`、`cards.js`）风格不一致
- 工作台有自己的 TTS 播放链路（服务端 edge-tts → 在线多源 → Web Speech），示例项目 也有 `player.js`
- 移动端底部导航栏 + 伴读宠物的遮挡问题需要处理

## 2. 决策考量因素

- **维护成本**：工作台是独立项目，合并代码意味着每次上游更新都要手动 merge 到 示例项目 的 JS/CSS 结构里
- **样式隔离**：工作台有自己的 CSS 体系，示例项目 也有全局样式，直接合并会互相污染
- **风险控制**：3300 行 JS 一次性合并进主应用，变量冲突、事件绑定冲突、CSS 覆盖等问题难以穷举
- **功能复用**：工作台的 TTS 链路可以复用 示例项目 的 `/api/audio/tts` 服务端点，但 UI 和数据模型完全独立
- **数据互通**：工作台数据存在 `localStorage`，与主应用的 IndexedDB 是两套体系；备份恢复需要单独处理 `wb.*` 键
- **独立运行能力**：工作台需要支持脱离 示例项目 单独使用（file:// 打开），不能强依赖主应用的 JS API

## 3. 决议方案

采用 **iframe 嵌入**方案。`index.html` 的 `#view-german` 容器里放一个 `<iframe src="/german/workbench.html" allow="autoplay">`，由 flex 布局撑满剩余高度。工作台作为独立页面运行，与主应用通过 HTTP API（而非 JS 全局变量）交互。

具体要点：
- **样式隔离**：iframe 天然隔离 CSS，工作台和主应用的样式互不干扰
- **JS 隔离**：两套全局变量互不冲突，工作台的 `_ttsAudio`、`S`、`Deck` 等不污染主应用
- **TTS 复用**：工作台通过 `fetch('/api/audio/tts')` 调服务端 edge-tts，走 HTTP 而非跨 iframe JS 调用；`location.protocol.startsWith('http')` 判断是否在 示例项目 内运行，file:// 下自动跳过走在线源
- **备份集成**：主应用备份/恢复时单独处理 `localStorage` 里的 `wb.*` 键（工作台数据），与 IndexedDB 的主数据分开管理
- **伴读宠物避让**：切到德语 Tab 时给 `#companion` 加 `is-disabled` 类隐藏，防止盖住工作台底部按钮
- **移动端底部栏**：保留显示，iframe 高度由 flex 链计算，自动避开底部 dock

被拒绝的方案：
- **代码合并（把工作台 JS 直接合并进 main.js / cards.js）**：3300 行一次性合并风险高，变量冲突和样式污染难以全面排查；上游更新时 merge 成本极高，失去独立迭代能力
- **Web Component 封装**：需要把工作台重构为 Custom Element，改动量接近重写，成本远高于 iframe；且 shadow DOM 对 TTS 音频播放和 localStorage 的行为需要额外验证
- **完全重写（用 示例项目 既有组件重构工作台）**：工作量最大，等于重写一个 684 词的 FSRS 背词系统；完全失去上游同步能力
- **单文件内联（把 workbench.html 内容直接插进 index.html）**：全局变量和样式冲突问题与代码合并相同，且更难定位故障边界

## 4. 积极后果与消极妥协

- **正面收益**：零样式/JS 冲突风险；上游 `D:\Ran\German` 更新时只需替换 `static/german/workbench.html` 一个文件；工作台保持独立运行能力（file:// 打开也能用，只是少了服务端 TTS）；嵌入与独立运行两条路径代码同一套，不维护分叉
- **妥协风险**：跨 iframe 通信只能走 HTTP API 或 `postMessage`，增加少量复杂度（如 v4.6.3 的导出功能，blob URL 在 Android WebView 的 iframe 里静默失败，需要走服务端下载通道）；伴读宠物在德语 Tab 被隐藏，少了互动感；两套存储体系（IndexedDB + localStorage `wb.*`），备份恢复要两边都覆盖
