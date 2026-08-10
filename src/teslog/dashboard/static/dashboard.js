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

  function showEmpty(canvasId, title, hint) {
    const canvas = document.getElementById(canvasId);
    const wrap = canvas.closest(".chart-canvas-wrap") || canvas.parentElement;
    canvas.remove();
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

  async function renderDistanceChart() {
    const rows = await fetchJSON("/api/metrics/distance");
    if (!rows || rows.length === 0) {
      showEmpty("chart-distance", "No completed drives yet", "Charts fill in once TeslaMate records a drive.");
      return;
    }
    renderLegend("legend-distance", [
      { label: "Odometer", color: palette.series1 },
      { label: "OSRM route", color: palette.series2 },
      { label: "GPS trace", color: palette.series3 },
    ]);
    const ctx = document.getElementById("chart-distance");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          { label: "Odometer", data: cumulativeSum(rows.map((r) => r.odometer_mi)), borderColor: palette.series1, backgroundColor: palette.series1, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
          { label: "OSRM route", data: cumulativeSum(rows.map((r) => r.osrm_mi)), borderColor: palette.series2, backgroundColor: palette.series2, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
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
    return rows;
  }

  // Odometer (x) vs. OSRM / GPS traced distance (y), one point per drive, plus a y=x reference
  // line — points on the line mean the traced distance matched the odometer exactly.
  async function renderScatterChart(distanceRows) {
    const rows = distanceRows || (await fetchJSON("/api/metrics/distance"));
    if (!rows || rows.length === 0) {
      showEmpty("chart-scatter", "No completed drives yet", "Charts fill in once TeslaMate records a drive.");
      return;
    }
    renderLegend("legend-scatter", [
      { label: "OSRM route", color: palette.series2, dot: true },
      { label: "GPS trace", color: palette.series3, dot: true },
    ]);
    const allVals = rows.flatMap((r) => [r.odometer_mi, r.osrm_mi, r.gps_mi]).filter((v) => v !== null && v !== undefined);
    const lo = Math.floor(Math.min(...allVals) - 0.5);
    const hi = Math.ceil(Math.max(...allVals) + 0.5);

    const ctx = document.getElementById("chart-scatter");
    new Chart(ctx, {
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
            label: "OSRM route",
            data: rows.map((r) => ({ x: r.odometer_mi, y: r.osrm_mi })),
            borderColor: palette.series2,
            backgroundColor: palette.series2,
            showLine: false,
            pointRadius: 4,
            pointHoverRadius: 6,
            order: 1,
          },
          {
            label: "GPS trace",
            data: rows.map((r) => ({ x: r.odometer_mi, y: r.gps_mi })),
            borderColor: palette.series3,
            backgroundColor: palette.series3,
            showLine: false,
            pointRadius: 4,
            pointHoverRadius: 6,
            order: 2,
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

  async function renderDriftChart() {
    const rows = await fetchJSON("/api/metrics/drift");
    if (!rows || rows.length === 0) {
      showEmpty("chart-drift", "No drift data yet", "Shows up once a completed drive has both odometer and OSRM/GPS distance.");
      return;
    }
    renderLegend("legend-drift", [
      { label: "OSRMDrift", color: palette.series2 },
      { label: "GPSDrift", color: palette.series3 },
    ]);
    const ctx = document.getElementById("chart-drift");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          { label: "OSRMDrift", data: rows.map((r) => r.osrm_drift_pct), borderColor: palette.series2, backgroundColor: palette.series2, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25, spanGaps: true },
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

  async function renderSingleLineChart(canvasId, url, field, opts) {
    const rows = await fetchJSON(url);
    const values = (rows || []).filter((r) => r[field] !== null && r[field] !== undefined);
    if (values.length === 0) {
      showEmpty(canvasId, opts.emptyTitle, opts.emptyHint);
      return null;
    }
    const ctx = document.getElementById(canvasId);
    new Chart(ctx, {
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
    return rows;
  }

  async function renderBarChart(canvasId, url, field, opts) {
    const rows = await fetchJSON(url);
    const values = (rows || []).filter((r) => r[field] !== null && r[field] !== undefined);
    if (values.length === 0) {
      showEmpty(canvasId, opts.emptyTitle, opts.emptyHint);
      return;
    }
    const ctx = document.getElementById(canvasId);
    new Chart(ctx, {
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

  function renderDualSparkline(canvasId, rows, fieldA, colorA, fieldB, colorB) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !rows || rows.length < 2) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => r.date),
        datasets: [
          { data: rows.map((r) => r[fieldA]), borderColor: colorA, borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true },
          { data: rows.map((r) => r[fieldB]), borderColor: colorB, borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true },
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

  // Sets a KPI sub-row's value to the mean of every non-null `field` reading so far (all drives
  // to date, not a fixed trailing window), and its delta to their sample standard deviation —
  // how consistent that's been, not a change-vs-previous-drive.
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

  async function renderDriftKpi() {
    const rows = await fetchJSON("/api/metrics/drift");
    const tile = document.getElementById("kpi-drift");
    const fmtValue = (v) => `${v.toFixed(1)}%`;
    const fmtDelta = (v) => `±${v.toFixed(1)}pp`;
    setMeanStdevKpiValue(tile, ".drift-value-osrm", ".drift-delta-osrm", rows, "osrm_drift_pct", fmtValue, fmtDelta);
    setMeanStdevKpiValue(tile, ".drift-value-haversine", ".drift-delta-haversine", rows, "haversine_drift_pct", fmtValue, fmtDelta);
    renderDualSparkline(
      "kpi-drift-spark",
      (rows || []).slice(-12),
      "osrm_drift_pct",
      palette.series2,
      "haversine_drift_pct",
      palette.series3
    );
  }

  async function renderEfficiencyKpi() {
    const rows = await fetchJSON("/api/metrics/energy-efficiency");
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

  renderDriftKpi();
  renderEfficiencyKpi();
  renderBatteryHealthKpi();

  renderDistanceChart().then((rows) => renderScatterChart(rows));
  renderDriftChart();
  renderBarChart("chart-energy-used", "/api/metrics/energy-used", "kwh_used", {
    unit: "kWh",
    emptyTitle: "No energy data yet",
    emptyHint: "Needs completed drives and a car with a learned rated efficiency.",
  });
  renderSingleLineChart("chart-energy-efficiency", "/api/metrics/energy-efficiency", "wh_per_mi", {
    unit: "Wh/mi",
    emptyTitle: "No efficiency data yet",
    emptyHint: "Needs completed drives and a car with a learned rated efficiency.",
  });
  renderBarChart("chart-charging-energy", "/api/metrics/charging-energy", "kwh_added", {
    unit: "kWh",
    emptyTitle: "No charging sessions yet",
    emptyHint: "Shows up once TeslaMate records a completed charge.",
  });
})();
