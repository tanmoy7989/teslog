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

  function baseScales(extraY = {}) {
    return {
      x: {
        grid: { color: palette.gridline, drawTicks: false },
        border: { color: palette.baseline },
        ticks: { color: palette.textMuted, maxRotation: 0, autoSkip: true, font: { size: 11 } },
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
      swatch.className = "swatch";
      swatch.style.background = item.color;
      const label = document.createElement("span");
      label.textContent = item.label;
      span.appendChild(swatch);
      span.appendChild(label);
      el.appendChild(span);
    }
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
          { label: "Odometer", data: rows.map((r) => r.odometer_km), borderColor: palette.series1, backgroundColor: palette.series1, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
          { label: "OSRM route", data: rows.map((r) => r.osrm_km), borderColor: palette.series2, backgroundColor: palette.series2, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
          { label: "GPS trace", data: rows.map((r) => r.gps_km), borderColor: palette.series3, backgroundColor: palette.series3, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: baseScales({ title: { display: true, text: "km", color: palette.textMuted, font: { size: 11 } } }),
        plugins: { legend: { display: false }, tooltip: tooltipConfig() },
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
      { label: "OSRMDrift", color: palette.series1 },
      { label: "HaversineDrift", color: palette.series2 },
    ]);
    const ctx = document.getElementById("chart-drift");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => formatLabel(r.date)),
        datasets: [
          { label: "OSRMDrift", data: rows.map((r) => r.osrm_drift_pct), borderColor: palette.series1, backgroundColor: palette.series1, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25, spanGaps: true },
          { label: "HaversineDrift", data: rows.map((r) => r.haversine_drift_pct), borderColor: palette.series2, backgroundColor: palette.series2, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, tension: 0.25, spanGaps: true },
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

  function renderSparkline(canvasId, rows, field) {
    const values = (rows || []).filter((r) => r[field] !== null && r[field] !== undefined);
    if (values.length < 2) return;
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map((r) => r.date),
        datasets: [
          {
            data: rows.map((r) => r[field]),
            borderColor: palette.series1,
            backgroundColor: withAlpha(palette.series1, 0.1),
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3,
            fill: true,
          },
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

  async function renderDriftKpi() {
    const rows = await fetchJSON("/api/metrics/drift");
    const tile = document.getElementById("kpi-drift");
    const withOsrm = (rows || []).filter((r) => r.osrm_drift_pct !== null && r.osrm_drift_pct !== undefined);
    if (withOsrm.length === 0) {
      tile.querySelector(".value").textContent = "—";
      tile.querySelector(".delta").textContent = "";
      return;
    }
    const latest = withOsrm[withOsrm.length - 1].osrm_drift_pct;
    tile.querySelector(".value").textContent = `${latest.toFixed(1)}%`;
    if (withOsrm.length >= 2) {
      const prev = withOsrm[withOsrm.length - 2].osrm_drift_pct;
      const delta = latest - prev;
      const improving = Math.abs(latest) < Math.abs(prev);
      const deltaEl = tile.querySelector(".delta");
      deltaEl.textContent = `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}pp vs prev`;
      deltaEl.classList.add(improving ? "good" : "bad");
    }
    renderSparkline("kpi-drift-spark", withOsrm.slice(-12), "osrm_drift_pct");
  }

  async function renderEfficiencyKpi() {
    const rows = await fetchJSON("/api/metrics/energy-efficiency");
    const tile = document.getElementById("kpi-efficiency");
    if (!rows || rows.length === 0) {
      tile.querySelector(".value").textContent = "—";
      return;
    }
    const latest = rows[rows.length - 1].wh_per_km;
    tile.querySelector(".value").textContent = `${Math.round(latest)}`;
    renderSparkline("kpi-efficiency-spark", rows.slice(-12), "wh_per_km");
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

  renderDistanceChart();
  renderDriftChart();
  renderBarChart("chart-energy-used", "/api/metrics/energy-used", "kwh_used", {
    unit: "kWh",
    emptyTitle: "No energy data yet",
    emptyHint: "Needs completed drives and a car with a learned rated efficiency.",
  });
  renderSingleLineChart("chart-energy-efficiency", "/api/metrics/energy-efficiency", "wh_per_km", {
    unit: "Wh/km",
    emptyTitle: "No efficiency data yet",
    emptyHint: "Needs completed drives and a car with a learned rated efficiency.",
  });
  renderBarChart("chart-charging-energy", "/api/metrics/charging-energy", "kwh_added", {
    unit: "kWh",
    emptyTitle: "No charging sessions yet",
    emptyHint: "Shows up once TeslaMate records a completed charge.",
  });
  renderBarChart("chart-charging-cost", "/api/metrics/charging-cost", "cost", {
    unit: "cost",
    emptyTitle: "No charging cost data",
    emptyHint: "TeslaMate only tracks this if you've configured electricity pricing.",
  });
})();
