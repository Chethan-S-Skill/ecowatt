/**
 * EcoWatt AI – Frontend Dashboard Engine
 * Strict Vanilla JS, Inline SVG Charts, 5-Second Real-Time Telemetry Polling
 */

// Application State
const state = {
  currentBuilding: "",
  days: 28,
  horizon: "24h",
  authToken: localStorage.getItem("ecowatt_token") || null,
  currentUser: null,
  theme: localStorage.getItem("ecowatt_theme") || "light",
  isPolling: true,
  lastUpdated: null,
  summaryData: null,
  seriesData: null,
  forecastData: null,
  buildingsList: [],
  kpiPrevious: { total: 0, waste: 0, savings: 0, co2: 0, score: 100 }
};

// Utility: Clean Number Formatting (Never shows NaN, undefined, or Infinity)
function safeNum(val, defaultVal = 0) {
  if (val === undefined || val === null || isNaN(val) || !isFinite(val)) {
    return defaultVal;
  }
  return Number(val);
}

function formatNum(val, decimals = 0) {
  const n = safeNum(val, 0);
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Animated Count-Up
function animateValue(elementId, start, end, duration = 600, prefix = "", suffix = "", decimals = 0) {
  const el = document.getElementById(elementId);
  if (!el) return;
  start = safeNum(start, 0);
  end = safeNum(end, 0);
  if (Math.abs(start - end) < 0.01) {
    el.textContent = `${prefix}${formatNum(end, decimals)}${suffix}`;
    return;
  }
  const startTime = performance.now();
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease-out cubic
    const ease = 1 - Math.pow(1 - progress, 3);
    const current = start + (end - start) * ease;
    el.textContent = `${prefix}${formatNum(current, decimals)}${suffix}`;
    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      el.textContent = `${prefix}${formatNum(end, decimals)}${suffix}`;
    }
  }
  requestAnimationFrame(update);
}

// Theme Management
function initTheme() {
  document.documentElement.setAttribute("data-theme", state.theme);
  updateThemeIcon();
}

function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  localStorage.setItem("ecowatt_theme", state.theme);
  document.documentElement.setAttribute("data-theme", state.theme);
  updateThemeIcon();
  if (state.seriesData) renderSvgChart();
}

function updateThemeIcon() {
  const icon = document.getElementById("themeIcon");
  if (icon) icon.textContent = state.theme === "light" ? "🌙" : "☀️";
}

// Authentication Helpers
function getAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (state.authToken) {
    headers["Authorization"] = `Bearer ${state.authToken}`;
  }
  return headers;
}

async function checkAuthMe() {
  if (!state.authToken) {
    updateAuthBtnText();
    return;
  }
  try {
    const res = await fetch("/api/auth/me", { headers: getAuthHeaders() });
    if (res.ok) {
      state.currentUser = await res.json();
    } else {
      state.authToken = null;
      localStorage.removeItem("ecowatt_token");
      state.currentUser = null;
    }
  } catch (e) {
    console.warn("Auth check failed:", e);
  }
  updateAuthBtnText();
}

function updateAuthBtnText() {
  const textEl = document.getElementById("authBtnText");
  if (!textEl) return;
  if (state.currentUser) {
    textEl.textContent = `${state.currentUser.role.toUpperCase()} (${state.currentUser.email.split('@')[0]})`;
  } else {
    textEl.textContent = "Login";
  }
}

// -------------------------------------------------------------
// Core API Calls
// -------------------------------------------------------------

async function fetchBuildings() {
  try {
    const res = await fetch("/api/buildings");
    if (!res.ok) throw new Error("Failed to fetch buildings");
    const buildings = await res.json();
    state.buildingsList = buildings;
    populateBuildingFilter(buildings);
    renderBuildingCards(buildings);
  } catch (err) {
    console.error("Error fetching buildings:", err);
  }
}

function populateBuildingFilter(buildings) {
  const select = document.getElementById("buildingFilter");
  if (!select) return;
  const currentVal = select.value;
  select.innerHTML = '<option value="">Campus Total (All 7 Buildings)</option>';
  buildings.forEach(b => {
    const opt = document.createElement("option");
    opt.value = b.name;
    opt.textContent = `${b.name} (${b.type.toUpperCase()} - ${b.peak_kw}kW)`;
    select.appendChild(opt);
  });
  select.value = currentVal;
}

function renderBuildingCards(buildings) {
  const container = document.getElementById("buildingCardsList");
  if (!container) return;
  container.innerHTML = "";

  buildings.forEach(b => {
    const isSelected = (state.currentBuilding === b.name);
    const card = document.createElement("div");
    card.className = `building-item ${isSelected ? "active" : ""}`;
    card.setAttribute("tabindex", "0");
    card.onclick = () => selectBuilding(b.name);
    card.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") selectBuilding(b.name); };

    const score = safeNum(b.energy_score, 100);
    const scoreColor = score >= 80 ? "var(--brand-green)" : (score >= 60 ? "var(--severity-med)" : "var(--severity-high)");

    card.innerHTML = `
      <div class="building-info">
        <span class="building-name">${escapeHtml(b.name)}</span>
        <span class="building-type-badge">${escapeHtml(b.type)} ${b.is_24h ? "• 24h" : ""}</span>
      </div>
      <div class="building-metrics">
        <span class="metric-pill" style="color:var(--brand-teal);">${formatNum(b.current_kw, 1)} kW</span>
        <span class="metric-pill" style="color:${scoreColor};">${score}/100</span>
        ${b.anomaly_count > 0 ? `<span class="anomaly-badge high" style="font-size:10px;">${b.anomaly_count} alerts</span>` : ""}
      </div>
    `;
    container.appendChild(card);
  });
}

function selectBuilding(name) {
  state.currentBuilding = (state.currentBuilding === name) ? "" : name;
  const filter = document.getElementById("buildingFilter");
  if (filter) filter.value = state.currentBuilding;
  refreshAllData();
}

async function fetchSummary() {
  try {
    const params = new URLSearchParams({
      days: state.days,
      building: state.currentBuilding
    });
    const res = await fetch(`/api/summary?${params}`);
    if (!res.ok) throw new Error("Failed to load summary");
    const data = await res.json();
    state.summaryData = data;
    updateKpis(data);
  } catch (err) {
    console.error("Error fetching summary:", err);
  }
}

function updateKpis(data) {
  const total = safeNum(data.total_kwh);
  const waste = safeNum(data.wasted_kwh);
  const wastePct = safeNum(data.wasted_pct);
  const savings = safeNum(data.projected_savings_rupees_year);
  const co2 = safeNum(data.co2_reduction_tons_year);
  const baselineScore = safeNum(data.energy_score_baseline, 100);
  const optimizedScore = safeNum(data.energy_score_optimized, 100);

  // Animate Count-ups
  animateValue("kpiTotalKwh", state.kpiPrevious.total, total, 600, "", "", 0);
  animateValue("kpiWastedKwh", state.kpiPrevious.waste, waste, 600, "", "", 0);
  animateValue("kpiSavingsRupees", state.kpiPrevious.savings, savings, 600, "₹", "", 0);
  animateValue("kpiCo2Tons", state.kpiPrevious.co2, co2, 600, "", "", 2);
  animateValue("scoreValueText", state.kpiPrevious.score, baselineScore, 600, "", "", 1);
  animateValue("gaugeCenterNumber", state.kpiPrevious.score, baselineScore, 600, "", "", 0);

  document.getElementById("kpiWastePct").textContent = `${formatNum(wastePct, 1)}%`;
  document.getElementById("kpiOpenAnomalies").textContent = formatNum(data.open_anomalies_count);
  document.getElementById("kpiSubtextDays").textContent = `Over last ${state.days} days in ${escapeHtml(data.building_name)}`;

  // Applied vs potential savings text
  const appliedCount = safeNum(data.applied_recommendations_count, 0);
  const totalRecs = safeNum(data.total_recommendations_count, 0);
  document.getElementById("kpiAppliedSavingsText").textContent =
    appliedCount > 0 ? `${appliedCount} of ${totalRecs} what-if fixes applied` : `Preview: 0 of ${totalRecs} fixes applied`;

  // CO2 equivalent trees (approx 1 ton CO2 = 45 mature trees planted)
  const trees = Math.round(co2 * 45);
  document.getElementById("kpiTreesEquiv").textContent = `≈ ${formatNum(trees)} trees planted annually`;

  // Energy Score Ring SVG update
  updateScoreGauge(baselineScore, optimizedScore);

  state.kpiPrevious = { total, waste, savings, co2, score: baselineScore };
}

function updateScoreGauge(score, optimizedScore) {
  const circle = document.getElementById("gaugeValCircle");
  if (!circle) return;

  const radius = 40;
  const circumference = 2 * Math.PI * radius; // 251.327
  const offset = circumference - (score / 100.0) * circumference;
  circle.style.strokeDasharray = `${circumference}`;
  circle.style.strokeDashoffset = `${offset}`;

  // Gauge color based on performance
  if (score >= 80) {
    circle.style.stroke = "var(--brand-green)";
  } else if (score >= 60) {
    circle.style.stroke = "var(--severity-med)";
  } else {
    circle.style.stroke = "var(--severity-high)";
  }

  // Optimized score tag
  const tagEl = document.getElementById("scoreOptimizedTag");
  const diffEl = document.getElementById("scoreDiffText");
  if (tagEl && diffEl) {
    if (optimizedScore > score) {
      tagEl.textContent = `OPTIMIZED: ${optimizedScore}/100 (+${formatNum(optimizedScore - score, 1)})`;
      tagEl.style.display = "inline";
      diffEl.textContent = `Improves by +${formatNum(optimizedScore - score, 1)} pts when fixes applied`;
    } else {
      tagEl.textContent = `OPTIMIZED: ${score}/100`;
      diffEl.textContent = `Baseline campus efficiency rating`;
    }
  }
}

// -------------------------------------------------------------
// Main SVG Line Chart & Forecast Engine (Hand-Crafted SVG)
// -------------------------------------------------------------

async function fetchSeriesAndForecast() {
  try {
    const seriesParams = new URLSearchParams({
      days: Math.min(state.days, 7), // View last 7 days on chart
      building: state.currentBuilding
    });
    const forecastParams = new URLSearchParams({
      horizon: state.horizon,
      building: state.currentBuilding
    });

    const [seriesRes, forecastRes] = await Promise.all([
      fetch(`/api/series?${seriesParams}`),
      fetch(`/api/forecast?${forecastParams}`)
    ]);

    if (seriesRes.ok) state.seriesData = await seriesRes.json();
    if (forecastRes.ok) state.forecastData = await forecastRes.json();

    renderSvgChart();
  } catch (err) {
    console.error("Error fetching chart data:", err);
  }
}

function renderSvgChart() {
  const container = document.getElementById("svgChartContainer");
  const svg = document.getElementById("mainEnergySvg");
  if (!container || !svg || !state.seriesData) return;

  const points = state.seriesData.points || [];
  const forecastPoints = (state.forecastData && state.forecastData.points) ? state.forecastData.points : [];

  if (points.length === 0) return;

  const width = container.clientWidth || 800;
  const height = container.clientHeight || 360;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const padLeft = 50;
  const padRight = 30;
  const padTop = 20;
  const padBottom = 30;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  // Compute min/max load for scaling
  let maxKw = 0;
  points.forEach(p => {
    if (p.kwh > maxKw) maxKw = p.kwh;
  });
  forecastPoints.forEach(p => {
    if (p.upper_bound_kwh > maxKw) maxKw = p.upper_bound_kwh;
  });
  maxKw = Math.ceil(maxKw * 1.15) || 100;

  const totalPointsCount = points.length + forecastPoints.length;
  const xStep = plotW / Math.max(1, totalPointsCount - 1);

  // Generate coordinate arrays
  const coords = points.map((p, i) => {
    const x = padLeft + i * xStep;
    const y = padTop + plotH - (p.kwh / maxKw) * plotH;
    const optY = padTop + plotH - (p.optimized_kwh / maxKw) * plotH;
    return { x, y, optY, raw: p };
  });

  const forecastCoords = forecastPoints.map((p, i) => {
    const x = padLeft + (points.length + i) * xStep;
    const y = padTop + plotH - (p.predicted_kwh / maxKw) * plotH;
    const lowerY = padTop + plotH - (p.lower_bound_kwh / maxKw) * plotH;
    const upperY = padTop + plotH - (p.upper_bound_kwh / maxKw) * plotH;
    return { x, y, lowerY, upperY, raw: p };
  });

  // 1. Grid Lines & Axis
  const gridG = document.getElementById("svgGridLines");
  gridG.innerHTML = "";
  const numYLines = 4;
  for (let i = 0; i <= numYLines; i++) {
    const yVal = (maxKw / numYLines) * i;
    const yPos = padTop + plotH - (yVal / maxKw) * plotH;
    // Horizontal line
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", padLeft);
    line.setAttribute("y1", yPos);
    line.setAttribute("x2", width - padRight);
    line.setAttribute("y2", yPos);
    line.setAttribute("stroke", "var(--border-subtle)");
    line.setAttribute("stroke-width", "1");
    gridG.appendChild(line);

    // Y Axis label
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", padLeft - 8);
    text.setAttribute("y", yPos + 4);
    text.setAttribute("fill", "var(--text-subtle)");
    text.setAttribute("font-size", "10");
    text.setAttribute("text-anchor", "end");
    text.textContent = `${Math.round(yVal)}`;
    gridG.appendChild(text);
  }

  // 2. Forecast Shaded Zone
  const fZoneG = document.getElementById("svgForecastZone");
  fZoneG.innerHTML = "";
  if (forecastCoords.length > 0) {
    const fStartX = forecastCoords[0].x;
    const fEndX = forecastCoords[forecastCoords.length - 1].x;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", fStartX);
    rect.setAttribute("y", padTop);
    rect.setAttribute("width", fEndX - fStartX);
    rect.setAttribute("height", plotH);
    rect.setAttribute("fill", "var(--chart-forecast-zone)");
    fZoneG.appendChild(rect);

    // Divider line
    const divLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    divLine.setAttribute("x1", fStartX);
    divLine.setAttribute("y1", padTop);
    divLine.setAttribute("x2", fStartX);
    divLine.setAttribute("y2", padTop + plotH);
    divLine.setAttribute("stroke", "#2563eb");
    divLine.setAttribute("stroke-width", "1.5");
    divLine.setAttribute("stroke-dasharray", "4,3");
    fZoneG.appendChild(divLine);

    // Label
    const fLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    fLabel.setAttribute("x", fStartX + 8);
    fLabel.setAttribute("y", padTop + 16);
    fLabel.setAttribute("fill", "#2563eb");
    fLabel.setAttribute("font-size", "11");
    fLabel.setAttribute("font-weight", "bold");
    fLabel.textContent = `FORECAST ZONE (${state.horizon})`;
    fZoneG.appendChild(fLabel);
  }

  // 3. Main Path & Gradient Area
  let dLine = `M ${coords[0].x} ${coords[0].y}`;
  let dOpt = `M ${coords[0].x} ${coords[0].optY}`;
  for (let i = 1; i < coords.length; i++) {
    dLine += ` L ${coords[i].x} ${coords[i].y}`;
    dOpt += ` L ${coords[i].x} ${coords[i].optY}`;
  }

  const dArea = `${dLine} L ${coords[coords.length - 1].x} ${padTop + plotH} L ${coords[0].x} ${padTop + plotH} Z`;
  document.getElementById("svgAreaPath").setAttribute("d", dArea);
  document.getElementById("svgLoadLine").setAttribute("d", dLine);
  document.getElementById("svgOptimizedLine").setAttribute("d", dOpt);

  // 4. Forecast Path
  if (forecastCoords.length > 0) {
    let dFcast = `M ${coords[coords.length - 1].x} ${coords[coords.length - 1].y}`;
    forecastCoords.forEach(fc => {
      dFcast += ` L ${fc.x} ${fc.y}`;
    });
    document.getElementById("svgForecastLine").setAttribute("d", dFcast);
  } else {
    document.getElementById("svgForecastLine").setAttribute("d", "");
  }

  // 5. Anomaly Dots (Red dots for waste hours)
  const dotsG = document.getElementById("svgAnomalyDots");
  dotsG.innerHTML = "";
  coords.forEach(pt => {
    if (pt.raw.is_anomaly) {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", pt.x);
      circle.setAttribute("cy", pt.y);
      circle.setAttribute("r", "4");
      circle.setAttribute("fill", "var(--chart-anomaly-dot)");
      circle.setAttribute("stroke", "#ffffff");
      circle.setAttribute("stroke-width", "1.5");
      dotsG.appendChild(circle);
    }
  });

  // Attach mouse interaction for interactive crosshair & tooltip
  attachChartInteraction(container, coords, forecastCoords, width, height);
}

function attachChartInteraction(container, coords, forecastCoords, width, height) {
  const crosshair = document.getElementById("svgCrosshair");
  const tooltip = document.getElementById("chartTooltip");
  if (!crosshair || !tooltip) return;

  const allPoints = coords.concat(forecastCoords.map(fc => ({
    x: fc.x,
    y: fc.y,
    raw: {
      ts: fc.raw.ts,
      kwh: fc.raw.predicted_kwh,
      optimized_kwh: fc.raw.predicted_kwh,
      wasted_kwh: 0,
      isForecast: true
    }
  })));

  container.onmousemove = (e) => {
    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Find closest point along X
    let closest = allPoints[0];
    let minDist = Math.abs(mouseX - closest.x);
    for (let i = 1; i < allPoints.length; i++) {
      const dist = Math.abs(mouseX - allPoints[i].x);
      if (dist < minDist) {
        minDist = dist;
        closest = allPoints[i];
      }
    }

    if (!closest) return;

    crosshair.style.display = "block";
    crosshair.setAttribute("x1", closest.x);
    crosshair.setAttribute("y1", 20);
    crosshair.setAttribute("x2", closest.x);
    crosshair.setAttribute("y2", height - 30);

    // Update Tooltip
    tooltip.style.opacity = "1";
    tooltip.style.transform = `translate(${Math.min(mouseX + 12, width - 180)}px, ${Math.max(mouseY - 70, 10)}px)`;

    const raw = closest.raw;
    const dt = new Date(raw.ts);
    const dateStr = dt.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
    });

    document.getElementById("tooltipDate").textContent = `${dateStr} ${raw.isForecast ? "🔮 [Forecast]" : ""}`;
    document.getElementById("tooltipActual").textContent = `Meter Load: ${formatNum(raw.kwh, 1)} kW`;
    document.getElementById("tooltipOptimized").textContent = `Optimized: ${formatNum(raw.optimized_kwh, 1)} kW`;

    const wasteEl = document.getElementById("tooltipWasted");
    if (raw.wasted_kwh > 0) {
      wasteEl.style.display = "block";
      wasteEl.textContent = `Wasted: ${formatNum(raw.wasted_kwh, 1)} kW (${raw.anomaly_rule || 'waste'})`;
    } else {
      wasteEl.style.display = "none";
    }

    const mlEl = document.getElementById("tooltipMl");
    if (raw.ml_anomaly_score !== null && raw.ml_anomaly_score !== undefined) {
      mlEl.style.display = "block";
      mlEl.textContent = `ML Anomaly Score: ${formatNum(raw.ml_anomaly_score, 1)}%`;
    } else {
      mlEl.style.display = "none";
    }
  };

  container.onmouseleave = () => {
    crosshair.style.display = "none";
    tooltip.style.opacity = "0";
  };
}

// -------------------------------------------------------------
// 24x7 Heatmap Engine
// -------------------------------------------------------------

async function fetchHeatmap() {
  try {
    const params = new URLSearchParams({ building: state.currentBuilding });
    const res = await fetch(`/api/heatmap?${params}`);
    if (!res.ok) throw new Error("Failed to load heatmap");
    const data = await res.json();
    renderHeatmap(data.cells);
  } catch (err) {
    console.error("Error fetching heatmap:", err);
  }
}

function renderHeatmap(cells) {
  const grid = document.getElementById("heatmapGrid");
  if (!grid) return;
  grid.innerHTML = "";

  const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  // Find max load for color scaling
  let maxLoad = 0;
  cells.forEach(c => { if (c.avg_kwh > maxLoad) maxLoad = c.avg_kwh; });
  maxLoad = maxLoad || 100;

  // Render 7 rows (one per weekday)
  for (let w = 0; w < 7; w++) {
    // Day Label
    const label = document.createElement("div");
    label.className = "heatmap-day-label";
    label.textContent = dayNames[w];
    grid.appendChild(label);

    // 24 Hour Cells
    for (let h = 0; h < 24; h++) {
      const cellData = cells.find(c => c.weekday === w && c.hour === h) || { avg_kwh: 0, is_wasted_zone: false };
      const val = safeNum(cellData.avg_kwh, 0);
      const cell = document.createElement("div");
      cell.className = "heatmap-cell";

      // Color mapping: low load = teal/slate, high load = amber/red
      const ratio = Math.min(val / maxLoad, 1);
      if (cellData.is_wasted_zone) {
        cell.style.backgroundColor = `rgba(239, 68, 68, ${0.45 + 0.55 * ratio})`;
      } else {
        cell.style.backgroundColor = `rgba(13, 148, 136, ${0.15 + 0.85 * ratio})`;
      }

      cell.title = `${dayNames[w]} at ${h.toString().padStart(2, "0")}:00 -> Avg: ${formatNum(val, 1)} kWh ${cellData.is_wasted_zone ? '(Waste Zone)' : ''}`;
      grid.appendChild(cell);
    }
  }
}

// -------------------------------------------------------------
// Anomalies Alert Center
// -------------------------------------------------------------

async function fetchAnomalies() {
  try {
    const params = new URLSearchParams({
      building: state.currentBuilding,
      status: "open"
    });
    const res = await fetch(`/api/anomalies?${params}`);
    if (!res.ok) throw new Error("Failed to load anomalies");
    const anomalies = await res.json();
    renderAnomalies(anomalies);
  } catch (err) {
    console.error("Error fetching anomalies:", err);
  }
}

function renderAnomalies(anomalies) {
  const container = document.getElementById("anomaliesList");
  const badge = document.getElementById("anomaliesCountBadge");
  if (!container) return;
  if (badge) badge.textContent = anomalies.length;

  container.innerHTML = "";

  if (anomalies.length === 0) {
    container.innerHTML = `
      <div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px;">
        ✓ All systems optimal. No open energy waste anomalies detected in selected facility.
      </div>
    `;
    return;
  }

  anomalies.forEach(a => {
    const card = document.createElement("div");
    card.className = `anomaly-card ${a.severity.toLowerCase()}`;

    let evidenceObj = {};
    try { evidenceObj = JSON.parse(a.evidence); } catch (e) {}

    const startStr = new Date(a.start_ts).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
    });
    const endStr = new Date(a.end_ts).toLocaleString(undefined, {
      hour: "2-digit", minute: "2-digit"
    });

    card.innerHTML = `
      <div class="anomaly-header">
        <div>
          <strong style="font-size:14px;color:var(--text-main);">${escapeHtml(a.building_name)}</strong>
          <code style="font-size:11px;background:var(--border-subtle);padding:2px 6px;border-radius:4px;margin-left:6px;">${escapeHtml(a.rule)}</code>
        </div>
        <span class="anomaly-badge ${a.severity.toLowerCase()}">${a.severity}</span>
      </div>

      <div class="anomaly-details">
        <span>Period: <strong>${startStr} &rarr; ${endStr}</strong></span> &bull;
        <span>Wasted Load: <strong style="color:var(--severity-high);">${formatNum(a.wasted_kwh, 1)} kWh</strong></span>
        ${evidenceObj.duration_hours ? `(${evidenceObj.duration_hours} hrs)` : ""}
      </div>

      <div class="anomaly-actions">
        <button class="btn-ai-explain" onclick="triggerAiExplanation(${a.id})">
          <span>✨ Explain with AI</span>
        </button>
        <button class="btn-resolve" onclick="resolveAnomaly(${a.id})">
          Resolve
        </button>
      </div>
    `;
    container.appendChild(card);
  });
}

async function resolveAnomaly(anomalyId) {
  try {
    const res = await fetch(`/api/anomalies/${anomalyId}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify({ status: "resolved" })
    });
    if (!res.ok) {
      alert("Failed to resolve anomaly.");
      return;
    }
    refreshAllData();
  } catch (err) {
    console.error("Resolve anomaly error:", err);
  }
}

// -------------------------------------------------------------
// Recommendations Engine & What-If Toggles
// -------------------------------------------------------------

async function fetchRecommendations() {
  try {
    const params = new URLSearchParams({ building: state.currentBuilding });
    const res = await fetch(`/api/recommendations?${params}`);
    if (!res.ok) throw new Error("Failed to load recommendations");
    const recs = await res.json();
    renderRecommendations(recs);
  } catch (err) {
    console.error("Error fetching recommendations:", err);
  }
}

function renderRecommendations(recs) {
  const container = document.getElementById("recommendationsList");
  if (!container) return;
  container.innerHTML = "";

  if (recs.length === 0) {
    container.innerHTML = `
      <div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px;">
        No active recommendations for selected filter. Run analysis or select another facility.
      </div>
    `;
    return;
  }

  recs.forEach(r => {
    const item = document.createElement("div");
    item.className = "recommendation-item";

    item.innerHTML = `
      <div class="rec-content">
        <div class="rec-title">${escapeHtml(r.building_name)}: ${escapeHtml(r.fix_text)}</div>
        <div class="rec-impact">
          <span>Capture Rate: <strong>${Math.round(r.capture_rate * 100)}%</strong></span>
          <span>Weekly: <strong>${formatNum(r.kwh_week, 0)} kWh/wk</strong></span>
          <span>Annual Savings: <strong>₹${formatNum(r.rupees_year, 0)}</strong></span>
          <span>CO₂ Avoided: <strong style="color:var(--brand-blue);">${formatNum(r.co2_t_year, 2)} t/yr</strong></span>
        </div>
      </div>

      <label class="ios-switch" title="Toggle applied intervention">
        <input type="checkbox" ${r.applied ? "checked" : ""} onchange="toggleRecommendationApplied(${r.id}, this.checked)">
        <span class="ios-slider"></span>
      </label>
    `;
    container.appendChild(item);
  });
}

async function toggleRecommendationApplied(recId, isApplied) {
  try {
    const res = await fetch(`/api/recommendations/${recId}`, {
      method: "PATCH",
      headers: getAuthHeaders(),
      body: JSON.stringify({ applied: isApplied })
    });
    if (!res.ok) {
      alert("Failed to update recommendation.");
      return;
    }
    // Re-fetch summary and chart immediately to reflect the what-if simulation!
    fetchSummary();
    fetchSeriesAndForecast();
  } catch (err) {
    console.error("Error toggling recommendation:", err);
  }
}

// -------------------------------------------------------------
// Weather Panel & Open-Meteo Integration
// -------------------------------------------------------------

async function fetchWeather() {
  try {
    const params = new URLSearchParams({
      days: 7,
      building: state.currentBuilding
    });
    const res = await fetch(`/api/weather?${params}`);
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("tempBadge").textContent = `Temp: ${formatNum(data.current_temp_c, 1)}°C`;
    document.getElementById("weatherMsgText").textContent = data.correlation_message;

    const corrBadge = document.getElementById("weatherCorrBadge");
    if (data.weather_correlation_pct !== null && data.weather_correlation_pct !== undefined) {
      corrBadge.textContent = `Weather Correlation: ${formatNum(data.weather_correlation_pct, 1)}%`;
      corrBadge.style.display = "inline-block";
    } else {
      corrBadge.textContent = "Correlation: Pending 14d sync";
    }
  } catch (err) {
    console.warn("Weather fetch error:", err);
  }
}

// -------------------------------------------------------------
// AI Explanation Modal Popup (POST /api/explain/{id})
// -------------------------------------------------------------

async function triggerAiExplanation(anomalyId) {
  const modal = document.getElementById("aiModal");
  const sub = document.getElementById("aiModalSubtitle");
  const exp = document.getElementById("aiModalExplanation");
  const fix = document.getElementById("aiModalFix");
  const src = document.getElementById("aiModalSource");

  modal.classList.add("active");
  sub.textContent = `Analyzing anomaly #${anomalyId}...`;
  exp.textContent = "Querying intelligence model (Gemini / Kimi / Claude / deterministic fallback)...";
  fix.textContent = "...";
  src.textContent = "Model: Requesting...";

  try {
    const res = await fetch(`/api/explain/${anomalyId}`, { method: "POST" });
    if (!res.ok) throw new Error("Explanation request failed");
    const data = await res.json();

    sub.textContent = `${data.building_name} (${data.rule}) &bull; ${formatNum(data.wasted_kwh, 1)} kWh Wasted`;
    exp.textContent = data.explanation;
    fix.textContent = data.recommended_action;
    src.textContent = `Provider: ${data.source.toUpperCase()}`;
  } catch (err) {
    exp.textContent = "Failed to load explanation. The server fallback template is engaged.";
    src.textContent = "Provider: OFFLINE TEMPLATE";
  }
}

function closeAiModal() {
  document.getElementById("aiModal").classList.remove("active");
}

// -------------------------------------------------------------
// CSV Ingestion (Drag-and-Drop)
// -------------------------------------------------------------

function initCsvDropzone() {
  const dropzone = document.getElementById("csvDropzone");
  const fileInput = document.getElementById("csvFileInput");
  if (!dropzone || !fileInput) return;

  dropzone.onclick = () => fileInput.click();

  dropzone.ondragover = (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  };

  dropzone.ondragleave = () => {
    dropzone.classList.remove("dragover");
  };

  dropzone.ondrop = (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleCsvUpload(e.dataTransfer.files[0]);
    }
  };

  fileInput.onchange = () => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleCsvUpload(fileInput.files[0]);
    }
  };
}

async function handleCsvUpload(file) {
  const summaryBox = document.getElementById("uploadSummaryBox");
  if (!summaryBox) return;

  summaryBox.style.display = "block";
  summaryBox.innerHTML = `<strong>Uploading & validating ${escapeHtml(file.name)} (${Math.round(file.size / 1024)} KB)...</strong>`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload-csv", {
      method: "POST",
      headers: state.authToken ? { "Authorization": `Bearer ${state.authToken}` } : {},
      body: formData
    });

    const data = await res.json();
    if (!res.ok) {
      summaryBox.innerHTML = `<span style="color:var(--severity-high);">❌ Upload failed: ${escapeHtml(data.detail || "Server error")}</span>`;
      return;
    }

    let reasonsHtml = "";
    if (data.skipped_reasons && data.skipped_reasons.length > 0) {
      reasonsHtml = `<ul style="margin-top:6px;padding-left:18px;font-size:12px;color:var(--text-muted);">
        ${data.skipped_reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")}
      </ul>`;
    }

    summaryBox.innerHTML = `
      <div style="color:var(--brand-green);font-weight:700;">
        ✓ Ingestion Complete!
      </div>
      <div style="margin-top:4px;">
        Processed: <strong>${data.total_rows}</strong> rows &bull;
        Loaded: <strong style="color:var(--brand-green);">${data.rows_loaded}</strong> &bull;
        Skipped: <strong style="color:var(--severity-high);">${data.rows_skipped}</strong>
      </div>
      ${reasonsHtml}
    `;

    // Refresh entire dashboard to reflect new telemetry!
    refreshAllData();
  } catch (err) {
    summaryBox.innerHTML = `<span style="color:var(--severity-high);">❌ Error communicating with EcoWatt API: ${err.message}</span>`;
  }
}

// -------------------------------------------------------------
// Authentication Modal & Handler
// -------------------------------------------------------------

function initAuthHandlers() {
  const authBtn = document.getElementById("authBtn");
  const modal = document.getElementById("loginModal");
  const closeBtn = document.getElementById("closeLoginModalBtn");
  const form = document.getElementById("loginForm");
  const errBox = document.getElementById("loginErrorMsg");

  if (!authBtn || !modal) return;

  authBtn.onclick = () => {
    if (state.currentUser) {
      if (confirm(`Logged in as ${state.currentUser.email}. Logout now?`)) {
        state.authToken = null;
        localStorage.removeItem("ecowatt_token");
        state.currentUser = null;
        updateAuthBtnText();
      }
    } else {
      modal.classList.add("active");
    }
  };

  closeBtn.onclick = () => modal.classList.remove("active");

  form.onsubmit = async (e) => {
    e.preventDefault();
    errBox.style.display = "none";
    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (!res.ok) {
        errBox.textContent = data.detail || "Authentication failed.";
        errBox.style.display = "block";
        return;
      }
      state.authToken = data.access_token;
      localStorage.setItem("ecowatt_token", data.access_token);
      state.currentUser = data.user;
      updateAuthBtnText();
      modal.classList.remove("active");
    } catch (err) {
      errBox.textContent = "Server unreachable.";
      errBox.style.display = "block";
    }
  };
}

// -------------------------------------------------------------
// Global Orchestrator & 5-Second Real-Time Polling
// -------------------------------------------------------------

async function refreshAllData() {
  const liveDot = document.getElementById("liveDot");
  const liveText = document.getElementById("liveStatusText");

  try {
    await Promise.all([
      fetchBuildings(),
      fetchSummary(),
      fetchSeriesAndForecast(),
      fetchHeatmap(),
      fetchAnomalies(),
      fetchRecommendations(),
      fetchWeather()
    ]);

    state.lastUpdated = new Date();
    document.getElementById("lastUpdatedText").textContent =
      `Updated: ${state.lastUpdated.toLocaleTimeString()}`;

    if (liveDot) {
      liveDot.classList.remove("offline");
      liveText.textContent = "Live Feed";
    }
  } catch (err) {
    console.warn("Poll refresh issue:", err);
    if (liveDot) {
      liveDot.classList.add("offline");
      liveText.textContent = "Offline";
    }
  }
}

// Initialization on DOM Ready
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  document.getElementById("themeToggleBtn").onclick = toggleTheme;

  // Filter change listeners
  document.getElementById("buildingFilter").onchange = (e) => {
    state.currentBuilding = e.target.value;
    refreshAllData();
  };

  document.getElementById("daysFilter").onchange = (e) => {
    state.days = parseInt(e.target.value, 10);
    refreshAllData();
  };

  document.getElementById("forecastHorizon").onchange = (e) => {
    state.horizon = e.target.value;
    fetchSeriesAndForecast();
  };

  document.getElementById("manualRefreshBtn").onclick = () => {
    refreshAllData();
  };

  // Modal close buttons
  document.getElementById("closeAiModalBtn").onclick = closeAiModal;
  document.getElementById("aiModalDismissBtn").onclick = closeAiModal;

  initCsvDropzone();
  initAuthHandlers();
  await checkAuthMe();

  // Initial load
  await refreshAllData();

  // Window resize re-renders hand-crafted SVG chart responsively
  window.addEventListener("resize", () => {
    if (state.seriesData) renderSvgChart();
  });

  // Auto-refresh every 5 seconds (syncs with live simulator.py!)
  setInterval(() => {
    if (state.isPolling) {
      refreshAllData();
    }
  }, 5000);
});
