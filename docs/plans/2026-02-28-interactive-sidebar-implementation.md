# Interactive Sidebar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a slide-over detail sidebar to `dashboard.html` triggered by clicking section headings, rendering expanded sub-metric charts per section.

**Architecture:** A fixed-position `<aside>` panel slides in from the right via CSS transform. A single delegated click handler on `<article>` dispatches to six `buildSidebar*()` functions. All data comes from the existing `rawData` global. No new dependencies, backend changes, or files.

**Tech Stack:** D3.js v7, DuckDB-WASM (existing), vanilla CSS transitions, single HTML file

**Design doc:** `docs/plans/2026-02-28-interactive-sidebar-design.md`

**Note:** This dashboard is a local-only single-file app rendering its own health data. It uses `innerHTML` and `d3.select().append()` for DOM construction, matching existing codebase patterns. No untrusted user input is rendered.

---

### Task 1: Add sidebar DOM and CSS

**Files:**
- Modify: `dashboard.html:9-355` (CSS section)
- Modify: `dashboard.html:393-394` (after `</article>`, before `<script>`)
- Modify: `dashboard.html:369-392` (add `data-section` attrs to `<h2>` elements)

**Step 1: Add `data-section` attributes to all `<h2>` headings**

Replace the section headings (lines 369-392). Each `<h2>` gets a `data-section` attribute mapping to a sidebar builder:

```html
<!-- ═══════════ SECTION 1: System Status ═══════════ -->
<h2 data-section="scorecard">Protocol Scorecard</h2>
<div id="system-status"></div>

<!-- ═══════════ SECTION 2: Bloodwork ═══════════ -->
<h2 data-section="biomarkers" id="biomarkers-heading">Clinical Biomarkers</h2>
<div class="content-with-sidenotes" id="bloodwork-section"></div>

<!-- ═══════════ SECTION 3: Small Multiples ═══════════ -->
<h2 data-section="trends">Trends</h2>
<p class="wide" id="data-span">Key biomarkers over time. Dotted lines mark longevity targets. Red dashes indicate danger thresholds.</p>
<div class="small-multiples" id="small-multiples"></div>

<!-- ═══════════ SECTION 3b: Gait & Mobility ═══════════ -->
<h2 data-section="gait">Gait &amp; Mobility</h2>
<div class="small-multiples" id="gait-section"></div>

<!-- ═══════════ SECTION 4: Cardiovascular Detail ═══════════ -->
<h2 data-section="cardio">Cardiovascular Detail</h2>
<div class="cardio-grid" id="cardio-detail"></div>

<!-- ═══════════ SECTION 5: Sleep Architecture ═══════════ -->
<h2 data-section="sleep">Sleep Architecture</h2>
<div class="sleep-chart" id="sleep-architecture"></div>
```

**Step 2: Add sidebar `<aside>` element after `</article>`**

Insert between the closing `</article>` (line 394) and `<script type="module">` (line 396):

```html
<!-- ═══════════ SIDEBAR ═══════════ -->
<aside id="sidebar" class="sidebar">
  <div class="sidebar-header">
    <h2 id="sidebar-title"></h2>
    <button id="sidebar-close" aria-label="Close">&times;</button>
  </div>
  <div id="sidebar-content"></div>
</aside>
```

**Step 3: Add sidebar CSS**

Insert the following CSS block before the closing `</style>` tag (line 355), after the responsive media queries:

```css
/* ── Sidebar ── */
.sidebar {
  position: fixed;
  top: 0;
  right: 0;
  width: 380px;
  height: 100vh;
  background: #fffff8;
  border-left: 1px solid #ddd;
  transform: translateX(100%);
  transition: transform 0.3s ease;
  z-index: 200;
  overflow-y: auto;
  padding: 1.5rem;
}

.sidebar.open {
  transform: translateX(0);
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1.2rem;
  padding-bottom: 0.6rem;
  border-bottom: 1px solid #ddd;
}

.sidebar-header h2 {
  font-variant: small-caps;
  font-weight: 400;
  font-size: 1.1rem;
  letter-spacing: 0.05em;
  margin: 0;
}

.sidebar-header button {
  background: none;
  border: none;
  font-size: 1.4rem;
  color: #888;
  cursor: pointer;
  padding: 0 0.3rem;
  line-height: 1;
  font-family: inherit;
}

.sidebar-header button:hover {
  color: #333;
}

/* Section heading click affordance */
h2[data-section] {
  cursor: pointer;
  transition: color 0.15s;
}

h2[data-section]::after {
  content: " \203A";
  opacity: 0;
  transition: opacity 0.15s;
  color: #999;
}

h2[data-section]:hover::after {
  opacity: 1;
}

h2[data-section].sidebar-active {
  color: #333;
}

h2[data-section].sidebar-active::after {
  opacity: 1;
  color: #333;
}

/* Sidebar detail row (used by scorecard sidebar) */
.sidebar-metric {
  margin-bottom: 1rem;
  padding-bottom: 0.8rem;
  border-bottom: 1px solid #f0f0eb;
}

.sidebar-metric:last-child {
  border-bottom: none;
}

.sidebar-metric .metric-label {
  font-variant: small-caps;
  font-size: 0.85rem;
  letter-spacing: 0.03em;
  color: #555;
  margin-bottom: 0.2rem;
}

.sidebar-metric .metric-stats {
  display: flex;
  gap: 1rem;
  font-size: 0.82rem;
  font-variant-numeric: tabular-nums;
  margin-top: 0.3rem;
  color: #666;
}

.sidebar-metric .metric-stats .current {
  font-weight: 600;
  color: #333;
}

.sidebar-section-title {
  font-variant: small-caps;
  font-size: 0.9rem;
  letter-spacing: 0.04em;
  color: #555;
  margin-top: 1.2rem;
  margin-bottom: 0.5rem;
}

.sidebar-chart {
  margin-bottom: 1.2rem;
}

.sidebar-chart .chart-title {
  font-size: 0.78rem;
  font-variant: small-caps;
  letter-spacing: 0.03em;
  color: #555;
  margin-bottom: 0.15rem;
}

.sidebar-chart svg {
  display: block;
}

@media (max-width: 720px) {
  .sidebar {
    width: 100%;
    height: 60vh;
    top: auto;
    bottom: 0;
    transform: translateY(100%);
    border-left: none;
    border-top: 1px solid #ddd;
    border-radius: 12px 12px 0 0;
  }
  .sidebar.open {
    transform: translateY(0);
  }
}

@media print {
  .sidebar { display: none; }
  h2[data-section]::after { display: none; }
  h2[data-section] { cursor: default; }
}
```

**Step 4: Verify in browser**

Open `dashboard.html` in a browser. Verify:
- All existing sections render correctly (no regressions)
- Section headings show a `>` on hover
- The sidebar `<aside>` exists in DOM but is not visible

**Step 5: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): add sidebar DOM, CSS, and heading affordances"
```

---

### Task 2: Add sidebar open/close logic and event delegation

**Files:**
- Modify: `dashboard.html` (inside `<script type="module">`, after the IIFE, before section builders)

**Step 1: Add sidebar state management**

Insert the following code immediately after the `let currentRange = 365;` line (line 670):

```javascript
// ── Sidebar state ──
let sidebarSection = null;  // currently open section id, or null

function openSidebar(section) {
  const sidebar = document.getElementById("sidebar");
  const titleEl = document.getElementById("sidebar-title");
  const contentEl = document.getElementById("sidebar-content");

  // Clear previous active heading
  document.querySelectorAll("h2.sidebar-active").forEach(el => el.classList.remove("sidebar-active"));

  // Set active heading
  const heading = document.querySelector(`h2[data-section="${section}"]`);
  if (heading) heading.classList.add("sidebar-active");

  // Get current filtered data
  const { filtered } = filterByRange(rawData, currentRange);

  // Build sidebar title
  const titles = {
    scorecard: "Protocol Scorecard",
    biomarkers: "Clinical Biomarkers",
    trends: "Trends",
    gait: "Gait & Mobility",
    cardio: "Cardiovascular",
    sleep: "Sleep",
  };
  titleEl.textContent = titles[section] || section;
  contentEl.textContent = "";

  // Dispatch to builder
  const builders = {
    scorecard: () => buildSidebarScorecard(contentEl, filtered),
    biomarkers: () => buildSidebarBiomarkers(contentEl, filtered),
    trends: () => buildSidebarTrends(contentEl, filtered),
    gait: () => buildSidebarGait(contentEl, filtered),
    cardio: () => buildSidebarCardio(contentEl, filtered),
    sleep: () => buildSidebarSleep(contentEl, filtered),
  };

  if (builders[section]) builders[section]();

  sidebar.classList.add("open");
  sidebarSection = section;
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("open");
  document.querySelectorAll("h2.sidebar-active").forEach(el => el.classList.remove("sidebar-active"));
  sidebarSection = null;
}

function refreshSidebar() {
  if (sidebarSection) openSidebar(sidebarSection);
}
```

**Step 2: Add event listeners**

Insert the following code immediately after the `refreshSidebar` function:

```javascript
// ── Sidebar event listeners ──
document.querySelector("article").addEventListener("click", e => {
  const heading = e.target.closest("h2[data-section]");
  if (!heading) return;
  const section = heading.dataset.section;
  if (sidebarSection === section) {
    closeSidebar();
  } else {
    openSidebar(section);
  }
});

document.getElementById("sidebar-close").addEventListener("click", closeSidebar);

document.addEventListener("keydown", e => {
  if (e.key === "Escape" && sidebarSection) closeSidebar();
});
```

**Step 3: Hook sidebar refresh into `renderAll`**

In the `renderAll` function (around line 672), add this line at the very end, after `buildSleepArchitecture(filtered);`:

```javascript
  refreshSidebar();
```

**Step 4: Add stub builder functions**

Add these stub functions that will be filled in by later tasks. Place them after the event listener code. Each stub creates a paragraph using DOM methods:

```javascript
// ── Sidebar builders (stubs, implemented in later tasks) ──
function buildSidebarScorecard(el, data) {
  const p = document.createElement("p");
  p.style.cssText = "color:#888;font-style:italic";
  p.textContent = "Scorecard detail coming soon.";
  el.appendChild(p);
}
function buildSidebarBiomarkers(el, data) {
  const p = document.createElement("p");
  p.style.cssText = "color:#888;font-style:italic";
  p.textContent = "Biomarker detail coming soon.";
  el.appendChild(p);
}
function buildSidebarTrends(el, data) {
  const p = document.createElement("p");
  p.style.cssText = "color:#888;font-style:italic";
  p.textContent = "Trend detail coming soon.";
  el.appendChild(p);
}
function buildSidebarGait(el, data) {
  const p = document.createElement("p");
  p.style.cssText = "color:#888;font-style:italic";
  p.textContent = "Gait detail coming soon.";
  el.appendChild(p);
}
function buildSidebarCardio(el, data) {
  const p = document.createElement("p");
  p.style.cssText = "color:#888;font-style:italic";
  p.textContent = "Cardiovascular detail coming soon.";
  el.appendChild(p);
}
function buildSidebarSleep(el, data) {
  const p = document.createElement("p");
  p.style.cssText = "color:#888;font-style:italic";
  p.textContent = "Sleep detail coming soon.";
  el.appendChild(p);
}
```

**Step 5: Verify in browser**

- Click each section heading: sidebar should slide in with stub text
- Click same heading again: sidebar should close
- Click a different heading: sidebar content swaps
- Press Escape: sidebar closes
- Change date range: sidebar refreshes if open

**Step 6: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): add sidebar open/close logic with event delegation"
```

---

### Task 3: Implement scorecard sidebar builder

**Files:**
- Modify: `dashboard.html` (replace `buildSidebarScorecard` stub)

**Step 1: Replace the `buildSidebarScorecard` stub**

This renders an expanded sparkline (200x40) per metric plus current, 7d avg, and 30d avg values. Uses DOM methods (createElement/textContent) for text and the existing `sparklineSVG()` function for charts:

```javascript
function buildSidebarScorecard(el, data) {
  const sc = data.scorecard;

  const metrics = [
    { name: "Daily Steps", unit: "", fmt: d3.format(","),
      arr: sc, arrKey: "steps", target: "10,000" },
    { name: "Total Sleep", unit: " hrs", fmt: d3.format(".1f"),
      arr: data.sleep.filter(d => d.total > 0.5), arrKey: "total", target: "7.5 hrs" },
    { name: "Deep Sleep", unit: " hrs", fmt: d3.format(".1f"),
      arr: data.sleep.filter(d => d.total > 0.5), arrKey: "deep", target: "1.5 hrs" },
    { name: "REM Sleep", unit: " hrs", fmt: d3.format(".1f"),
      arr: data.sleep.filter(d => d.total > 0.5), arrKey: "rem", target: "1.5 hrs" },
    { name: "Resting HR", unit: " bpm", fmt: d3.format(".0f"),
      arr: data.rhr, arrKey: "v", target: "65 bpm" },
    { name: "HRV", unit: " ms", fmt: d3.format(".0f"),
      arr: data.hrv, arrKey: "v", target: "50 ms" },
    { name: "SpO2 Min", unit: "%", fmt: d3.format(".0f"),
      arr: data.spo2, arrKey: "min", target: "90%" },
    { name: "VO2 Max", unit: "", fmt: d3.format(".1f"),
      arr: data.vo2, arrKey: "v", target: "40" },
    { name: "Body Fat", unit: "%", fmt: d3.format(".1f"),
      arr: data.bodyfat, arrKey: "v", target: "25%" },
    { name: "Exercise", unit: " min/wk", fmt: d3.format(".0f"),
      arr: data.exercise, arrKey: "v", target: "150 min" },
  ];

  for (const m of metrics) {
    const values = m.arr.map(d => d[m.arrKey]).filter(v => v != null && v > 0);
    if (values.length === 0) continue;

    const current = values[values.length - 1];
    const avg7 = d3.mean(values.slice(-7)) ?? current;
    const avg30 = d3.mean(values.slice(-30)) ?? current;

    const div = document.createElement("div");
    div.className = "sidebar-metric";

    const label = document.createElement("div");
    label.className = "metric-label";
    label.textContent = m.name;
    div.appendChild(label);

    // Sparkline (uses existing sparklineSVG which returns safe SVG markup)
    const sparkContainer = document.createElement("div");
    sparkContainer.innerHTML = sparklineSVG(values.slice(-90), 200, 40);
    div.appendChild(sparkContainer);

    const stats = document.createElement("div");
    stats.className = "metric-stats";

    const curSpan = document.createElement("span");
    curSpan.className = "current";
    curSpan.textContent = m.fmt(current) + m.unit;
    stats.appendChild(curSpan);

    const avg7Span = document.createElement("span");
    avg7Span.textContent = "7d: " + m.fmt(avg7);
    stats.appendChild(avg7Span);

    const avg30Span = document.createElement("span");
    avg30Span.textContent = "30d: " + m.fmt(avg30);
    stats.appendChild(avg30Span);

    const targetSpan = document.createElement("span");
    targetSpan.style.color = "#999";
    targetSpan.textContent = "target: " + m.target;
    stats.appendChild(targetSpan);

    div.appendChild(stats);
    el.appendChild(div);
  }
}
```

**Step 2: Verify in browser**

Click "Protocol Scorecard" heading. Sidebar should show:
- Each metric with a 200x40 sparkline (last 90 days)
- Current value (bold), 7d avg, 30d avg, target
- Metrics without data are skipped

**Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): implement scorecard sidebar with expanded sparklines"
```

---

### Task 4: Implement biomarkers sidebar builder

**Files:**
- Modify: `dashboard.html` (replace `buildSidebarBiomarkers` stub)

**Step 1: Replace the `buildSidebarBiomarkers` stub**

This renders each lab group with its tests, values, optimal ranges, and status dots. Uses DOM methods throughout:

```javascript
function buildSidebarBiomarkers(el, data) {
  const labs = data.labs;
  if (!labs || !labs.groups || Object.keys(labs.groups).length === 0) {
    const p = document.createElement("p");
    p.style.cssText = "color:#888;font-style:italic";
    p.textContent = "No lab data available.";
    el.appendChild(p);
    return;
  }

  const dateDiv = document.createElement("div");
  dateDiv.style.cssText = "font-size:0.82rem;color:#888;margin-bottom:1rem";
  dateDiv.textContent = "Last panel: " + labs.date;
  el.appendChild(dateDiv);

  for (const [group, tests] of Object.entries(labs.groups)) {
    const groupDiv = document.createElement("div");
    groupDiv.className = "sidebar-chart";

    const title = document.createElement("div");
    title.className = "sidebar-section-title";
    title.textContent = group;
    groupDiv.appendChild(title);

    // Summary: count of green/amber/red
    const counts = { green: 0, amber: 0, red: 0 };
    for (const t of tests) counts[t.status]++;

    const summary = document.createElement("div");
    summary.style.cssText = "font-size:0.78rem;margin-bottom:0.5rem;color:#888";
    const parts = [];
    if (counts.green > 0) parts.push(counts.green + " optimal");
    if (counts.amber > 0) parts.push(counts.amber + " borderline");
    if (counts.red > 0) parts.push(counts.red + " out of range");
    summary.textContent = parts.join(", ");
    groupDiv.appendChild(summary);

    // Individual tests
    for (const t of tests) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:0.15rem 0;font-size:0.82rem;border-bottom:1px solid #f5f5f0";

      const nameSpan = document.createElement("span");
      nameSpan.textContent = t.test;
      nameSpan.style.color = "#444";

      const valContainer = document.createElement("span");
      valContainer.style.cssText = "font-variant-numeric:tabular-nums;display:flex;align-items:center;gap:0.4rem";

      const valText = document.createElement("span");
      valText.textContent = t.value + (t.unit ? " " + t.unit : "");
      valContainer.appendChild(valText);

      const dot = document.createElement("span");
      dot.className = "dot dot-" + t.status;
      valContainer.appendChild(dot);

      row.appendChild(nameSpan);
      row.appendChild(valContainer);
      groupDiv.appendChild(row);
    }

    el.appendChild(groupDiv);
  }
}
```

**Step 2: Verify in browser**

Click "Clinical Biomarkers" heading. Sidebar should show:
- Last panel date
- Each lab group with summary counts (optimal/borderline/out of range)
- Individual test values with status dots

**Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): implement biomarkers sidebar with group summaries"
```

---

### Task 5: Implement trends sidebar builder

**Files:**
- Modify: `dashboard.html` (replace `buildSidebarTrends` stub)

**Step 1: Replace the `buildSidebarTrends` stub**

This renders an expanded chart for each trend metric with rolling averages and statistics. Uses the same D3 chart pattern as `buildSmallMultiples` but at sidebar width (340x160). Stats use `textContent`:

```javascript
function buildSidebarTrends(el, data) {
  const w = 340, h = 160;
  const margin = { top: 8, right: 40, bottom: 20, left: 34 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const charts = [
    { title: "Steps (30d avg)", rawData: data.steps,
      mapFn: d => ({ d: parseDate(d.d), v: d.r30, r7: d.r7 }),
      target: 10000, yFmt: d3.format(",.0f") },
    { title: "Sleep", rawData: data.sleep.filter(d => d.total > 0.5),
      mapFn: d => ({ d: parseDate(d.d), v: d.total }),
      target: 7.5, yFmt: d3.format(".1f") },
    { title: "Resting HR", rawData: data.rhr,
      mapFn: d => ({ d: parseDate(d.d), v: d.v }),
      target: 65, yFmt: d3.format(".0f"), lowerBetter: true },
    { title: "HRV (30d avg)", rawData: data.hrv,
      mapFn: d => ({ d: parseDate(d.d), v: d.r30 || d.v, r7: d.r7 }),
      target: 50, yFmt: d3.format(".0f") },
    { title: "SpO2 Min", rawData: data.spo2,
      mapFn: d => ({ d: parseDate(d.d), v: d.min }),
      target: 90, yFmt: d3.format(".0f") },
    { title: "Body Fat", rawData: data.bodyfat,
      mapFn: d => ({ d: parseDate(d.d), v: d.v }),
      target: 25, yFmt: d3.format(".1f"), lowerBetter: true },
    { title: "Weight", rawData: data.weight,
      mapFn: d => ({ d: parseDate(d.d), v: d.v }),
      target: null, yFmt: d3.format(".0f") },
    { title: "Respiratory Rate", rawData: data.respiratory_rate || [],
      mapFn: d => ({ d: parseDate(d.d), v: d.v }),
      target: null, yFmt: d3.format(".1f") },
  ];

  for (const ch of charts) {
    const chartData = ch.rawData.map(ch.mapFn).filter(d => d.d && d.v != null);
    if (chartData.length < 2) continue;

    const div = document.createElement("div");
    div.className = "sidebar-chart";

    const titleEl = document.createElement("div");
    titleEl.className = "chart-title";
    titleEl.textContent = ch.title;
    div.appendChild(titleEl);

    // Stats row
    const values = chartData.map(d => d.v);
    const statsDiv = document.createElement("div");
    statsDiv.style.cssText = "font-size:0.78rem;color:#888;margin-bottom:0.3rem;font-variant-numeric:tabular-nums";
    statsDiv.textContent = "min " + ch.yFmt(d3.min(values)) + "  max " + ch.yFmt(d3.max(values)) + "  avg " + ch.yFmt(d3.mean(values));
    div.appendChild(statsDiv);

    const svg = d3.select(div).append("svg").attr("width", w).attr("height", h);
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    const xExt = d3.extent(chartData, d => d.d);
    const yExt = d3.extent(chartData, d => d.v);
    let yMin = yExt[0], yMax = yExt[1];
    if (ch.target != null) { yMin = Math.min(yMin, ch.target); yMax = Math.max(yMax, ch.target); }
    yMin *= 0.95; yMax *= 1.05;

    const x = d3.scaleTime().domain(xExt).range([0, iw]);
    const y = d3.scaleLinear().domain([yMin, yMax]).range([ih, 0]);

    // Area + line
    const area = d3.area().x(d => x(d.d)).y0(ih).y1(d => y(d.v)).curve(d3.curveMonotoneX);
    g.append("path").attr("class", "data-area").attr("d", area(chartData));
    const line = d3.line().x(d => x(d.d)).y(d => y(d.v)).curve(d3.curveMonotoneX);
    g.append("path").attr("class", "data-line").attr("d", line(chartData));

    // 7-day rolling average overlay (if data has r7)
    const r7Data = chartData.filter(d => d.r7 != null && d.r7 > 0);
    if (r7Data.length >= 2) {
      const r7Line = d3.line().x(d => x(d.d)).y(d => y(d.r7)).curve(d3.curveMonotoneX);
      g.append("path").attr("d", r7Line(r7Data))
        .attr("fill", "none").attr("stroke", "#5b8a5e").attr("stroke-width", 1)
        .attr("stroke-dasharray", "4,3").attr("opacity", 0.7);
    }

    // Target line
    if (ch.target != null) {
      g.append("line").attr("class", "target-line")
        .attr("x1", 0).attr("x2", iw)
        .attr("y1", y(ch.target)).attr("y2", y(ch.target));
      g.append("text").attr("class", "annotation-text")
        .attr("x", iw + 3).attr("y", y(ch.target)).attr("dy", "0.35em")
        .text(ch.yFmt(ch.target));
    }

    // Endpoint
    const last = chartData[chartData.length - 1];
    g.append("circle").attr("class", "endpoint-dot")
      .attr("cx", x(last.d)).attr("cy", y(last.v)).attr("r", 2.5);
    g.append("text").attr("class", "annotation-text")
      .attr("x", x(last.d)).attr("y", y(last.v) - 6).attr("text-anchor", "end")
      .style("font-weight", "600").style("fill", "#333")
      .text(ch.yFmt(last.v));

    tufteYAxis(g, y, iw, ch.yFmt);
    tufteXAxis(g, x, ih, "%b '%y");
    addLineTooltip(g, chartData, x, y, ch.yFmt, iw, ih);

    el.appendChild(div);
  }
}
```

**Step 2: Verify in browser**

Click "Trends" heading. Sidebar should show:
- Each metric as a 340x160 chart (larger than the 280x110 small multiples)
- Min/max/avg stats above each chart
- Rolling average overlay where available (steps, HRV)
- Target lines, endpoint dots, tooltips

**Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): implement trends sidebar with expanded charts"
```

---

### Task 6: Implement gait sidebar builder

**Files:**
- Modify: `dashboard.html` (replace `buildSidebarGait` stub)

**Step 1: Replace the `buildSidebarGait` stub**

Renders walking speed and asymmetry as expanded charts plus step count trend:

```javascript
function buildSidebarGait(el, data) {
  const w = 340, h = 140;
  const margin = { top: 8, right: 40, bottom: 20, left: 34 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const charts = [
    { title: "Walking Speed", data: (data.walking_speed || []).map(d => ({ d: parseDate(d.d), v: d.v })),
      target: 3.0, yFmt: d3.format(".2f") },
    { title: "Walking Asymmetry", data: (data.walking_asymmetry || []).map(d => ({ d: parseDate(d.d), v: d.v })),
      target: 10, yFmt: d3.format(".1f"), lowerBetter: true },
    { title: "Daily Steps", data: data.steps.map(d => ({ d: parseDate(d.d), v: d.v })),
      target: 10000, yFmt: d3.format(",.0f") },
  ];

  for (const ch of charts) {
    const chartData = ch.data.filter(d => d.d && d.v != null);
    if (chartData.length < 2) continue;

    const div = document.createElement("div");
    div.className = "sidebar-chart";

    const titleEl = document.createElement("div");
    titleEl.className = "chart-title";
    titleEl.textContent = ch.title;
    div.appendChild(titleEl);

    // Stats
    const values = chartData.map(d => d.v);
    const statsDiv = document.createElement("div");
    statsDiv.style.cssText = "font-size:0.78rem;color:#888;margin-bottom:0.3rem;font-variant-numeric:tabular-nums";
    statsDiv.textContent = "min " + ch.yFmt(d3.min(values)) + "  max " + ch.yFmt(d3.max(values)) + "  avg " + ch.yFmt(d3.mean(values));
    div.appendChild(statsDiv);

    const svg = d3.select(div).append("svg").attr("width", w).attr("height", h);
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    const xExt = d3.extent(chartData, d => d.d);
    const yExt = d3.extent(chartData, d => d.v);
    let yMin = yExt[0], yMax = yExt[1];
    if (ch.target != null) { yMin = Math.min(yMin, ch.target); yMax = Math.max(yMax, ch.target); }
    yMin *= 0.95; yMax *= 1.05;

    const x = d3.scaleTime().domain(xExt).range([0, iw]);
    const y = d3.scaleLinear().domain([yMin, yMax]).range([ih, 0]);

    if (chartData.length < 20) {
      const line = d3.line().x(d => x(d.d)).y(d => y(d.v));
      g.append("path").attr("d", line(chartData)).attr("fill", "none").attr("stroke", "#999").attr("stroke-width", 0.8);
      g.selectAll("circle.scatter").data(chartData).join("circle")
        .attr("cx", d => x(d.d)).attr("cy", d => y(d.v)).attr("r", 3).attr("fill", "#333");
    } else {
      const area = d3.area().x(d => x(d.d)).y0(ih).y1(d => y(d.v)).curve(d3.curveMonotoneX);
      g.append("path").attr("class", "data-area").attr("d", area(chartData));
      const line = d3.line().x(d => x(d.d)).y(d => y(d.v)).curve(d3.curveMonotoneX);
      g.append("path").attr("class", "data-line").attr("d", line(chartData));
    }

    if (ch.target != null) {
      g.append("line").attr("class", "target-line")
        .attr("x1", 0).attr("x2", iw).attr("y1", y(ch.target)).attr("y2", y(ch.target));
      g.append("text").attr("class", "annotation-text")
        .attr("x", iw + 3).attr("y", y(ch.target)).attr("dy", "0.35em")
        .text(ch.yFmt(ch.target));
    }

    const last = chartData[chartData.length - 1];
    g.append("circle").attr("class", "endpoint-dot")
      .attr("cx", x(last.d)).attr("cy", y(last.v)).attr("r", 2.5);

    tufteYAxis(g, y, iw, ch.yFmt);
    tufteXAxis(g, x, ih, "%b '%y");
    addLineTooltip(g, chartData, x, y, ch.yFmt, iw, ih);
    el.appendChild(div);
  }
}
```

**Step 2: Verify in browser**

Click "Gait & Mobility" heading. Sidebar shows walking speed, asymmetry, and steps charts.

**Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): implement gait sidebar with speed, asymmetry, and steps"
```

---

### Task 7: Implement cardiovascular sidebar builder

**Files:**
- Modify: `dashboard.html` (replace `buildSidebarCardio` stub)

**Step 1: Replace the `buildSidebarCardio` stub**

Renders RHR vs HRV scatter plot and HR zone breakdown:

```javascript
function buildSidebarCardio(el, data) {
  const w = 340, h = 180;
  const margin = { top: 8, right: 12, bottom: 24, left: 34 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  // ── RHR vs HRV Scatter ──
  const rhrMap = new Map(data.rhr.map(d => [d.d, d.v]));
  const hrvMap = new Map(data.hrv.map(d => [d.d, d.v]));

  const scatterData = [];
  for (const [dateStr, rhr] of rhrMap) {
    const hrv = hrvMap.get(dateStr);
    if (rhr && hrv && rhr > 0 && hrv > 0) {
      scatterData.push({ d: parseDate(dateStr), rhr, hrv });
    }
  }

  if (scatterData.length >= 3) {
    const div = document.createElement("div");
    div.className = "sidebar-chart";

    const titleEl = document.createElement("div");
    titleEl.className = "chart-title";
    titleEl.textContent = "Resting HR vs HRV (daily)";
    div.appendChild(titleEl);

    const svg = d3.select(div).append("svg").attr("width", w).attr("height", h);
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    const xExt = d3.extent(scatterData, d => d.rhr);
    const yExt = d3.extent(scatterData, d => d.hrv);
    const x = d3.scaleLinear().domain([xExt[0] * 0.95, xExt[1] * 1.05]).range([0, iw]);
    const y = d3.scaleLinear().domain([yExt[0] * 0.9, yExt[1] * 1.1]).range([ih, 0]);

    // Color by recency (most recent = darkest)
    const dateExt = d3.extent(scatterData, d => d.d);
    const colorScale = d3.scaleLinear()
      .domain([dateExt[0], dateExt[1]])
      .range([0.15, 0.8]);

    g.selectAll("circle").data(scatterData).join("circle")
      .attr("cx", d => x(d.rhr))
      .attr("cy", d => y(d.hrv))
      .attr("r", 2.5)
      .attr("fill", "#333")
      .attr("opacity", d => colorScale(d.d));

    // Axis labels
    g.append("text").attr("class", "axis-label")
      .attr("x", iw / 2).attr("y", ih + 16).attr("text-anchor", "middle")
      .text("Resting HR (bpm)");
    g.append("text").attr("class", "axis-label")
      .attr("transform", "rotate(-90)")
      .attr("x", -ih / 2).attr("y", -24).attr("text-anchor", "middle")
      .text("HRV (ms)");

    tufteYAxis(g, y, iw, d3.format(".0f"));

    // X axis min/max
    g.append("text").attr("class", "axis-label")
      .attr("x", 0).attr("y", ih + 16).attr("text-anchor", "start")
      .text(d3.format(".0f")(x.domain()[0]));
    g.append("text").attr("class", "axis-label")
      .attr("x", iw).attr("y", ih + 16).attr("text-anchor", "end")
      .text(d3.format(".0f")(x.domain()[1]));

    el.appendChild(div);
  }

  // ── HR Zone weekly breakdown ──
  const hrData = data.hrzones.map(d => ({
    d: parseDate(d.d),
    z2: d.z2,
    z4: d.z4,
  }));

  if (hrData.length >= 2) {
    const div2 = document.createElement("div");
    div2.className = "sidebar-chart";

    const titleEl2 = document.createElement("div");
    titleEl2.className = "chart-title";
    titleEl2.textContent = "Weekly HR zone minutes";
    div2.appendChild(titleEl2);

    const svg2 = d3.select(div2).append("svg").attr("width", w).attr("height", 140);
    const g2 = svg2.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    const ih2 = 140 - margin.top - margin.bottom;

    const x2 = d3.scaleBand().domain(hrData.map(d => d.d)).range([0, iw]).padding(0.3);
    const maxY = d3.max(hrData, d => d.z2 + d.z4) || 30;
    const y2 = d3.scaleLinear().domain([0, Math.max(maxY * 1.1, 30)]).range([ih2, 0]);

    hrData.forEach(d => {
      const barW = x2.bandwidth();
      const xPos = x2(d.d);
      // Z2 bar
      if (d.z2 > 0) {
        g2.append("rect").attr("x", xPos).attr("y", y2(d.z2)).attr("width", barW)
          .attr("height", ih2 - y2(d.z2)).attr("fill", "#777");
      }
      // Z4 bar on top
      if (d.z4 > 0) {
        g2.append("rect").attr("x", xPos).attr("y", y2(d.z2 + d.z4)).attr("width", barW)
          .attr("height", ih2 - y2(d.z4)).attr("fill", "#333");
      }
    });

    tufteYAxis(g2, y2, iw, d3.format(".0f"));
    const dfmt = d3.timeFormat("%b %d");
    g2.append("text").attr("class", "axis-label")
      .attr("x", 0).attr("y", ih2 + 14).attr("text-anchor", "start").text(dfmt(hrData[0].d));
    g2.append("text").attr("class", "axis-label")
      .attr("x", iw).attr("y", ih2 + 14).attr("text-anchor", "end").text(dfmt(hrData[hrData.length - 1].d));

    // Legend
    const leg = g2.append("g").attr("transform", `translate(${iw - 80}, 0)`);
    [{ label: "Zone 2", color: "#777" }, { label: "Zone 4+", color: "#333" }].forEach((l, i) => {
      leg.append("rect").attr("x", 0).attr("y", i * 13).attr("width", 10).attr("height", 8).attr("fill", l.color);
      leg.append("text").attr("class", "annotation-text").attr("x", 14).attr("y", i * 13 + 7).text(l.label);
    });

    el.appendChild(div2);
  }

  // ── VO2 Max trend ──
  const vo2Data = data.vo2.map(d => ({ d: parseDate(d.d), v: d.v }));
  if (vo2Data.length >= 2) {
    const div3 = document.createElement("div");
    div3.className = "sidebar-chart";

    const titleEl3 = document.createElement("div");
    titleEl3.className = "chart-title";
    titleEl3.textContent = "VO2 Max trend";
    div3.appendChild(titleEl3);

    const svg3 = d3.select(div3).append("svg").attr("width", w).attr("height", 120);
    const g3 = svg3.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    const ih3 = 120 - margin.top - margin.bottom;

    const x3 = d3.scaleTime().domain(d3.extent(vo2Data, d => d.d)).range([0, iw]);
    const y3 = d3.scaleLinear().domain([24, 45]).range([ih3, 0]);

    g3.selectAll("circle").data(vo2Data).join("circle")
      .attr("cx", d => x3(d.d)).attr("cy", d => y3(d.v)).attr("r", 3).attr("fill", "#333");
    const line3 = d3.line().x(d => x3(d.d)).y(d => y3(d.v));
    g3.append("path").attr("d", line3(vo2Data)).attr("fill", "none").attr("stroke", "#333").attr("stroke-width", 1);

    // Targets
    [35, 40].forEach(t => {
      g3.append("line").attr("class", "target-line")
        .attr("x1", 0).attr("x2", iw).attr("y1", y3(t)).attr("y2", y3(t));
      g3.append("text").attr("class", "annotation-text")
        .attr("x", iw + 3).attr("y", y3(t)).attr("dy", "0.35em").text(t);
    });

    tufteYAxis(g3, y3, iw, d3.format(".0f"));
    tufteXAxis(g3, x3, ih3, "%b '%y");
    el.appendChild(div3);
  }
}
```

**Step 2: Verify in browser**

Click "Cardiovascular Detail" heading. Sidebar should show:
- RHR vs HRV scatter (dots fading from light to dark by recency)
- Weekly HR zone stacked bars
- VO2 Max trend with target lines

**Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): implement cardiovascular sidebar with scatter and zones"
```

---

### Task 8: Implement sleep sidebar builder

**Files:**
- Modify: `dashboard.html` (replace `buildSidebarSleep` stub)

**Step 1: Replace the `buildSidebarSleep` stub**

Renders sleep stage percentage trends and sleep duration consistency:

```javascript
function buildSidebarSleep(el, data) {
  const w = 340, h = 160;
  const margin = { top: 8, right: 40, bottom: 20, left: 34 };
  const iw = w - margin.left - margin.right;
  const ih = h - margin.top - margin.bottom;

  const sleepData = data.sleep.filter(d => d.total > 0.5).map(d => ({
    d: parseDate(d.d),
    deep: d.deep ?? 0,
    rem: d.rem ?? 0,
    light: Math.max(0, d.total - (d.deep ?? 0) - (d.rem ?? 0)),
    total: d.total
  }));

  if (sleepData.length < 2) {
    const p = document.createElement("p");
    p.style.cssText = "color:#888;font-style:italic";
    p.textContent = "Not enough sleep data.";
    el.appendChild(p);
    return;
  }

  // ── Sleep stage percentages over time ──
  const div1 = document.createElement("div");
  div1.className = "sidebar-chart";

  const title1 = document.createElement("div");
  title1.className = "chart-title";
  title1.textContent = "Sleep stage % (7-day rolling)";
  div1.appendChild(title1);

  // Compute 7-day rolling percentages
  const pctData = [];
  for (let i = 0; i < sleepData.length; i++) {
    const win = sleepData.slice(Math.max(0, i - 6), i + 1);
    const avgDeep = d3.mean(win, d => d.deep / d.total * 100);
    const avgRem = d3.mean(win, d => d.rem / d.total * 100);
    const avgLight = d3.mean(win, d => d.light / d.total * 100);
    pctData.push({ d: sleepData[i].d, deep: avgDeep, rem: avgRem, light: avgLight });
  }

  const svg1 = d3.select(div1).append("svg").attr("width", w).attr("height", h);
  const g1 = svg1.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x1 = d3.scaleTime().domain(d3.extent(pctData, d => d.d)).range([0, iw]);
  const y1 = d3.scaleLinear().domain([0, 60]).range([ih, 0]);

  const stages = [
    { key: "deep", color: "#444", label: "Deep" },
    { key: "rem", color: "#888", label: "REM" },
    { key: "light", color: "#c8c8be", label: "Light" },
  ];

  for (const stage of stages) {
    const line = d3.line()
      .x(d => x1(d.d)).y(d => y1(d[stage.key]))
      .curve(d3.curveMonotoneX);
    g1.append("path").attr("d", line(pctData))
      .attr("fill", "none").attr("stroke", stage.color).attr("stroke-width", 1.3);

    // Label at end
    const last = pctData[pctData.length - 1];
    g1.append("text").attr("class", "annotation-text")
      .attr("x", iw + 3).attr("y", y1(last[stage.key])).attr("dy", "0.35em")
      .text(d3.format(".0f")(last[stage.key]) + "% " + stage.label);
  }

  tufteYAxis(g1, y1, iw, d => d + "%");
  tufteXAxis(g1, x1, ih, "%b '%y");
  el.appendChild(div1);

  // ── Total sleep trend ──
  const div2 = document.createElement("div");
  div2.className = "sidebar-chart";

  const title2 = document.createElement("div");
  title2.className = "chart-title";
  title2.textContent = "Total sleep (hours)";
  div2.appendChild(title2);

  const svg2 = d3.select(div2).append("svg").attr("width", w).attr("height", 120);
  const g2 = svg2.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  const ih2 = 120 - margin.top - margin.bottom;

  const x2 = d3.scaleTime().domain(d3.extent(sleepData, d => d.d)).range([0, iw]);
  const y2 = d3.scaleLinear().domain([4, 10]).range([ih2, 0]);

  const area2 = d3.area().x(d => x2(d.d)).y0(ih2).y1(d => y2(d.total)).curve(d3.curveMonotoneX);
  g2.append("path").attr("class", "data-area").attr("d", area2(sleepData));
  const line2 = d3.line().x(d => x2(d.d)).y(d => y2(d.total)).curve(d3.curveMonotoneX);
  g2.append("path").attr("class", "data-line").attr("d", line2(sleepData));

  // Target
  g2.append("line").attr("class", "target-line")
    .attr("x1", 0).attr("x2", iw).attr("y1", y2(7.5)).attr("y2", y2(7.5));
  g2.append("text").attr("class", "annotation-text")
    .attr("x", iw + 3).attr("y", y2(7.5)).attr("dy", "0.35em").text("7.5 target");

  tufteYAxis(g2, y2, iw, d3.format(".1f"));
  tufteXAxis(g2, x2, ih2, "%b '%y");
  addLineTooltip(g2, sleepData.map(d => ({ d: d.d, v: d.total })), x2, y2, d3.format(".1f"), iw, ih2);
  el.appendChild(div2);

  // ── Summary stats ──
  const statsDiv = document.createElement("div");
  statsDiv.style.cssText = "font-size:0.82rem;color:#666;margin-top:0.5rem;line-height:1.6";
  const avgTotal = d3.mean(sleepData, d => d.total);
  const avgDeep = d3.mean(sleepData, d => d.deep);
  const avgRem = d3.mean(sleepData, d => d.rem);
  const avgDeepPct = d3.mean(sleepData, d => d.deep / d.total * 100);
  const avgRemPct = d3.mean(sleepData, d => d.rem / d.total * 100);

  const strong = document.createElement("strong");
  strong.textContent = "Period averages:";
  statsDiv.appendChild(strong);
  statsDiv.appendChild(document.createElement("br"));
  statsDiv.appendChild(document.createTextNode(
    "Total: " + d3.format(".1f")(avgTotal) + " hrs \u00b7 " +
    "Deep: " + d3.format(".1f")(avgDeep) + " hrs (" + d3.format(".0f")(avgDeepPct) + "%) \u00b7 " +
    "REM: " + d3.format(".1f")(avgRem) + " hrs (" + d3.format(".0f")(avgRemPct) + "%)"
  ));
  el.appendChild(statsDiv);
}
```

**Step 2: Verify in browser**

Click "Sleep Architecture" heading. Sidebar should show:
- Sleep stage percentage lines (Deep, REM, Light) over time
- Total sleep area chart with 7.5-hour target
- Period averages summary text

**Step 3: Commit**

```bash
git add dashboard.html
git commit -m "feat(dashboard): implement sleep sidebar with stage trends and stats"
```

---

### Task 9: Final verification and integration commit

**Step 1: Full end-to-end verification**

Open `dashboard.html` in a browser with the DuckDB file. Test each interaction:

1. Click each of the 6 section headings -- sidebar opens with correct content
2. Click same heading -- sidebar closes (toggle behavior)
3. Click different heading while sidebar is open -- content swaps without close/reopen flash
4. Press Escape -- sidebar closes
5. Click the X button -- sidebar closes
6. Change date range (30d/90d/1y/All) while sidebar is open -- content refreshes
7. Hover chart tooltips in sidebar -- they work correctly
8. Resize browser to <720px -- sidebar becomes bottom sheet
9. Verify all main dashboard charts still render correctly (no regressions)
10. Check browser console for JavaScript errors

**Step 2: Fix any issues found**

If tooltips inside the sidebar overflow, the sidebar's `overflow-y: auto` should handle it. If tooltip positions are off (because they reference viewport coords), adjust as needed.

**Step 3: Commit (if fixes needed)**

```bash
git add dashboard.html
git commit -m "fix(dashboard): polish sidebar interactions and edge cases"
```
