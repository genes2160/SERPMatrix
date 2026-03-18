// js/ui.js
"use strict";

// ─── Step constants ───────────────────────────────────────────────────────
const STEP_ORDER = ["FETCH_CLIENT", "CLASSIFY", "KEYWORDS", "SERP", "COMPETITORS", "ANALYZE", "FINALIZE"];
const STEP_ICONS = { FETCH_CLIENT: "⬇", CLASSIFY: "◈", KEYWORDS: "#", SERP: "🔍", COMPETITORS: "⊞", ANALYZE: "★", FINALIZE: "✓" };

// ─── Tiny chart helpers ───────────────────────────────────────────────────
const Charts = {
  hbar(items, { valueKey = "value", labelKey = "label", color = "#6366f1", max = null, suffix = "" } = {}) {
    if (!items.length) return `<div class="chart-empty">No data yet</div>`;
    const peak = max || Math.max(...items.map(d => d[valueKey] || 0), 1);
    return items.map(d => {
      const pct = Math.round(((d[valueKey] || 0) / peak) * 100);
      return `<div class="hbar-row">
        <div class="hbar-label">${d[labelKey] || "—"}</div>
        <div class="hbar-track"><div class="hbar-fill" style="width:${pct}%;background:${color}"></div></div>
        <div class="hbar-val">${d[valueKey] || 0}${suffix}</div>
      </div>`;
    }).join("");
  },

  donut(segments, { size = 88, stroke = 10, centerLabel = "", centerSub = "" } = {}) {
    const r = (size / 2) - stroke / 2, circ = 2 * Math.PI * r;
    const total = segments.reduce((s, x) => s + (x.value || 0), 0) || 1;
    let offset = 0;
    const circles = segments.filter(s => s.value).map(s => {
      const dash = (s.value / total) * circ;
      const el = `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${stroke}"
        stroke-dasharray="${dash.toFixed(2)} ${circ.toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" stroke-linecap="round"/>`;
      offset += dash; return el;
    }).join("");
    return `<div style="width:${size}px;height:${size}px;position:relative;flex-shrink:0;">
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#f1f5f9" stroke-width="${stroke}"/>
        ${circles}
      </svg>
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;">
        <div style="font-size:17px;font-weight:800;">${centerLabel}</div>
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;">${centerSub}</div>
      </div>
    </div>`;
  },
};

// ─── Main UI ──────────────────────────────────────────────────────────────
const UI = {

  _fmtDate(v) {
    if (!v) return "—";
    try { return new Date(v).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }); }
    catch { return "—"; }
  },
  _durationMs(start, end) {
    if (!start) return null;
    return (end ? new Date(end) : new Date()) - new Date(start);
  },
  _durStr(start, end) {
    const ms = UI._durationMs(start, end);
    if (ms === null) return null;
    if (ms < 1000) return ms + "ms";
    if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
    return Math.floor(ms / 60000) + "m " + Math.floor((ms % 60000) / 1000) + "s";
  },
  _escape(s) {
    return String(s || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  },
  _statusBadge(s) {
    const st = (s || "queued").toLowerCase();
    return `<span class="status-badge status-${st}">${st}</span>`;
  },
  _priorityColor(p) {
    return { high: "#ef4444", med: "#f59e0b", low: "#6b7280" }[p] || "#6b7280";
  },
  _shortUrl(url) {
    return (url || "").replace(/https?:\/\/(www\.)?/, "").replace(/\/$/, "").slice(0, 28);
  },

  // ── OVERVIEW ─────────────────────────────────────────────────────────────
  async renderOverview() {
    document.getElementById("pageTitle").innerText = "Overview";
    document.getElementById("metricsBar").innerHTML = "";

    document.getElementById("content").innerHTML = `
      <!-- Hero Banner -->
      <div class="overview-hero">
        <div class="overview-hero-left">
          <div class="overview-eyebrow">SEO Audit Engine</div>
          <h1 class="overview-hero-title">Track. Audit.<br><span class="hero-accent">Optimise.</span></h1>
          <p class="overview-hero-sub">Full-pipeline audits — keywords, SERP, competitors &amp; AI recommendations, all in one place.</p>
          <button class="hero-cta" onclick="UI.openAddSiteModal()">+ Add New Site</button>
        </div>
        <div class="overview-hero-right">
          <div class="hero-stat"><div class="hero-stat-val" id="hst-sites">—</div><div class="hero-stat-lbl">Sites</div></div>
          <div class="hero-stat"><div class="hero-stat-val" id="hst-runs">—</div><div class="hero-stat-lbl">Runs</div></div>
          <div class="hero-stat"><div class="hero-stat-val" id="hst-rate">—</div><div class="hero-stat-lbl">Success Rate</div></div>
          <div class="hero-stat"><div class="hero-stat-val" id="hst-vis">—</div><div class="hero-stat-lbl">Avg Visibility</div></div>
        </div>
      </div>

      <!-- 4-chart quad -->
      <div class="charts-quad">
        <div class="chart-card"><div class="chart-card-title">Recs by Type</div><div id="cb-recs"><div class="chart-empty">Loading…</div></div></div>
        <div class="chart-card"><div class="chart-card-title">Runs per Site</div><div id="cb-kws"><div class="chart-empty">Loading…</div></div></div>
        <div class="chart-card"><div class="chart-card-title">Step Failure Rate</div><div id="cb-fails"><div class="chart-empty">Loading…</div></div></div>
        <div class="chart-card"><div class="chart-card-title">Avg Run Duration</div><div id="cb-dur"><div class="chart-empty">Loading…</div></div></div>
      </div>

      <!-- Donut + Activity -->
      <div class="overview-mid-grid">
        <div class="section-card">
          <div class="section-title" style="margin-bottom:16px;">Run Distribution</div>
          <div id="donutRow"><div class="chart-empty">Loading…</div></div>
        </div>
        <div class="section-card">
          <div class="section-title" style="margin-bottom:16px;">Recent Activity</div>
          <div class="activity-list" id="activityList"><div class="chart-empty">Loading…</div></div>
        </div>
      </div>

      <!-- Sites table -->
      <div class="section-card" style="margin-top:16px;">
        <div class="section-head">
          <h3 class="section-title">Your Sites</h3>
          <button class="primary-btn" onclick="UI.openAddSiteModal()">+ Add Site</button>
        </div>
        <table class="data-table">
          <thead><tr><th>URL</th><th>Geo</th><th>Device</th><th>Latest Run</th><th>Status</th><th></th></tr></thead>
          <tbody id="overviewSitesTbody"><tr><td colspan="6" class="tbl-loading">Loading…</td></tr></tbody>
        </table>
      </div>`;

    let overview = {}, sites = [];
    try {
      [overview, sites] = await Promise.all([
        API.authFetch("/dashboard/overview").catch(() => ({})),
        API.getSites().catch(() => []),
      ]);
    } catch { }

    const total = overview.total_runs || 0;
    const rate = total ? Math.round((overview.success_runs / total) * 100) : 0;

    document.getElementById("hst-sites").textContent = overview.total_sites ?? sites.length;
    document.getElementById("hst-runs").textContent = total || "—";
    document.getElementById("hst-rate").textContent = rate + "%";
    document.getElementById("hst-vis").textContent =
      overview.avg_visibility_score != null
        ? (overview.avg_visibility_score * 100).toFixed(1) + "%"
        : "—";

    const allRuns = sites.flatMap(s => s.runs || []);

    // Chart: Runs per site
    const kw2 = sites.map(s => ({
      label: UI._shortUrl(s.url),
      value: (s.runs || []).length,
    })).filter(d => d.value);
    document.getElementById("cb-kws").innerHTML = Charts.hbar(kw2, { color: "#6366f1", suffix: " runs" }) || `<div class="chart-empty">No data</div>`;

    // Chart: Avg run duration
    const durData = sites.map(s => {
      const done = (s.runs || []).filter(r => r.started_at && r.finished_at);
      const avg = done.length ? done.reduce((s, r) => s + (new Date(r.finished_at) - new Date(r.started_at)), 0) / done.length : 0;
      return { label: UI._shortUrl(s.url), value: Math.round(avg / 1000) };
    }).filter(d => d.value);
    document.getElementById("cb-dur").innerHTML = durData.length
      ? Charts.hbar(durData, { color: "#f59e0b", suffix: "s" })
      : `<div class="chart-empty">Complete a run first</div>`;

    // Async charts (need dashboard calls)
    UI._buildRecsChart(sites);
    UI._buildFailureChart(sites);

    // Donut
    const seg = [
      { label: "Success", value: overview.success_runs || 0, color: "#10b981" },
      { label: "Running", value: overview.running_runs || 0, color: "#3b82f6" },
      { label: "Failed", value: overview.failed_runs || 0, color: "#ef4444" },
      { label: "Queued", value: overview.queued_runs || 0, color: "#94a3b8" },
    ].filter(s => s.value);
    document.getElementById("donutRow").innerHTML = `
      <div style="display:flex;align-items:center;gap:24px;">
        ${Charts.donut(seg, { centerLabel: total, centerSub: "runs" })}
        <div style="display:flex;flex-direction:column;gap:8px;">
          ${seg.map(s => `<div style="display:flex;align-items:center;gap:8px;font-size:12px;">
            <span style="width:10px;height:10px;border-radius:3px;background:${s.color};display:inline-block;flex-shrink:0;"></span>
            <span style="color:#64748b;">${s.label}</span>
            <strong style="margin-left:4px;">${s.value}</strong>
          </div>`).join("")}
        </div>
      </div>`;

    // Activity feed
    const dotC = { success: "#10b981", running: "#3b82f6", failed: "#ef4444", queued: "#94a3b8" };
    document.getElementById("activityList").innerHTML =
      [...allRuns].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 7)
        .map(r => {
          const site = sites.find(s => (s.runs || []).find(x => x.id === r.id));
          return `<div class="activity-item">
          <div class="activity-dot" style="background:${dotC[r.status] || "#94a3b8"}"></div>
          <div class="activity-content">
            <div class="activity-title">${UI._escape(UI._shortUrl(site?.url || "Unknown"))}</div>
            <div class="activity-meta">${r.status.toUpperCase()} · ${UI._fmtDate(r.created_at)}</div>
          </div>${UI._statusBadge(r.status)}
        </div>`;
        }).join("") || `<div class="chart-empty">No runs yet</div>`;

    // Sites table
    document.getElementById("overviewSitesTbody").innerHTML = sites.map(s => {
      const latest = (s.runs || [])[0];
      return `<tr>
        <td class="mono">${UI._escape(s.url)}</td>
        <td>${s.geo}</td><td>${s.device}</td>
        <td class="mono" style="font-size:11px;">${UI._fmtDate(latest?.created_at)}</td>
        <td>${UI._statusBadge(latest?.status || "none")}</td>
        <td style="display:flex;gap:6px;">
          <button class="small-success-btn" onclick="UI.startRun('${s.id}')">▶ Run</button>
          ${latest ? `<button class="small-success-btn black-spaced" onclick="UI.renderRunDashboard('${latest.id}')">View</button>` : ""}
        </td>
      </tr>`;
    }).join("") || `<tr><td colspan="6" class="tbl-loading">No sites yet — add your first one!</td></tr>`;
  },

  async _buildRecsChart(sites) {
    const typeCounts = {};
    await Promise.allSettled(sites.map(async s => {
      const latest = (s.runs || []).find(r => r.status === "success");
      if (!latest) return;
      try {
        const d = await API.getRunDashboard(latest.id);
        (d.ai?.recommendations || []).forEach(r => { typeCounts[r.action_type] = (typeCounts[r.action_type] || 0) + 1; });
      } catch { }
    }));
    const items = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).slice(0, 6)
      .map(([k, v]) => ({ label: k.replace(/_/g, " "), value: v }));
    document.getElementById("cb-recs").innerHTML = items.length
      ? Charts.hbar(items, { color: "#10b981" })
      : `<div class="chart-empty">Run audits first</div>`;
  },

  async _buildFailureChart(sites) {
    const fails = {}, totals = {};
    STEP_ORDER.forEach(s => { fails[s] = 0; totals[s] = 0; });
    const sample = sites.flatMap(s => s.runs || []).slice(0, 10);
    await Promise.allSettled(sample.map(async r => {
      try {
        const d = await API.getRunDashboard(r.id);
        (d.steps || []).forEach(s => {
          const n = s.step_name;
          if (!totals[n]) totals[n] = 0;
          if (!fails[n]) fails[n] = 0;
          totals[n]++;
          if (s.status === "failed") fails[n]++;
        });
      } catch { }
    }));
    const items = STEP_ORDER.filter(n => totals[n] > 0)
      .map(n => ({ label: n.replace("_", " "), value: Math.round((fails[n] / totals[n]) * 100) }));
    document.getElementById("cb-fails").innerHTML = items.length
      ? Charts.hbar(items, { color: "#ef4444", suffix: "%" })
      : `<div class="chart-empty">No step data yet</div>`;
  },

  // ── SITES ─────────────────────────────────────────────────────────────────
  async renderSites() {
    document.getElementById("pageTitle").innerText = "Sites";
    document.getElementById("metricsBar").innerHTML = "";
    try {
      const sites = await API.getSites();
      document.getElementById("metricsBar").innerHTML = `
        <div class="metric-card metric-green"><p>Total Sites</p><h3>${sites.length}</h3><div class="metric-sub">Tracked domains</div></div>`;
      let html = `<div class="section-card"><div class="section-head">
        <h3 class="section-title">Client Sites</h3>
        <button class="primary-btn" onclick="UI.openAddSiteModal()">+ Add Site</button>
      </div>
      <table class="data-table"><thead><tr><th>URL</th><th>Geo</th><th>Lang</th><th>Device</th><th>Runs</th><th>Created</th><th>Actions</th></tr></thead><tbody>`;
      sites.forEach(s => {
        const runs = s.runs || [], latest = runs[0];
        html += `<tr>
          <td class="mono">${UI._escape(s.url)}</td>
          <td>${s.geo}</td><td>${s.language}</td><td>${s.device}</td>
          <td><span class="runs-count">${runs.length}</span></td>
          <td class="mono" style="font-size:11px;">${UI._fmtDate(s.created_at)}</td>
          <td style="display:flex;gap:6px;">
            <button class="small-success-btn" onclick="UI.startRun('${s.id}')">▶ Run</button>
            ${latest ? `<button class="small-success-btn black-spaced" onclick="UI.renderRunDashboard('${latest.id}')">View</button>` : ""}
          </td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
      document.getElementById("content").innerHTML = html;
    } catch (e) { Toast.error(e.message || "Failed to load sites"); }
  },

  openAddSiteModal() {
    document.getElementById("modalContainer").innerHTML = `
      <div class="modal" onclick="UI.closeModalOnBackdrop(event)">
        <div class="modal-content">
          <h3>Add New Site</h3>
          <label class="form-label">URL</label>
          <input id="newSiteUrl" placeholder="https://example.com"/>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
            <div><label class="form-label">Geo</label><input id="newSiteGeo" placeholder="GH" value="GH" style="margin-bottom:0"/></div>
            <div><label class="form-label">Language</label><input id="newSiteLang" placeholder="en" value="en" style="margin-bottom:0"/></div>
            <div><label class="form-label">Device</label>
              <select id="newSiteDevice" style="width:100%;padding:10px 12px;border:1px solid #e5e7eb;border-radius:6px;font-size:14px;">
                <option value="desktop">Desktop</option><option value="mobile">Mobile</option>
              </select>
            </div>
          </div>
          <div class="modal-actions">
            <button class="primary-btn" onclick="UI.submitNewSite(this)">Save</button>
            <button class="btn-secondary" onclick="UI.closeModal()">Cancel</button>
          </div>
        </div>
      </div>`;
    setTimeout(() => document.getElementById("newSiteUrl")?.focus(), 0);
  },

  closeModalOnBackdrop(e) { if (e.target.classList.contains("modal")) UI.closeModal(); },
  closeModal() { document.getElementById("modalContainer").innerHTML = ""; },

  async submitNewSite(btn) {
    const url = document.getElementById("newSiteUrl").value.trim();
    if (!url) return Toast.error("URL is required");
    setButtonState(btn, false, "Saving...");
    try {
      await API.authFetch("/sites", {
        method: "POST", body: JSON.stringify({
          url,
          geo: document.getElementById("newSiteGeo").value || "GH",
          language: document.getElementById("newSiteLang").value || "en",
          device: document.getElementById("newSiteDevice").value || "desktop",
        })
      });
      Toast.success("Site added");
      UI.closeModal();
      UI.renderSites();
    } catch (e) { Toast.error(e.message || "Failed to add site"); }
    finally { setButtonState(btn, true, "Save"); }
  },

  async startRun(siteId) {
    try {
      const run = await API.createRun(siteId);
      Toast.success("Audit started!");
      UI.renderRunDashboard(run.id);
    } catch (e) { Toast.error(e.message || "Failed to start run"); }
  },

  // ── HEALTH ────────────────────────────────────────────────────────────────
  async renderHealth() {
    document.getElementById("pageTitle").innerText = "Health";
    document.getElementById("metricsBar").innerHTML = "";
    try {
      const health = await API.getHealth();
      const svc = health.services || {};
      const rows = Object.entries(svc).map(([k, v]) => {
        const ok = v === "ok" || v === "healthy";
        return `<div class="activity-item">
          <div class="activity-dot" style="background:${ok ? "#10b981" : "#ef4444"}"></div>
          <div class="activity-content"><div class="activity-title">${k}</div><div class="activity-meta">${v}</div></div>
          ${UI._statusBadge(ok ? "success" : "failed")}
        </div>`;
      }).join("");
      document.getElementById("content").innerHTML = `
        <div class="overview-mid-grid">
          <div class="section-card"><div class="section-title" style="margin-bottom:14px;">Services</div>
            <div class="activity-list">${rows || '<div class="chart-empty">No data</div>'}</div>
          </div>
        </div>`;
    } catch { Toast.error("Health check failed"); }
  },

  // ── RUN HISTORY ───────────────────────────────────────────────────────────
  async renderRunHistory() {
    document.getElementById("pageTitle").innerText = "Run History";
    document.getElementById("metricsBar").innerHTML = "";
    document.getElementById("content").innerHTML = `<div class="section-card"><div class="tbl-loading">Loading…</div></div>`;
    try {
      const sites = await API.getSites();
      const allRuns = sites.flatMap(s => (s.runs || []).map(r => ({ ...r, site_url: s.url, site_id: s.id })))
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      const counts = { success: 0, running: 0, failed: 0, queued: 0 };
      allRuns.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; });
      document.getElementById("metricsBar").innerHTML = `
        <div class="metric-card metric-green"><p>Total Runs</p><h3>${allRuns.length}</h3><div class="metric-sub">All time</div></div>
        <div class="metric-card metric-blue"><p>Running</p><h3>${counts.running}</h3><div class="metric-sub">Active now</div></div>
        <div class="metric-card metric-amber"><p>Failed</p><h3>${counts.failed}</h3><div class="metric-sub">Need attention</div></div>
        <div class="metric-card metric-purple"><p>Success Rate</p><h3>${allRuns.length ? Math.round(counts.success / allRuns.length * 100) : 0}%</h3><div class="metric-sub">Completion</div></div>`;
      window.__RUN_HISTORY_DATA__ = allRuns;
      document.getElementById("content").innerHTML = `
        <div class="section-card">
          <div class="section-head">
            <h3 class="section-title">All Runs</h3>
            <div class="filter-tabs" id="runFilterTabs">
              ${["all", "success", "running", "failed", "queued"].map(f =>
        `<button class="filter-tab ${f === "all" ? "active" : ""}" onclick="UI._setRunFilter('${f}')">${f}</button>`
      ).join("")}
            </div>
          </div>
          <table class="data-table">
            <thead><tr><th>Run ID</th><th>Site</th><th>Status</th><th>Created</th><th>Started</th><th>Duration</th><th></th></tr></thead>
            <tbody id="runHistoryTbody">${UI._runRows(allRuns)}</tbody>
          </table>
        </div>`;
    } catch (e) { Toast.error(e.message || "Failed to load run history"); }
  },

  _runRows(runs) {
    return runs.map(r => `<tr onclick="UI.renderRunDashboard('${r.id}')" style="cursor:pointer;">
      <td class="mono" style="font-size:11px;">${r.id.slice(0, 8)}…</td>
      <td class="mono">${UI._escape(UI._shortUrl(r.site_url || "—"))}</td>
      <td>${UI._statusBadge(r.status)}</td>
      <td class="mono" style="font-size:11px;">${UI._fmtDate(r.created_at)}</td>
      <td class="mono" style="font-size:11px;">${UI._fmtDate(r.started_at)}</td>
      <td class="mono">${UI._durStr(r.started_at, r.finished_at) || "—"}</td>
      <td><button class="small-success-btn black-spaced" onclick="event.stopPropagation();UI.renderRunDashboard('${r.id}')">View</button></td>
    </tr>`).join("") || `<tr><td colspan="7" class="tbl-loading">No runs match</td></tr>`;
  },

  _setRunFilter(f) {
    document.querySelectorAll("#runFilterTabs .filter-tab").forEach(t => t.classList.toggle("active", t.textContent === f));
    const all = window.__RUN_HISTORY_DATA__ || [];
    const filtered = f === "all" ? all : all.filter(r => r.status === f);
    document.getElementById("runHistoryTbody").innerHTML = UI._runRows(filtered);
  },

  // ── RECOMMENDATIONS ───────────────────────────────────────────────────────
  async renderRecommendations() {
    document.getElementById("pageTitle").innerText = "Recommendations";
    document.getElementById("metricsBar").innerHTML = "";
    document.getElementById("content").innerHTML = `<div class="section-card"><div class="tbl-loading">Loading recommendations…</div></div>`;
    try {
      const sites = await API.getSites();
      const allRecs = [];
      await Promise.allSettled(sites.map(async s => {
        const latest = (s.runs || []).find(r => r.status === "success");
        if (!latest) return;
        try {
          const d = await API.getRunDashboard(latest.id);
          (d.ai?.recommendations || []).forEach(r => allRecs.push({ ...r, site_url: s.url, run_id: latest.id }));
        } catch { }
      }));
      const highC = allRecs.filter(r => r.priority === "high").length;
      const medC = allRecs.filter(r => r.priority === "med").length;
      const types = [...new Set(allRecs.map(r => r.action_type))];
      document.getElementById("metricsBar").innerHTML = `
        <div class="metric-card metric-green"><p>Total Recs</p><h3>${allRecs.length}</h3><div class="metric-sub">Across all sites</div></div>
        <div class="metric-card metric-amber"><p>High Priority</p><h3>${highC}</h3><div class="metric-sub">Need attention</div></div>
        <div class="metric-card metric-blue"><p>Medium</p><h3>${medC}</h3><div class="metric-sub">Nice to fix</div></div>
        <div class="metric-card metric-purple"><p>Action Types</p><h3>${types.length}</h3><div class="metric-sub">Unique</div></div>`;
      window.__ALL_RECS__ = allRecs;
      document.getElementById("content").innerHTML = `
        <div class="section-card">
          <div class="section-head">
            <h3 class="section-title">All Recommendations</h3>
            <div class="filter-tabs" id="recTypeTabs">
              <button class="filter-tab active" onclick="UI._setRecFilter('all')">All</button>
              ${types.map(t => `<button class="filter-tab" onclick="UI._setRecFilter('${UI._escape(t)}')">${t.replace(/_/g, " ")}</button>`).join("")}
            </div>
          </div>
          <div class="rec-cards-grid" id="recCardsGrid">${UI._recCards(allRecs)}</div>
        </div>`;
    } catch (e) { Toast.error(e.message || "Failed to load recommendations"); }
  },

  _recCards(recs) {
    const icons = { title_fix: "📝", h1_fix: "📌", content_expand: "📄", meta_description: "🏷", ranking_improvement: "📈", general: "💡" };
    return recs.map(r => `
      <div class="rec-card rec-card-${r.priority || "low"}" onclick="UI.renderRunDashboard('${r.run_id}')" style="cursor:pointer;">
        <div class="rec-card-icon">${icons[r.action_type] || "💡"}</div>
        <div class="rec-card-body">
          <div class="rec-card-site">${UI._escape(UI._shortUrl(r.site_url || "—"))}</div>
          <div class="rec-card-title">${(r.action_type || "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</div>
          <div class="rec-card-text">${UI._escape(r.reason_text || "")}</div>
          <div class="rec-tags" style="margin-top:8px;">
            <span class="rec-tag rec-tag-${r.priority}">${r.priority || "low"}</span>
            <span class="rec-tag rec-tag-type">${UI._escape(r.action_type || "")}</span>
            ${r.keyword ? `<span class="rec-tag rec-tag-kw">${UI._escape(r.keyword)}</span>` : ""}
          </div>
        </div>
        <div class="rec-card-impact">
          <div class="impact-label">Impact</div>
          <div class="impact-val" style="color:${UI._priorityColor(r.expected_impact)}">${r.expected_impact || "—"}</div>
        </div>
      </div>`).join("") || `<div class="chart-empty" style="padding:32px;">No recommendations found</div>`;
  },

  _setRecFilter(type) {
    document.querySelectorAll("#recTypeTabs .filter-tab").forEach(t =>
      t.classList.toggle("active", type === "all" ? t.textContent === "All" : t.textContent.trim().replace(/ /g, "_") === type)
    );
    const all = window.__ALL_RECS__ || [];
    const filtered = type === "all" ? all : all.filter(r => r.action_type === type);
    document.getElementById("recCardsGrid").innerHTML = UI._recCards(filtered);
  },

  // ── KEYWORDS EXPLORER ─────────────────────────────────────────────────────
  async renderKeywords() {
    document.getElementById("pageTitle").innerText = "Keywords Explorer";
    document.getElementById("metricsBar").innerHTML = "";
    document.getElementById("content").innerHTML = `<div class="section-card"><div class="tbl-loading">Loading keywords…</div></div>`;
    try {
      const sites = await API.getSites();
      const allKws = [];
      await Promise.allSettled(sites.map(async s => {
        const latest = (s.runs || []).find(r => r.status === "success");
        if (!latest) return;
        try {
          const d = await API.getRunDashboard(latest.id);
          const kwSet = new Set();
          (d.ai?.recommendations || []).forEach(r => { if (r.keyword) kwSet.add(r.keyword); });
          kwSet.forEach(kw => allKws.push({ keyword: kw, site_url: s.url, run_id: latest.id, position: null }));
        } catch { }
      }));
      document.getElementById("metricsBar").innerHTML = `
        <div class="metric-card metric-green"><p>Total Keywords</p><h3>${allKws.length}</h3><div class="metric-sub">Across all sites</div></div>
        <div class="metric-card metric-blue"><p>Sites Tracked</p><h3>${sites.length}</h3><div class="metric-sub">With audit data</div></div>`;
      window.__ALL_KWS__ = allKws;
      document.getElementById("content").innerHTML = `
        <div class="section-card">
          <div class="section-head">
            <h3 class="section-title">Keyword Coverage</h3>
            <input class="kw-search" id="kwSearch" placeholder="🔍  Search keywords…" oninput="UI._filterKeywords(this.value)"/>
          </div>
          ${allKws.length ? `
          <table class="data-table" id="kwTable">
            <thead><tr><th>Keyword</th><th>Site</th><th>Position</th><th></th></tr></thead>
            <tbody id="kwTbody">${UI._kwRows(allKws)}</tbody>
          </table>`: `<div class="chart-empty" style="padding:48px;text-align:center;">
            <div style="font-size:36px;margin-bottom:12px;">🔍</div>
            <div>Run audits to discover keywords</div>
          </div>`}
        </div>`;
    } catch (e) { Toast.error(e.message || "Failed to load keywords"); }
  },

  _kwRows(kws) {
    return kws.map(k => `<tr>
      <td><span class="kw-chip">${UI._escape(k.keyword)}</span></td>
      <td class="mono" style="font-size:11px;">${UI._escape(UI._shortUrl(k.site_url || "—"))}</td>
      <td>${k.position != null ? `<span class="pos-badge">#${k.position}</span>` : `<span style="color:#94a3b8;font-size:11px;">unranked</span>`}</td>
      <td><button class="small-success-btn black-spaced" onclick="UI.renderRunDashboard('${k.run_id}')">View Run</button></td>
    </tr>`).join("") || `<tr><td colspan="4" class="tbl-loading">No matches</td></tr>`;
  },

  _filterKeywords(q) {
    const all = window.__ALL_KWS__ || [];
    const filtered = q ? all.filter(k => k.keyword.toLowerCase().includes(q.toLowerCase())) : all;
    document.getElementById("kwTbody").innerHTML = UI._kwRows(filtered);
  },

  // ── RUN DASHBOARD ─────────────────────────────────────────────────────────
  _runPollTimer: null,
  _runPollActive: false,
  _runPollCount: 0,
  _POLL_INTERVAL_MS: 5000,
  _POLL_MAX: 120, // stop after 10 min (120 × 5s) regardless

  async renderRunDashboard(runId) {
    if (!runId || runId === "null") { Toast.error("Missing run id"); return Router.go("sites"); }
    document.getElementById("pageTitle").innerText = "Run Monitor";
    document.getElementById("metricsBar").innerHTML = "";

    document.getElementById("content").innerHTML = `
      <div class="run-hero">
        <div class="run-hero-top">
          <div>
            <div class="run-hero-url" id="heroUrl">Loading…</div>
            <div class="run-hero-id mono">${runId}</div>
          </div>
          <div class="row-gap">
            <div id="heroStatus"></div>
            <button class="btn-secondary" onclick="Router.go('sites')">← Back</button>
            <button class="primary-btn" onclick="UI.retryRun('${runId}',this)">↺ Retry</button>
          </div>
        </div>
        <div class="run-hero-stats" id="heroStats"></div>
        <div class="progress-track"><div class="progress-fill" id="runProgress" style="width:0%"></div></div>
      </div>

      <div class="section-card" style="margin-bottom:16px;">
        <div class="section-title" style="margin-bottom:14px;">Pipeline</div>
        <div class="pipeline-steps" id="pipelineSteps"></div>
      </div>

      <div id="runMetricsBar" style="display:flex;gap:14px;margin-bottom:16px;flex-wrap:wrap;"></div>

      <div class="dashboard-grid" style="margin-bottom:16px;">
        <div class="section-card">
          <div class="section-title" style="margin-bottom:14px;">Step Durations</div>
          <div id="durChart" class="dur-chart"></div>
        </div>
        <div class="section-card">
          <div class="section-title" style="margin-bottom:14px;">Recommendations</div>
          <div id="recList" class="rec-list"></div>
        </div>
      </div>

      <div class="section-card" style="margin-bottom:16px;">
        <div class="section-title" style="margin-bottom:14px;">Step Details</div>
        <table class="data-table">
          <thead><tr><th>Step</th><th>Status</th><th>Started</th><th>Finished</th><th>Duration</th><th>Attempts</th><th>Meta</th><th></th></tr></thead>
          <tbody id="stepsTableBody"></tbody>
        </table>
      </div>

      <div class="section-card">
        <div class="section-title" style="margin-bottom:14px;">AI Analysis</div>
        <div id="aiWrap"><div class="muted">Waiting for analysis…</div></div>
      </div>`;

    history.replaceState(null, '', '#run:' + runId); // update hash without re-routing
    await UI._loadRunDashboard(runId, { silent: false });
    UI._startRunPolling(runId);
  },

  async retryRun(runId, runBtn) {
    setButtonState(runBtn, false, "…");
    try {
      const force = await new Promise(resolve => {
        document.getElementById("modalContainer").innerHTML = `
          <div class="modal" onclick="UI.closeModalOnBackdrop(event)">
            <div class="modal-content">
              <h3>Retry Run</h3>
              <p style="margin-bottom:14px;color:#6b7280;font-size:13px;">Normal retry resumes from earliest incomplete step. Force retry resets failed steps.</p>
              <label style="display:flex;align-items:center;gap:10px;margin-bottom:18px;cursor:pointer;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;">
                <input type="checkbox" id="forceRetryCheck" style="width:16px;height:16px;cursor:pointer;"/>
                <div><div style="font-size:13px;font-weight:600;">Force retry</div><div style="font-size:11px;color:#9ca3af;margin-top:2px;">Resets failed steps</div></div>
              </label>
              <div class="modal-actions">
                <button class="primary-btn" onclick="const c=document.getElementById('forceRetryCheck').checked;document.getElementById('modalContainer').innerHTML='';window.__retryResolve__(c)">Confirm</button>
                <button class="btn-secondary" onclick="document.getElementById('modalContainer').innerHTML='';window.__retryResolve__(null)">Cancel</button>
              </div>
            </div>
          </div>`;
        window.__retryResolve__ = resolve;
      });
      if (force === null) return;
      await API.retryRun(runId, force);
      Toast.success(force ? "Force retry triggered" : "Retry triggered");
      await UI._loadRunDashboard(runId, { silent: true });
      UI._startRunPolling(runId);
    } catch (e) { Toast.error(e.message || "Retry failed"); }
    finally { setButtonState(runBtn, true, "↺ Retry"); }
  },

  _startRunPolling(runId) {
    UI._stopRunPolling();
    UI._runPollActive = true;
    UI._runPollCount = 0;
    const loop = async () => {
      if (!UI._runPollActive) return;
      if (UI._runPollCount >= UI._POLL_MAX) { UI._stopRunPolling(); return; }
      UI._runPollCount++;
      await UI._loadRunDashboard(runId, { silent: true });
      if (!UI._runPollActive) return;
      UI._runPollTimer = setTimeout(loop, UI._POLL_INTERVAL_MS);
    };
    UI._runPollTimer = setTimeout(loop, UI._POLL_INTERVAL_MS);
  },
  _stopRunPolling() {
    UI._runPollActive = false;
    if (UI._runPollTimer) { clearTimeout(UI._runPollTimer); UI._runPollTimer = null; }
  },

  async _loadRunDashboard(runId, { silent }) {
    let data;
    try { data = await API.getRunDashboard(runId); window.__LAST_RUN_DASHBOARD__ = data; }
    catch (e) { if (!silent) Toast.error(e.message || "Failed to load run"); return; }

    const run = data.run;
    const site = data.site;
    const steps = (data.steps || []).map(s => ({ ...s, step_name: s.step_name || s.step || s.name }))
      .sort((a, b) => STEP_ORDER.indexOf(a.step_name) - STEP_ORDER.indexOf(b.step_name));
    const ai = data.ai || {}, recs = ai.recommendations || [];

    const heroUrlEl = document.getElementById("heroUrl");
    if (heroUrlEl) heroUrlEl.textContent = site.normalized_url || run.site_url || run.id;
    const heroStatus = document.getElementById("heroStatus");
    if (heroStatus) heroStatus.innerHTML = UI._statusBadge(run.status);
    const heroStats = document.getElementById("heroStats");
    if (heroStats) heroStats.innerHTML = `
      <div class="run-stat"><label>Started</label><span>${UI._fmtDate(run.started_at)}</span></div>
      <div class="run-stat"><label>Finished</label><span>${run.finished_at ? UI._fmtDate(run.finished_at) : "—"}</span></div>
      <div class="run-stat"><label>Duration</label><span>${UI._durStr(run.started_at, run.finished_at) || "—"}</span></div>
      <div class="run-stat"><label>Steps</label><span>${steps.length} / ${STEP_ORDER.length}</span></div>`;

    const done = steps.filter(s => s.status === "success" || s.status === "skipped").length;
    const progEl = document.getElementById("runProgress");
    if (progEl) progEl.style.width = Math.round((done / STEP_ORDER.length) * 100) + "%";

    const kwCount = steps.find(s => s.step_name === "KEYWORDS")?.meta?.count || 0;
    const recCount = steps.find(s => s.step_name === "ANALYZE")?.meta?.recommendations || 0;
    const words = steps.find(s => s.step_name === "FETCH_CLIENT")?.meta?.word_count || 0;
    const comp = steps.find(s => s.step_name === "COMPETITORS")?.meta?.competitors_fetched || 0;
    const mbar = document.getElementById("runMetricsBar");
    if (mbar) mbar.innerHTML = `
      <div class="metric-card metric-green"><p>Keywords</p><h3>${kwCount}</h3><div class="metric-sub">Extracted</div></div>
      <div class="metric-card metric-purple"><p>Recommendations</p><h3>${recCount}</h3><div class="metric-sub">Generated</div></div>
      <div class="metric-card metric-blue"><p>Word Count</p><h3>${words}</h3><div class="metric-sub">Client page</div></div>
      <div class="metric-card metric-amber"><p>Competitors</p><h3>${comp}</h3><div class="metric-sub">Fetched</div></div>`;

    const pipeEl = document.getElementById("pipelineSteps");
    if (pipeEl) pipeEl.innerHTML = STEP_ORDER.map((name, i) => {
      const s = steps.find(x => x.step_name === name);
      const st = s?.status || "queued";
      const d = UI._durStr(s?.started_at, s?.finished_at);
      return `<div class="pipeline-step pipeline-${st}" onclick="UI.openStepModal('${s?.id || ""}')">
        ${i < STEP_ORDER.length - 1 ? `<div class="pipeline-connector pipeline-connector-${st}"></div>` : ""}
        <div class="pipeline-circle pipeline-circle-${st}">${STEP_ICONS[name] || "●"}</div>
        <div class="pipeline-label">${name.replace("_", " ")}</div>
        <div class="pipeline-dur">${d || (st === "queued" ? "pending" : "")}</div>
      </div>`;
    }).join("");

    const stepsT = steps.filter(s => s.started_at);
    const maxMs = Math.max(...stepsT.map(s => UI._durationMs(s.started_at, s.finished_at) || 0), 1);
    const barC = { success: "#10b981", running: "#3b82f6", failed: "#ef4444", queued: "#e5e7eb" };
    const durEl = document.getElementById("durChart");
    if (durEl) durEl.innerHTML = stepsT.map(s => {
      const ms = UI._durationMs(s.started_at, s.finished_at) || 0;
      const pct = Math.round((ms / maxMs) * 100);
      const label = ms < 1000 ? ms + "ms" : (ms / 1000).toFixed(1) + "s";
      return `<div class="dur-row">
        <div class="dur-label-row"><span class="dur-name">${s.step_name}</span><span class="dur-val">${label}</span></div>
        <div class="dur-track"><div class="dur-fill" style="width:${pct}%;background:${barC[s.status] || "#6b7280"}"></div></div>
      </div>`;
    }).join("") || `<div class="muted">No timing data yet</div>`;

    const recIcons = { title_fix: "📝", h1_fix: "📌", content_expand: "📄", meta_description: "🏷", ranking_improvement: "📈", general: "💡" };
    const recEl = document.getElementById("recList");
    if (recEl) recEl.innerHTML = recs.length ? recs.map(r => `
      <div class="rec-item rec-${r.priority || "low"}">
        <div class="rec-icon">${recIcons[r.action_type] || "💡"}</div>
        <div class="rec-body">
          <div class="rec-title">${(r.action_type || "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</div>
          <div class="rec-text">${UI._escape(r.reason_text || "")}</div>
          <div class="rec-tags">
            <span class="rec-tag rec-tag-${r.priority}">${r.priority || "low"}</span>
            <span class="rec-tag rec-tag-type">${UI._escape(r.action_type || "")}</span>
            ${r.keyword ? `<span class="rec-tag rec-tag-kw">${UI._escape(r.keyword)}</span>` : ""}
          </div>
        </div>
      </div>`).join("") : ` <div class="muted">No recommendations yet</div>`;

    const tbEl = document.getElementById("stepsTableBody");
    if (tbEl) tbEl.innerHTML = steps.map(s => {
      const meta = s.meta || {};
      const hint = Object.entries(meta).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—";
      return `<tr onclick="UI.openStepModal('${s.id}')" style="cursor:pointer;">
        <td class="mono">${s.step_name}</td>
        <td>${UI._statusBadge(s.status)}</td>
        <td class="mono" style="font-size:11px;">${UI._fmtDate(s.started_at)}</td>
        <td class="mono" style="font-size:11px;">${UI._fmtDate(s.finished_at)}</td>
        <td class="mono">${UI._durStr(s.started_at, s.finished_at) || "—"}</td>
        <td style="text-align:center;">${s.attempts ?? 0}</td>
        <td style="font-size:11px;color:#6b7280;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${UI._escape(hint)}</td>
        <td><button class="btn-secondary" style="font-size:11px;padding:4px 8px;" onclick="event.stopPropagation();UI.openStepModal('${s.id}')">View</button></td>
      </tr>`;
    }).join("");

    const aiEl = document.getElementById("aiWrap");
    if (aiEl && ai.summary) aiEl.innerHTML = `
      <div class="ai-summary">${UI._escape(ai.summary)}</div>
      ${ai.meta ? `<div class="ai-meta">Provider: ${UI._escape(ai.meta.provider || "—")} · Model: ${UI._escape(ai.meta.model || "—")} · Tokens: ${ai.meta.usage?.total_tokens ?? "—"} · Cost: $${ai.meta.usage?.cost?.toFixed(5) ?? "—"}</div>` : ""}`;

    if (["success", "failed", "canceled"].includes((run.status || "").toLowerCase())) UI._stopRunPolling();
  },

  openStepModal(stepId) {
    const data = window.__LAST_RUN_DASHBOARD__;
    if (!data?.steps?.length) return Toast.error("Step data not loaded");
    const step = data.steps.find(s => s.id === stepId);
    if (!step) return Toast.error("Step not found");
    const meta = step.meta || {};
    document.getElementById("modalContainer").innerHTML = `
      <div class="modal" onclick="UI.closeModalOnBackdrop(event)">
        <div class="modal-content modal-wide">
          <div class="section-head">
            <h3 class="section-title">Step: <span class="mono">${step.step_name}</span></h3>
            <button class="btn-secondary" onclick="UI.closeModal()">✕ Close</button>
          </div>
          <div class="step-modal-grid">
            <div class="metric-card metric-${step.status === "success" ? "green" : step.status === "running" ? "blue" : "amber"}">
              <p>Status</p><h3>${UI._statusBadge(step.status)}</h3>
            </div>
            <div class="metric-card metric-blue"><p>Duration</p><h3>${UI._durStr(step.started_at, step.finished_at) || "—"}</h3></div>
            <div class="metric-card metric-amber"><p>Attempts</p><h3>${step.attempts ?? 0}</h3></div>
          </div>
          <div class="summary-grid" style="margin-top:12px;">
            <div><div class="label">Started</div><div class="mono">${UI._fmtDate(step.started_at)}</div></div>
            <div><div class="label">Finished</div><div class="mono">${UI._fmtDate(step.finished_at)}</div></div>
          </div>
          ${step.last_error ? `<div class="error-panel" style="margin-top:12px;"><div class="error-title">Last Error</div><div class="error-text">${UI._escape(step.last_error)}</div></div>` : ""}
          <h3 class="section-title" style="margin:16px 0 8px;">Meta</h3>
          <pre class="pre">${UI._escape(JSON.stringify(meta, null, 2))}</pre>
        </div>
      </div>`;
  },
};