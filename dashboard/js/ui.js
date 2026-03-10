// js/ui.js
const UI = {

  // ─── Helpers ──────────────────────────────────────────────────────────────
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
    return String(s || "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  },

  _statusBadge(status) {
    const s = (status || "queued").toLowerCase();
    return `<span class="status-badge status-${s}">${s}</span>`;
  },

  _countSteps(steps) {
    const c = { queued: 0, running: 0, success: 0, failed: 0, skipped: 0 };
    steps.forEach(s => { const k = (s.status || "").toLowerCase(); if (c[k] !== undefined) c[k]++; });
    return c;
  },

  _currentStep(steps) {
    return steps.find(s => s.status === "running")
      || steps.find(s => s.status === "failed")
      || [...steps].filter(s => s.status === "success")
        .sort((a, b) => new Date(b.finished_at || 0) - new Date(a.finished_at || 0))[0]
      || null;
  },

  // ─── Overview ──────────────────────────────────────────────────────────────
  async renderOverview() {
    document.getElementById("pageTitle").innerText = "Overview";
    document.getElementById("metricsBar").innerHTML = "";

    let sites = [];
    try { sites = await API.getSites(); } catch { Toast.error("Failed to load overview"); }

    const allRuns = sites.flatMap(s => s.runs || []);
    const counts = { success: 0, running: 0, failed: 0, queued: 0 };
    allRuns.forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; });
    const total = allRuns.length || 1;
    const rate = Math.round((counts.success / total) * 100);

    document.getElementById("metricsBar").innerHTML = `
      <div class="metric-card metric-green"><p>Total Sites</p><h3>${sites.length}</h3><div class="metric-sub">Tracked domains</div></div>
      <div class="metric-card metric-blue"><p>Total Runs</p><h3>${allRuns.length}</h3><div class="metric-sub">All time</div></div>
      <div class="metric-card metric-amber"><p>Running Now</p><h3>${counts.running}</h3><div class="metric-sub">Active audits</div></div>
      <div class="metric-card metric-purple"><p>Success Rate</p><h3>${rate}%</h3><div class="metric-sub">Completion</div></div>
    `;

    const recent = [...allRuns]
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 6);

    const activityHtml = recent.map(r => {
      const site = sites.find(s => (s.runs || []).find(x => x.id === r.id));
      const dotColor = { success: "#10b981", running: "#3b82f6", failed: "#ef4444", queued: "#6b7280" }[r.status] || "#6b7280";
      return `<div class="activity-item">
        <div class="activity-dot" style="background:${dotColor}"></div>
        <div class="activity-content">
          <div class="activity-title">${UI._escape(site?.url || "Unknown")}</div>
          <div class="activity-meta">${r.status.toUpperCase()} · ${UI._fmtDate(r.created_at)}</div>
        </div>
        ${UI._statusBadge(r.status)}
      </div>`;
    }).join("") || `<div class="muted" style="padding:12px;">No runs yet</div>`;

    // Donut SVG
    const palette = { success: "#10b981", running: "#3b82f6", failed: "#ef4444", queued: "#9ca3af" };
    const r = 15.9, circ = 2 * Math.PI * r;
    let offset = 0, circles = "", legend = "";
    for (const [k, v] of Object.entries(counts)) {
      if (!v) continue;
      const dash = (v / total) * circ;
      circles += `<circle cx="18" cy="18" r="${r}" fill="none" stroke="${palette[k]}" stroke-width="3.2"
        stroke-dasharray="${dash} ${circ}" stroke-dashoffset="${-offset}" />`;
      offset += dash;
      legend += `<div class="donut-legend-item"><span class="donut-dot" style="background:${palette[k]}"></span>${k}: <strong>${v}</strong></div>`;
    }

    document.getElementById("content").innerHTML = `
      <div class="overview-grid">
        <div class="section-card">
          <div class="section-title" style="margin-bottom:14px;">Run Distribution</div>
          <div class="donut-wrap">
            <div class="donut-chart">
              <svg viewBox="0 0 36 36" style="transform:rotate(-90deg)">
                <circle cx="18" cy="18" r="${r}" fill="none" stroke="#f3f4f6" stroke-width="3.2"/>
                ${circles}
              </svg>
              <div class="donut-center"><div class="donut-pct">${rate}%</div><div class="donut-sub-label">success</div></div>
            </div>
            <div class="donut-legend">${legend}</div>
          </div>
        </div>

        <div class="section-card">
          <div class="section-title" style="margin-bottom:14px;">Recent Activity</div>
          <div class="activity-list">${activityHtml}</div>
        </div>
      </div>

      <div class="section-card" style="margin-top:16px;">
        <div class="section-head">
          <h3 class="section-title">Sites</h3>
          <button class="primary-btn" onclick="UI.openAddSiteModal()">+ Add Site</button>
        </div>
        <table class="data-table">
          <thead><tr><th>URL</th><th>Geo</th><th>Device</th><th>Latest Run</th><th>Status</th><th></th></tr></thead>
          <tbody>
            ${sites.map(s => {
      const latest = (s.runs || [])[0];
      return `<tr>
                <td class="mono">${UI._escape(s.url)}</td>
                <td>${s.geo}</td>
                <td>${s.device}</td>
                <td class="mono" style="font-size:11px;">${UI._fmtDate(latest?.created_at)}</td>
                <td>${UI._statusBadge(latest?.status || "none")}</td>
                <td>
                  <button class="small-success-btn" onclick="UI.startRun('${s.id}')">Run</button>
                  ${latest ? `<button class="small-success-btn black-spaced" onclick="UI.renderRunDashboard('${latest.id}')">View</button>` : ""}
                </td>
              </tr>`;
    }).join("")}
          </tbody>
        </table>
      </div>
    `;
  },

  // ─── Sites ─────────────────────────────────────────────────────────────────
  async renderSites() {
    document.getElementById("pageTitle").innerText = "Sites";
    document.getElementById("metricsBar").innerHTML = "";

    try {
      const sites = await API.getSites();

      document.getElementById("metricsBar").innerHTML = `
        <div class="metric-card metric-green"><p>Total Sites</p><h3>${sites.length}</h3><div class="metric-sub">Tracked domains</div></div>
      `;

      let html = `
        <div class="section-card">
          <div class="section-head">
            <h3 class="section-title">Client Sites</h3>
            <button class="primary-btn" onclick="UI.openAddSiteModal()">+ Add Site</button>
          </div>
          <table class="data-table">
            <thead><tr><th style="width:40%">URL</th><th>Geo</th><th>Lang</th><th>Device</th><th>Runs</th><th>Created</th><th style="width:160px">Actions</th></tr></thead>
            <tbody>
      `;
      sites.forEach(site => {
        const runs = site.runs || [];
        const latest = runs[0];
        html += `<tr>
          <td class="mono">${UI._escape(site.url)}</td>
          <td>${site.geo}</td>
          <td>${site.language}</td>
          <td>${site.device}</td>
          <td><span class="runs-count">${runs.length}</span></td>
          <td class="mono" style="font-size:11px;">${UI._fmtDate(site.created_at)}</td>
          <td>
            <button class="small-success-btn" onclick="UI.startRun('${site.id}')">▶ Run Audit</button>
            ${latest ? `<button class="small-success-btn black-spaced" onclick="UI.renderRunDashboard('${latest.id}')">View</button>` : ""}
          </td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
      document.getElementById("content").innerHTML = html;
    } catch (e) {
      Toast.error(e.message || "Failed to load sites");
      document.getElementById("content").innerHTML = `<div class="section-card">Failed to load sites.</div>`;
    }
  },

  openAddSiteModal() {
    document.getElementById("modalContainer").innerHTML = `
      <div class="modal" onclick="UI.closeModalOnBackdrop(event)">
        <div class="modal-content">
          <h3>Add New Site</h3>
          <label class="form-label">URL</label>
          <input id="newSiteUrl" placeholder="https://example.com" />
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
            <div>
              <label class="form-label">Geo</label>
              <input id="newSiteGeo" placeholder="GH" value="GH" style="margin-bottom:0"/>
            </div>
            <div>
              <label class="form-label">Language</label>
              <input id="newSiteLang" placeholder="en" value="en" style="margin-bottom:0"/>
            </div>
            <div>
              <label class="form-label">Device</label>
              <select id="newSiteDevice" style="width:100%;padding:10px 12px;border:1px solid #e5e7eb;border-radius:6px;font-size:14px;">
                <option value="desktop">Desktop</option>
                <option value="mobile">Mobile</option>
              </select>
            </div>
          </div>
          <div class="modal-actions">
            <button class="primary-btn" onclick="UI.submitNewSite(this)">Save</button>
            <button class="btn-secondary" onclick="UI.closeModal()">Cancel</button>
          </div>
        </div>
      </div>
    `;
    setTimeout(() => document.getElementById("newSiteUrl")?.focus(), 0);
  },

  closeModalOnBackdrop(e) {
    if (e.target.classList.contains("modal")) UI.closeModal();
  },

  closeModal() {
    document.getElementById("modalContainer").innerHTML = "";
  },

  async submitNewSite(btn) {
    const url = document.getElementById("newSiteUrl").value.trim();
    if (!url) return Toast.error("URL is required");
    setButtonState(btn, false, "Saving...");
    try {
      await API.authFetch("/sites", {
        method: "POST",
        body: JSON.stringify({
          url,
          geo: document.getElementById("newSiteGeo").value || "GH",
          language: document.getElementById("newSiteLang").value || "en",
          device: document.getElementById("newSiteDevice").value || "desktop",
        }),
      });
      Toast.success("Site added");
      UI.closeModal();
      UI.renderSites();
    } catch (e) {
      Toast.error(e.message || "Failed to add site");
    } finally {
      setButtonState(btn, true);
    }
  },

  async startRun(siteId) {
    try {
      const run = await API.createRun(siteId);
      Toast.success("Audit started!");
      Router.go(`run:${run.id}`);
    } catch (e) {
      Toast.error(e.message || "Failed to start run");
    }
  },

  // ─── Health ────────────────────────────────────────────────────────────────
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
          <div class="activity-content">
            <div class="activity-title">${k}</div>
            <div class="activity-meta">${v}</div>
          </div>
          ${UI._statusBadge(ok ? "success" : "failed")}
        </div>`;
      }).join("");

      document.getElementById("content").innerHTML = `
        <div class="overview-grid">
          <div class="section-card">
            <div class="section-title" style="margin-bottom:14px;">Services</div>
            <div class="activity-list">${rows || '<div class="muted" style="padding:12px;">No data</div>'}</div>
          </div>
        </div>
      `;
    } catch {
      Toast.error("Health check failed");
      document.getElementById("content").innerHTML = `<div class="section-card">Health unavailable.</div>`;
    }
  },

  // ─── Run Dashboard ─────────────────────────────────────────────────────────
  _runPollTimer: null,

  async renderRunDashboard(runId) {
    if (!runId || runId === "null") {
      Toast.error("Missing run id");
      return Router.go("sites");
    }

    document.getElementById("pageTitle").innerText = "Run Monitor";
    document.getElementById("metricsBar").innerHTML = "";

    document.getElementById("content").innerHTML = `
      <!-- Run Hero -->
      <div class="run-hero">
        <div class="run-hero-top">
          <div>
            <div class="run-hero-url" id="heroUrl">Loading…</div>
            <div class="run-hero-id mono">${runId}</div>
          </div>
          <div class="row-gap">
            <div id="heroStatus"></div>
            <button class="btn-secondary" onclick="Router.go('sites')">← Back</button>
            <button class="primary-btn" onclick="UI.retryRun('${runId}', this)">↺ Retry</button>
          </div>
        </div>
        <div class="run-hero-stats" id="heroStats"></div>
        <div class="progress-track"><div class="progress-fill" id="runProgress" style="width:0%"></div></div>
      </div>

      <!-- Pipeline -->
      <div class="section-card" style="margin-bottom:16px;">
        <div class="section-title" style="margin-bottom:14px;">Pipeline</div>
        <div class="pipeline-steps" id="pipelineSteps"></div>
      </div>

      <!-- Metric cards -->
      <div id="runMetricsBar" style="display:flex;gap:14px;margin-bottom:16px;flex-wrap:wrap;"></div>

      <!-- Charts + Recs -->
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

      <!-- Steps table -->
      <div class="section-card" style="margin-bottom:16px;">
        <div class="section-title" style="margin-bottom:14px;">Step Details</div>
        <table class="data-table">
          <thead><tr><th>Step</th><th>Status</th><th>Started</th><th>Finished</th><th>Duration</th><th>Attempts</th><th>Meta</th><th></th></tr></thead>
          <tbody id="stepsTableBody"></tbody>
        </table>
      </div>

      <!-- AI -->
      <div class="section-card">
        <div class="section-title" style="margin-bottom:14px;">AI Analysis</div>
        <div id="aiWrap"><div class="muted">Waiting for analysis…</div></div>
      </div>
    `;

    Router.go(`run:${runId}`);
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
              <p style="margin-bottom:14px;color:#6b7280;font-size:13px;">Normal retry resumes from the earliest incomplete step. Force retry resets failed steps.</p>
              <label style="display:flex;align-items:center;gap:10px;margin-bottom:18px;cursor:pointer;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 14px;">
                <input type="checkbox" id="forceRetryCheck" style="width:16px;height:16px;cursor:pointer;" />
                <div>
                  <div style="font-size:13px;font-weight:600;">Force retry</div>
                  <div style="font-size:11px;color:#9ca3af;margin-top:2px;">Resets failed steps so they can run again</div>
                </div>
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
    } catch (e) {
      Toast.error(e.message || "Retry failed");
    } finally {
      setButtonState(runBtn, true, "↺ Retry");
    }
  },

  _startRunPolling(runId) {
    UI._stopRunPolling();
    UI._runPollTimer = setInterval(() => UI._loadRunDashboard(runId, { silent: true }), 4000);
  },

  _stopRunPolling() {
    if (UI._runPollTimer) clearInterval(UI._runPollTimer);
    UI._runPollTimer = null;
  },

  async _loadRunDashboard(runId, { silent }) {
    let data;
    try {
      data = await API.getRunDashboard(runId);
      window.__LAST_RUN_DASHBOARD__ = data;
    } catch (e) {
      if (!silent) Toast.error(e.message || "Failed to load run");
      return;
    }

    const run = data.run;
    const steps = (data.steps || [])
      .map(s => ({ ...s, step_name: s.step_name || s.step || s.name }))
      .sort((a, b) => STEP_ORDER.indexOf(a.step_name) - STEP_ORDER.indexOf(b.step_name));
    const ai = data.ai || {};
    const recs = ai.recommendations || [];

    // ── Hero ──
    const site = data?.site?.url || run.site_url || "";
    const heroUrlEl = document.getElementById("heroUrl");
    if (heroUrlEl) heroUrlEl.textContent = site || run.id;
    const heroStatus = document.getElementById("heroStatus");
    if (heroStatus) heroStatus.innerHTML = UI._statusBadge(run.status);

    const dur = UI._durStr(run.started_at, run.finished_at);
    const heroStats = document.getElementById("heroStats");
    if (heroStats) heroStats.innerHTML = `
      <div class="run-stat"><label>Started</label><span>${UI._fmtDate(run.started_at)}</span></div>
      <div class="run-stat"><label>Finished</label><span>${run.finished_at ? UI._fmtDate(run.finished_at) : "—"}</span></div>
      <div class="run-stat"><label>Duration</label><span>${dur || "—"}</span></div>
      <div class="run-stat"><label>Steps</label><span>${steps.length} / ${STEP_ORDER.length}</span></div>
    `;

    // ── Progress ──
    const done = steps.filter(s => s.status === "success" || s.status === "skipped").length;
    const pct = Math.round((done / STEP_ORDER.length) * 100);
    const progressEl = document.getElementById("runProgress");
    if (progressEl) progressEl.style.width = pct + "%";

    // ── Metrics bar ──
    const kwCount = steps.find(s => s.step_name === "KEYWORDS")?.meta?.count || 0;
    const recCount = steps.find(s => s.step_name === "ANALYZE")?.meta?.recommendations || 0;
    const words = steps.find(s => s.step_name === "FETCH_CLIENT")?.meta?.word_count || 0;
    const comp = steps.find(s => s.step_name === "COMPETITORS")?.meta?.competitors_fetched || 0;
    const metricsBar = document.getElementById("runMetricsBar");
    if (metricsBar) metricsBar.innerHTML = `
      <div class="metric-card metric-green"><p>Keywords</p><h3>${kwCount}</h3><div class="metric-sub">Extracted</div></div>
      <div class="metric-card metric-purple"><p>Recommendations</p><h3>${recCount}</h3><div class="metric-sub">Generated</div></div>
      <div class="metric-card metric-blue"><p>Word Count</p><h3>${words}</h3><div class="metric-sub">Client page</div></div>
      <div class="metric-card metric-amber"><p>Competitors</p><h3>${comp}</h3><div class="metric-sub">Fetched</div></div>
    `;

    // ── Pipeline ──
    const pipelineEl = document.getElementById("pipelineSteps");
    if (pipelineEl) pipelineEl.innerHTML = STEP_ORDER.map((name, i) => {
      const s = steps.find(x => x.step_name === name);
      const st = s?.status || "queued";
      const d = UI._durStr(s?.started_at, s?.finished_at);
      const icon = STEP_ICONS[name] || "●";
      const isLast = i === STEP_ORDER.length - 1;
      return `<div class="pipeline-step pipeline-${st}" onclick="UI.openStepModal('${s?.id || ""}')">
        ${!isLast ? `<div class="pipeline-connector pipeline-connector-${st}"></div>` : ""}
        <div class="pipeline-circle pipeline-circle-${st}">${icon}</div>
        <div class="pipeline-label">${name.replace("_", " ")}</div>
        <div class="pipeline-dur">${d || (st === "queued" ? "pending" : "")}</div>
      </div>`;
    }).join("");

    // ── Duration bar chart ──
    const stepsWithTime = steps.filter(s => s.started_at);
    const maxMs = Math.max(...stepsWithTime.map(s => UI._durationMs(s.started_at, s.finished_at) || 0), 1);
    const barColors = { success: "#10b981", running: "#3b82f6", failed: "#ef4444", queued: "#e5e7eb" };
    const durChartEl = document.getElementById("durChart");
    if (durChartEl) durChartEl.innerHTML = stepsWithTime.map(s => {
      const ms = UI._durationMs(s.started_at, s.finished_at) || 0;
      const pct = Math.round((ms / maxMs) * 100);
      const label = ms < 1000 ? ms + "ms" : (ms / 1000).toFixed(1) + "s";
      return `<div class="dur-row">
        <div class="dur-label-row">
          <span class="dur-name">${s.step_name}</span>
          <span class="dur-val">${label}</span>
        </div>
        <div class="dur-track">
          <div class="dur-fill" style="width:${pct}%;background:${barColors[s.status] || "#6b7280"}"></div>
        </div>
      </div>`;
    }).join("") || `<div class="muted">No timing data yet</div>`;

    // ── Recommendations ──
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
      </div>`).join("")
      : `<div class="muted">No recommendations yet</div>`;

    // ── Steps table ──
    const tbodyEl = document.getElementById("stepsTableBody");
    if (tbodyEl) tbodyEl.innerHTML = steps.map(s => {
      const meta = s.meta || {};
      const hint = Object.entries(meta).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—";
      return `<tr onclick="UI.openStepModal('${s.id}')">
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

    // ── AI ──
    const aiEl = document.getElementById("aiWrap");
    if (aiEl && ai.summary) {
      aiEl.innerHTML = `
        <div class="ai-summary">${UI._escape(ai.summary)}</div>
        ${ai.meta ? `<div class="ai-meta">
          Provider: ${UI._escape(ai.meta.provider || "—")} &nbsp;·&nbsp;
          Model: ${UI._escape(ai.meta.model || "—")} &nbsp;·&nbsp;
          Tokens: ${ai.meta.usage?.total_tokens ?? "—"} &nbsp;·&nbsp;
          Cost: $${ai.meta.usage?.cost?.toFixed(5) ?? "—"}
        </div>` : ""}`;
    }

    // ── Stop polling on terminal ──
    if (["success", "failed", "canceled"].includes((run.status || "").toLowerCase())) {
      UI._stopRunPolling();
    }
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
            <div class="metric-card metric-blue">
              <p>Duration</p><h3>${UI._durStr(step.started_at, step.finished_at) || "—"}</h3>
            </div>
            <div class="metric-card metric-amber">
              <p>Attempts</p><h3>${step.attempts ?? 0}</h3>
            </div>
          </div>

          <div class="summary-grid" style="margin-top:12px;">
            <div><div class="label">Started</div><div class="mono">${UI._fmtDate(step.started_at)}</div></div>
            <div><div class="label">Finished</div><div class="mono">${UI._fmtDate(step.finished_at)}</div></div>
          </div>

          ${step.last_error ? `<div class="error-panel" style="margin-top:12px;"><div class="error-title">Last Error</div><div class="error-text">${UI._escape(step.last_error)}</div></div>` : ""}

          <h3 class="section-title" style="margin:16px 0 8px;">Meta</h3>
          <pre class="pre">${UI._escape(JSON.stringify(meta, null, 2))}</pre>
        </div>
      </div>
    `;
  },
};

// ─── Constants ─────────────────────────────────────────────────────────────
const STEP_ORDER = ["FETCH_CLIENT", "CLASSIFY", "KEYWORDS", "SERP", "COMPETITORS", "ANALYZE", "FINALIZE"];
const STEP_ICONS = { FETCH_CLIENT: "⬇", CLASSIFY: "◈", KEYWORDS: "#", SERP: "🔍", COMPETITORS: "⊞", ANALYZE: "★", FINALIZE: "✓" };