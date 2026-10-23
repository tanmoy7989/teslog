(() => {
  "use strict";

  const style = getComputedStyle(document.documentElement);
  const color = (name) => style.getPropertyValue(name).trim();

  const palette = {
    series1: color("--series-1"),
    series2: color("--series-2"),
    series3: color("--series-3"),
    gridline: color("--gridline"),
    baseline: color("--baseline"),
    textMuted: color("--text-muted"),
    textSecondary: color("--text-secondary"),
    textPrimary: color("--text-primary"),
    surface: color("--surface-1"),
    border: color("--border"),
    statusGood: color("--status-good"),
    statusWarning: color("--status-warning"),
    statusCritical: color("--status-critical"),
  };

  // Chart window slider stops, in slider order. `days: null` = all history (no ?days= sent).
  const WINDOWS = [
    { days: 30, name: "30 days", chip: "last 30 days" },
    { days: 90, name: "90 days", chip: "last 90 days" },
    { days: 365, name: "1 year", chip: "last year" },
    { days: null, name: "All history", chip: "all history" },
  ];
  const DEFAULT_WINDOW_INDEX = 1;
  const WINDOW_STORAGE_KEY = "teslog.chartWindow";

  function withAlpha(hex, alpha) {
    const h = hex.replace("#", "");
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function formatLabel(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function formatLongDate(date) {
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) return null;
    return response.json();
  }

  function baseScales(extraY = {}, extraX = {}) {
    return {
      x: {
        grid: { color: palette.gridline, drawTicks: false },
        border: { color: palette.baseline },
        ticks: { color: palette.textMuted, maxRotation: 0, autoSkip: true, font: { size: 11 } },
        ...extraX,
      },
      y: {
        beginAtZero: true,
        grid: { color: palette.gridline, drawTicks: false },
        border: { display: false },
        ticks: { color: palette.textMuted, font: { size: 11 } },
        ...extraY,
      },
    };
  }

  function tooltipConfig() {
    return {
      mode: "index",
      intersect: false,
      backgroundColor: palette.surface,
      titleColor: palette.textPrimary,
      bodyColor: palette.textSecondary,
      borderColor: palette.border,
      borderWidth: 1,
      padding: 10,
      boxPadding: 4,
      titleFont: { size: 12, weight: "600" },
      bodyFont: { size: 12 },
    };
  }

  // Charts are redrawn every time the window changes, so a canvas may already hold a chart (to
  // destroy first) or be hidden behind an empty state from the previous window (to bring back).
  function mountChart(canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const wrap = canvas.closest(".chart-canvas-wrap") || canvas.parentElement;
    wrap.querySelector(".empty-state")?.remove();
    canvas.style.display = "";
    Chart.getChart(canvas)?.destroy();
    new Chart(canvas, config);
  }

  function showEmpty(canvasId, title, hint) {
    const canvas = document.getElementById(canvasId);
    const wrap = canvas.closest(".chart-canvas-wrap") || canvas.parentElement;
    Chart.getChart(canvas)?.destroy();
    canvas.style.display = "none";
    wrap.querySelector(".empty-state")?.remove();
    const div = document.createElement("div");
    div.className = "empty-state";
    const titleEl = document.createElement("div");
    titleEl.className = "empty-title";
    titleEl.textContent = title;
    const hintEl = document.createElement("div");
    hintEl.textContent = hint;
    div.appendChild(titleEl);
    div.appendChild(hintEl);
    wrap.appendChild(div);
  }

  // Empty-state copy for a windowed chart: "nothing yet" only makes sense on all history — in a
  // shorter window the data may well exist, just further back.
  function emptyText(win, noun, allTitle, allHint) {
    if (win.days === null) return [allTitle, allHint];
    return [`No ${noun} in the ${win.chip}`, "Slide the window wider to include older history."];
  }

  function renderLegend(elementId, items) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.innerHTML = "";
    for (const item of items) {
      const span = document.createElement("span");
      span.className = "legend-item";
      const swatch = document.createElement("span");
      swatch.className = "swatch" + (item.dot ? " dot" : "");
      swatch.style.background = item.color;
      const label = document.createElement("span");
      label.textContent = item.label;
      span.appendChild(swatch);
      span.appendChild(label);
      el.appendChild(span);
    }
  }

  function cumulativeSum(values) {
    let sum = 0;
    return values.map((v) => (sum += v || 0));
  }

  // Running totals start from 0 at the window's first drive, not from all-history totals — an
  // all-history offset would just lift both lines by the same constant and flatten the gap.
  function renderDistanceChart(rows, win) {
    if (!rows || rows.length === 0) {
      showEmpty("chart-distance", ...emptyText(win, "drives", "No completed drives yet", "Charts fill in once TeslaMate records a drive."));
      return;
    }
    const legendEl = document.getElementById("legend-distance");
    const preTrackingMi = legendEl.dataset.preTrackingMi;
    const preTrackingDate = legendEl.dataset.preTrackingDate;
    renderLegend("legend-distance", [
      { label: "Odometer", color: palette.series1 },
      { label: "GPS trace", color: palette.series3 },
      { label: `Pre-tracking odometer: ${preTrackingMi} mi (${preTrackingDate})`, color: palette.baseline },
    ]);
    mountChart("chart-distance", {
      type: "line",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          { label: "Odometer", data: cumulativeSum(rows.map((r) => r.odometer_mi)), borderColor: palette.series1, backgroundColor: palette.series1, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
          { label: "GPS trace", data: cumulativeSum(rows.map((r) => r.gps_mi)), borderColor: palette.series3, backgroundColor: palette.series3, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: baseScales({ title: { display: true, text: "cumulative mi", color: palette.textMuted, font: { size: 11 } } }),
        plugins: { legend: { display: false }, tooltip: tooltipConfig() },
      },
    });
  }

  // Odometer (x) vs. GPS traced distance (y), one point per drive, plus a y=x reference line —
  // points on the line mean the traced distance matched the odometer exactly.
  function renderScatterChart(rows, win) {
    if (!rows || rows.length === 0) {
      showEmpty("chart-scatter", ...emptyText(win, "drives", "No completed drives yet", "Charts fill in once TeslaMate records a drive."));
      return;
    }
    renderLegend("legend-scatter", [{ label: "GPS trace", color: palette.series3, dot: true }]);
    const allVals = rows.flatMap((r) => [r.odometer_mi, r.gps_mi]).filter((v) => v !== null && v !== undefined);
    const lo = Math.floor(Math.min(...allVals) - 0.5);
    const hi = Math.ceil(Math.max(...allVals) + 0.5);

    mountChart("chart-scatter", {
      type: "line",
      data: {
        datasets: [
          {
            label: "Perfect agreement",
            data: [{ x: lo, y: lo }, { x: hi, y: hi }],
            borderColor: palette.baseline,
            borderWidth: 1.5,
            borderDash: [4, 4],
            pointRadius: 0,
            showLine: true,
            order: 3,
          },
          {
            label: "GPS trace",
            data: rows.map((r) => ({ x: r.odometer_mi, y: r.gps_mi })),
            borderColor: palette.series3,
            backgroundColor: palette.series3,
            showLine: false,
            pointRadius: 4,
            pointHoverRadius: 6,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: true },
        scales: baseScales(
          { title: { display: true, text: "traced distance (mi)", color: palette.textMuted, font: { size: 11 } }, beginAtZero: false, min: lo, max: hi },
          { type: "linear", title: { display: true, text: "odometer (mi)", color: palette.textMuted, font: { size: 11 } }, min: lo, max: hi }
        ),
        plugins: {
          legend: { display: false },
          tooltip: {
            ...tooltipConfig(),
            mode: "nearest",
            intersect: true,
            filter: (item) => item.datasetIndex !== 0,
            callbacks: {
              label: (item) => `${item.dataset.label}: ${item.parsed.y.toFixed(2)} mi (odo ${item.parsed.x.toFixed(2)} mi)`,
            },
          },
        },
      },
    });
  }

  function renderDriftChart(rows, win) {
    if (!rows || rows.length === 0) {
      showEmpty("chart-drift", ...emptyText(win, "drift data", "No drift data yet", "Shows up once a completed drive has both odometer and GPS distance."));
      return;
    }
    renderLegend("legend-drift", [{ label: "GPSDrift", color: palette.series3 }]);
    mountChart("chart-drift", {
      type: "line",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          { label: "GPSDrift", data: rows.map((r) => r.haversine_drift_pct), borderColor: palette.series3, backgroundColor: palette.series3, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25, spanGaps: true },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: baseScales({ title: { display: true, text: "%", color: palette.textMuted, font: { size: 11 } } }),
        plugins: { legend: { display: false }, tooltip: tooltipConfig() },
      },
    });
  }

  function renderSingleLineChart(canvasId, rows, field, opts) {
    const values = (rows || []).filter((r) => r[field] !== null && r[field] !== undefined);
    if (values.length === 0) {
      showEmpty(canvasId, opts.emptyTitle, opts.emptyHint);
      return;
    }
    mountChart(canvasId, {
      type: "line",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          {
            data: rows.map((r) => r[field]),
            borderColor: palette.series1,
            backgroundColor: withAlpha(palette.series1, 0.1),
            borderWidth: 2,
            pointRadius: 2,
            pointHoverRadius: 5,
            tension: 0.25,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: baseScales({ title: { display: true, text: opts.unit, color: palette.textMuted, font: { size: 11 } } }),
        plugins: { legend: { display: false }, tooltip: tooltipConfig() },
      },
    });
  }

  function renderBarChart(canvasId, rows, field, opts) {
    const values = (rows || []).filter((r) => r[field] !== null && r[field] !== undefined);
    if (values.length === 0) {
      showEmpty(canvasId, opts.emptyTitle, opts.emptyHint);
      return;
    }
    mountChart(canvasId, {
      type: "bar",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          {
            data: rows.map((r) => r[field]),
            backgroundColor: palette.series1,
            borderRadius: { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 },
            borderSkipped: "bottom",
            maxBarThickness: 24,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: baseScales({ title: { display: true, text: opts.unit, color: palette.textMuted, font: { size: 11 } } }),
        plugins: { legend: { display: false }, tooltip: tooltipConfig() },
      },
    });
  }

  function renderSparkline(canvasId, rows, field, color) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    Chart.getChart(ctx)?.destroy();
    if (!rows || rows.length < 2) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => r.date),
        datasets: [
          { data: rows.map((r) => r[field]), borderColor: color, borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { x: { display: false }, y: { display: false } },
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
    });
  }

  function mean(values) {
    return values.reduce((sum, v) => sum + v, 0) / values.length;
  }

  // Sample (N-1) standard deviation — null if there's fewer than 2 values to compare.
  function sampleStdev(values, avg) {
    if (values.length < 2) return null;
    const variance = values.reduce((sum, v) => sum + (v - avg) ** 2, 0) / (values.length - 1);
    return Math.sqrt(variance);
  }

  // Sets a KPI sub-row's value to the mean of every non-null `field` reading in `rows` (every
  // drive in the current chart window, or all history for the cumulative tile), and its delta to
  // their sample standard deviation — how consistent that's been, not a change-vs-previous-drive.
  function setMeanStdevKpiValue(tile, valueSelector, deltaSelector, rows, field, formatValue, formatDelta) {
    const values = (rows || []).map((r) => r[field]).filter((v) => v !== null && v !== undefined);
    const valueEl = tile.querySelector(valueSelector);
    const deltaEl = tile.querySelector(deltaSelector);
    deltaEl.classList.remove("good", "bad");
    if (values.length === 0) {
      valueEl.textContent = "—";
      deltaEl.textContent = "";
      return;
    }
    const avg = mean(values);
    valueEl.textContent = formatValue(avg);
    const stdev = sampleStdev(values, avg);
    deltaEl.textContent = stdev === null ? "" : formatDelta(stdev);
  }

  function renderDriftKpi(rows) {
    const tile = document.getElementById("kpi-drift");
    const fmtValue = (v) => `${v.toFixed(1)}%`;
    const fmtDelta = (v) => `±${v.toFixed(1)}pp`;
    setMeanStdevKpiValue(tile, ".value", ".delta", rows, "haversine_drift_pct", fmtValue, fmtDelta);
    renderSparkline("kpi-drift-spark", (rows || []).slice(-12), "haversine_drift_pct", palette.series3);
  }

  // Always all history, whatever the window — see metrics.cumulative_drift_series.
  async function renderCumulativeDriftKpi() {
    const rows = await fetchJSON("/api/metrics/cumulative-drift");
    const tile = document.getElementById("kpi-cumulative-drift");
    const fmtValue = (v) => `${v.toFixed(1)}%`;
    const fmtDelta = (v) => `±${v.toFixed(1)}pp`;
    setMeanStdevKpiValue(tile, ".value", ".delta", rows, "cum_gps_drift_pct", fmtValue, fmtDelta);
    renderSparkline("kpi-cumulative-drift-spark", (rows || []).slice(-12), "cum_gps_drift_pct", palette.series3);
  }

  function renderEfficiencyKpi(rows) {
    const tile = document.getElementById("kpi-efficiency");
    setMeanStdevKpiValue(
      tile,
      ".value",
      ".delta",
      rows,
      "wh_per_mi",
      (v) => `${Math.round(v)}`,
      (v) => `±${Math.round(v)} Wh/mi`
    );
  }

  async function renderBatteryHealthKpi() {
    const data = await fetchJSON("/api/metrics/battery-health");
    const tile = document.getElementById("kpi-battery");
    const valueEl = tile.querySelector(".value");
    const fillEl = tile.querySelector(".meter-fill");
    if (!data || data.battery_health_pct === undefined) {
      valueEl.textContent = "—";
      tile.querySelector(".meter-track").style.display = "none";
      return;
    }
    const pct = data.battery_health_pct;
    valueEl.textContent = `${Math.round(pct)}%`;
    fillEl.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    fillEl.style.background =
      pct >= 90 ? palette.statusGood : pct >= 70 ? palette.statusWarning : palette.statusCritical;
  }

  // --- Chart window -------------------------------------------------------------------------

  const slider = document.getElementById("window-slider");

  // Starting stop: this browser's last choice, else the server's TESLOG_CHART_WINDOW_DAYS
  // (0 = all history), else 90 days. Storage can be unavailable (private mode), so it's
  // best-effort only.
  function initialWindowIndex() {
    try {
      const raw = localStorage.getItem(WINDOW_STORAGE_KEY);
      const stored = Number(raw);
      if (raw !== null && Number.isInteger(stored) && stored >= 0 && stored < WINDOWS.length) return stored;
    } catch {}
    const serverDays = Number(document.querySelector(".window-control").dataset.defaultDays);
    const idx = WINDOWS.findIndex((w) => (w.days ?? 0) === serverDays);
    return idx >= 0 ? idx : DEFAULT_WINDOW_INDEX;
  }

  function saveWindowIndex(idx) {
    try {
      localStorage.setItem(WINDOW_STORAGE_KEY, String(idx));
    } catch {}
  }

  function withWindow(url, win) {
    return win.days === null ? url : `${url}?days=${win.days}`;
  }

  // Slider label, stop highlight and window chips — cheap, so updated live while dragging.
  function renderWindowControls(win, idx) {
    document.getElementById("window-name").textContent = win.name;
    slider.setAttribute("aria-valuetext", win.name);
    document.querySelectorAll(".window-stop").forEach((el, i) => el.classList.toggle("active", i === idx));
    document.querySelectorAll(".window-chip:not(.all)").forEach((el) => (el.textContent = win.chip));
  }

  function renderWindowSummary(win, distance, charging) {
    const today = new Date();
    let start;
    if (win.days !== null) {
      start = new Date(today.getTime() - win.days * 864e5);
    } else {
      const dates = [...(distance || []), ...(charging || [])].map((r) => new Date(r.date));
      start = dates.length ? new Date(Math.min(...dates)) : null;
    }
    const drives = (distance || []).length;
    const charges = (charging || []).length;
    const range = start ? `${formatLongDate(start)} – ${formatLongDate(today)}` : "all history";
    document.getElementById("window-summary").textContent =
      `Showing ${range} · ${drives} drive${drives === 1 ? "" : "s"} · ${charges} charge${charges === 1 ? "" : "s"}`;
    document.getElementById("distance-desc").textContent = start
      ? `Cumulative odometer vs. GPS trace, running total from ${formatLongDate(start)}`
      : "Cumulative odometer vs. GPS trace, running total across drives";
  }

  // CSV downloads match what's on screen: same window as the charts.
  function renderCsvLinks(win) {
    document.querySelectorAll("a.csv-link").forEach((link) => {
      link.dataset.baseHref ??= link.getAttribute("href");
      link.setAttribute("href", withWindow(link.dataset.baseHref, win));
    });
  }

  // Bumped per window change; a fetch that finishes after a newer change began is dropped, so a
  // slow response for an old window can't overwrite the charts for the current one.
  let windowGeneration = 0;

  async function renderWindowed(win) {
    const generation = ++windowGeneration;
    renderCsvLinks(win);
    const [distance, drift, energyUsed, efficiency, charging] = await Promise.all(
      ["distance", "drift", "energy-used", "energy-efficiency", "charging-energy"].map((name) =>
        fetchJSON(withWindow(`/api/metrics/${name}`, win))
      )
    );
    if (generation !== windowGeneration) return;

    renderWindowSummary(win, distance, charging);
    renderDriftKpi(drift);
    renderEfficiencyKpi(efficiency);
    renderDistanceChart(distance, win);
    renderScatterChart(distance, win);
    renderDriftChart(drift, win);
    const [energyTitle, energyHint] = emptyText(win, "energy data", "No energy data yet", "Needs completed drives and a car with a learned rated efficiency.");
    renderBarChart("chart-energy-used", energyUsed, "kwh_used", { unit: "kWh", emptyTitle: energyTitle, emptyHint: energyHint });
    const [effTitle, effHint] = emptyText(win, "efficiency data", "No efficiency data yet", "Needs completed drives and a car with a learned rated efficiency.");
    renderSingleLineChart("chart-energy-efficiency", efficiency, "wh_per_mi", { unit: "Wh/mi", emptyTitle: effTitle, emptyHint: effHint });
    const [chargeTitle, chargeHint] = emptyText(win, "charging sessions", "No charging sessions yet", "Shows up once TeslaMate records a completed charge.");
    renderBarChart("chart-charging-energy", charging, "kwh_added", { unit: "kWh", emptyTitle: chargeTitle, emptyHint: chargeHint });
  }

  async function handleSync() {
    const btn = document.getElementById("sync-btn");
    btn.disabled = true;
    btn.textContent = "Syncing…";
    try {
      await fetch("/api/sync", { method: "POST" });
    } finally {
      location.reload();
    }
  }

  document.getElementById("sync-btn").addEventListener("click", handleSync);

  const startIdx = initialWindowIndex();
  slider.value = String(startIdx);
  renderWindowControls(WINDOWS[startIdx], startIdx);

  // `input` fires continuously while dragging (labels only); `change` fires once the thumb
  // settles on a stop (mouse release, or each arrow-key step) — that's when charts refetch.
  slider.addEventListener("input", () => {
    const idx = Number(slider.value);
    renderWindowControls(WINDOWS[idx], idx);
  });
  slider.addEventListener("change", () => {
    const idx = Number(slider.value);
    saveWindowIndex(idx);
    renderWindowed(WINDOWS[idx]);
  });

  renderCumulativeDriftKpi();
  renderBatteryHealthKpi();
  renderWindowed(WINDOWS[startIdx]);
})();
