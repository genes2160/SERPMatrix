// js/ui.js
const UI = {
  // -----------------------------
  // OVERVIEW
  // -----------------------------
  async renderOverview() {
    document.getElementById("pageTitle").innerText = "Overview";
    document.getElementById("metricsBar").innerHTML = "";

    let sites = [];
    try {
      sites = await API.getSites();
    } catch {
      Toast.error("Failed to load overview");
    }

    document.getElementById("metricsBar").innerHTML = `
      <div class="metric-card">
        <p>Total Sites</p>
        <h3>${sites?.length || 0}</h3>
      </div>
    `;

    document.getElementById("content").innerHTML = `
      <div class="section-card">
        <h3 class="section-title">Quick Actions</h3>
        <div class="row-gap">
          <button class="primary-btn" onclick="Router.go('sites')">Manage Sites</button>
        </div>
      </div>
    `;
  },

  // -----------------------------
  // SITES
  // -----------------------------
  async renderSites() {
    document.getElementById("pageTitle").innerText = "Sites";
    document.getElementById("metricsBar").innerHTML = "";

    try {
      const sites = await API.getSites();

      document.getElementById("metricsBar").innerHTML = `
        <div class="metric-card">
          <p>Total Sites</p>
          <h3>${sites.length}</h3>
        </div>
      `;

      let html = `
        <div class="section-card">
          <div class="section-head">
            <h3 class="section-title">Client Sites</h3>
            <button class="primary-btn" onclick="UI.openAddSiteModal()">+ Add Site</button>
          </div>

          <table class="data-table">
            <thead>
              <tr>
                <th style="width:45%">URL</th>
                <th>Geo</th>
                <th>Device</th>
                <th>Created</th>
                <th style="width:160px">Actions</th>
              </tr>
            </thead>
            <tbody>
          `;

      sites.forEach((site) => {
        let runId = site.runs && Array.isArray(site.runs) && site.runs.length > 0 ? site.runs[0].id : null;
        html += `
              <tr>
                <td class="mono">${site.url}</td>
                <td>${site.geo}</td>
                <td>${site.device}</td>
                <td>${new Date(site.created_at).toLocaleString()}</td>
                <td>
                  <button class="small-success-btn" onclick="UI.startRun('${site.id}')">Run Audit</button>
                  <button class="small-success-btn black-spaced" onclick="UI.renderRunDashboard('${runId}')">View State</button>
                </td>
              </tr>
            `;
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
          <input id="newSiteUrl" placeholder="https://example.com" />
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

    setButtonState(btn, false, "Running...");
    try {
      await API.authFetch("/sites", {
        method: "POST",
        body: JSON.stringify({ url }),
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
      Toast.success("Run started");
      Router.go(`run:${run.id}`);
    } catch (e) {
      Toast.error(e.message || "Failed to start run");
    }
  },

  // -----------------------------
  // HEALTH
  // -----------------------------
  async renderHealth() {
    document.getElementById("pageTitle").innerText = "Health";
    document.getElementById("metricsBar").innerHTML = "";

    try {
      const health = await API.getHealth();

      document.getElementById("content").innerHTML = `
        <div class="section-card">
          <h3 class="section-title">System Health</h3>
          <table class="data-table">
            <tbody>
              <tr><td>Database</td><td>${health.services.database}</td></tr>
              <tr><td>Redis</td><td>${health.services.redis}</td></tr>
            </tbody>
          </table>
        </div>
      `;
    } catch {
      Toast.error("Health check failed");
      document.getElementById("content").innerHTML = `<div class="section-card">Health unavailable.</div>`;
    }
  },

  // -----------------------------
  // RUN DASHBOARD (MONITOR)
  // -----------------------------
  _runPollTimer: null,

  async renderRunDashboard(runId) {
    if (!runId || runId === 'null') {
      Toast.error("Missing run id");
      return Router.go("sites");
    }

    document.getElementById("pageTitle").innerText = "Run Monitor";
    document.getElementById("metricsBar").innerHTML = "";


    // render shell immediately
    document.getElementById("content").innerHTML = `
      <div class="section-card">
        <div class="section-head">
          <h3 class="section-title">Run</h3>
          <div class="row-gap">
            <button class="btn-secondary" onclick="Router.go('sites')">Back to Sites</button>
            <button class="primary-btn" onclick="UI.retryRun('${runId}', this)">Retry Run</button>
          </div>
        </div>

        <div id="runSummary"></div>
        <div id="stepTimeline" class="timeline"></div>
        <div id="runErrorPanel"></div>

        <h3 class="section-title" style="margin-top:18px;">Steps</h3>
        <div id="stepsTableWrap"></div>

        <h3 class="section-title" style="margin-top:18px;">AI Summary</h3>
        <div id="aiWrap"></div>

        <h3 class="section-title" style="margin-top:18px;">System Summary</h3>
        <div id="systemWrap"></div>
      </div>
    `;
    let url = `run:${runId}`
    Router.go(url)
    // load once + polling control
    await UI._loadRunDashboard(runId, { silent: false });
    UI._startRunPolling(runId);
  },

  async retryRun(runId, runBtn) {
    try {
      setButtonState(runBtn, false, "Running...");
      await API.retryRun(runId);
      Toast.success("Retry triggered");
      await UI._loadRunDashboard(runId, { silent: true });
      UI._startRunPolling(runId);
    } catch (e) {
      Toast.error(e.message || "Retry failed");
    } finally {
      setButtonState(runBtn, true);
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
    } catch (e) {
      if (!silent) Toast.error(e.message || "Failed to load run");
      return;
    }

    const run = data.run;
    const steps = (data.steps || []).map((s) => ({
      ...s,
      // normalize names if backend returns audit_run_id vs audit_run etc
      step_name: s.step_name || s.step || s.name,
    }));

    // Metrics bar for this run monitor
    const counts = UI._countSteps(steps);
    const current = UI._currentStep(steps);
    document.getElementById("metricsBar").innerHTML = `
      <div class="metric-card"><p>Status</p><h3>${run.status}</h3></div>
      <div class="metric-card"><p>Steps</p><h3>${steps.length}</h3></div>
      <div class="metric-card"><p>Running</p><h3>${counts.running}</h3></div>
      <div class="metric-card"><p>Failed</p><h3>${counts.failed}</h3></div>
    `;

    // Summary
    document.getElementById("runSummary").innerHTML = UI._renderRunSummary(run, current);

    // Timeline
    document.getElementById("stepTimeline").innerHTML = UI._renderTimeline(steps);

    // Error panel
    document.getElementById("runErrorPanel").innerHTML = UI._renderErrorPanel(run, steps);

    // Steps table
    document.getElementById("stepsTableWrap").innerHTML = UI._renderStepsTable(steps);

    // AI
    document.getElementById("aiWrap").innerHTML = UI._renderAI(data.ai);

    // System summary
    document.getElementById("systemWrap").innerHTML = UI._renderSystemSummary(data.system);

    // Stop polling on terminal states
    const terminal = ["success", "failed", "canceled"];
    if (terminal.includes((run.status || "").toLowerCase())) {
      UI._stopRunPolling();
    }
  },

  _countSteps(steps) {
    const c = { queued: 0, running: 0, success: 0, failed: 0, skipped: 0 };
    steps.forEach((s) => {
      const k = (s.status || "").toLowerCase();
      if (c[k] !== undefined) c[k] += 1;
    });
    return c;
  },

  _currentStep(steps) {
    // running step first
    const running = steps.find((s) => (s.status || "").toLowerCase() === "running");
    if (running) return running;
    // if failed, show failed step
    const failed = steps.find((s) => (s.status || "").toLowerCase() === "failed");
    if (failed) return failed;
    // else last success
    const success = steps
      .filter((s) => (s.status || "").toLowerCase() === "success")
      .sort((a, b) => new Date(b.finished_at || 0) - new Date(a.finished_at || 0))[0];
    return success || null;
  },

  _fmtDate(v) {
    if (!v) return "-";
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString();
  },

  _durationSecs(start, end) {
    if (!start) return null;
    const s = new Date(start).getTime();
    const e = end ? new Date(end).getTime() : Date.now();
    if (Number.isNaN(s) || Number.isNaN(e)) return null;

    const diff = e - s;

    if (diff < 1000) {
      return `${diff}ms`;
    }

    return `${Math.floor(diff / 1000)}s`;
  },

  _renderRunSummary(run, currentStep) {
    const status = (run.status || "").toLowerCase();
    const badge = UI._statusBadge(status);
    const started = UI._fmtDate(run.started_at);
    const finished = UI._fmtDate(run.finished_at);
    const runDur = UI._durationSecs(run.started_at, run.finished_at);
    const runDurTxt = runDur === null ? "-" : `${runDur}`;

    const currentTxt = currentStep ? `${currentStep.step_name} (${currentStep.status})` : "-";

    return `
      <div class="summary-grid">
        <div><div class="label">Run ID</div><div class="mono">${run.id}</div></div>
        <div><div class="label">Status</div>${badge}</div>
        <div><div class="label">Started</div><div>${started}</div></div>
        <div><div class="label">Finished</div><div>${finished}</div></div>
        <div><div class="label">Duration</div><div>${runDurTxt}</div></div>
        <div><div class="label">Current Step</div><div>${currentTxt}</div></div>
      </div>
    `;
  },

  _renderTimeline(steps) {
    if (!steps.length) return `<div class="muted">No steps yet.</div>`;

    // sort by created_at to keep stable order
    const sorted = [...steps].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));

    return sorted
      .map((s) => {
        const st = (s.status || "").toLowerCase();
        const dur = UI._durationSecs(s.started_at, s.finished_at);
        const durTxt = dur === null ? "" : ` • ${dur}`;

        // warning if running too long
        const warn = st === "running" && dur !== null && dur > 120 ? `<span class="warn">⚠</span>` : "";

        return `
          <div class="timeline-item timeline-${st}" onclick="UI.openStepModal('${s.id}')">
            <div class="timeline-name">${s.step_name}${warn}</div>
            <div class="timeline-meta">${st}${durTxt}</div>
          </div>
        `;
      })
      .join("");
  },

  _renderErrorPanel(run, steps) {
    const status = (run.status || "").toLowerCase();
    const failedStep = steps.find((s) => (s.status || "").toLowerCase() === "failed");
    const hasError = status === "failed" || !!failedStep || !!run.error_summary;

    if (!hasError) return "";

    const msg =
      run.error_summary ||
      failedStep?.last_error ||
      "Run failed. Check step error details below.";

    return `
      <div class="error-panel">
        <div class="error-title">Failure Detected</div>
        <div class="error-text">${UI._escape(msg)}</div>
      </div>
    `;
  },

  _renderStepsTable(steps) {
    if (!steps.length) return `<div class="muted">No steps yet.</div>`;

    const sorted = [...steps].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));

    const rows = sorted
      .map((s) => {
        const st = (s.status || "").toLowerCase();
        const badge = UI._statusBadge(st);
        const dur = UI._durationSecs(s.started_at, s.finished_at);
        const durTxt = dur === null ? "-" : `${dur}`;

        // show “what it fetched” from meta (generic)
        const metaKeys = s.meta && typeof s.meta === "object" ? Object.keys(s.meta) : [];
        const metaHint = metaKeys.length ? metaKeys.slice(0, 3).join(", ") + (metaKeys.length > 3 ? "…" : "") : "-";

        return `
          <tr>
            <td class="mono">${s.step_name}</td>
            <td>${badge}</td>
            <td>${UI._fmtDate(s.started_at)}</td>
            <td>${UI._fmtDate(s.finished_at)}</td>
            <td>${durTxt}</td>
            <td>${s.attempts ?? "-"}</td>
            <td class="muted">${UI._escape(metaHint)}</td>
            <td>
              <button class="btn-secondary" onclick="UI.openStepModal('${s.id}')">View</button>
            </td>
          </tr>
        `;
      })
      .join("");

    return `
      <table class="data-table">
        <thead>
          <tr>
            <th>Step</th>
            <th>Status</th>
            <th>Started</th>
            <th>Finished</th>
            <th>Duration</th>
            <th>Attempts</th>
            <th>Meta</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  openStepModal(stepId) {
    // Find current cached run steps from DOM by re-fetching minimal: safest approach = call run dashboard again? (no)
    // We’ll store last run payload on window for now.
    const data = window.__LAST_RUN_DASHBOARD__;
    if (!data?.steps?.length) return Toast.error("Step data not loaded");

    const step = data.steps.find((s) => s.id === stepId);
    if (!step) return Toast.error("Step not found");

    const meta = step.meta || {};
    const err = step.last_error || "";
    const dur = UI._durationSecs(step.started_at, step.finished_at);
    const durTxt = dur === null ? "-" : `${dur}`;

    document.getElementById("modalContainer").innerHTML = `
      <div class="modal" onclick="UI.closeModalOnBackdrop(event)">
        <div class="modal-content modal-wide">
          <div class="section-head">
            <h3 class="section-title">Step: <span class="mono">${step.step_name}</span></h3>
            <button class="btn-secondary" onclick="UI.closeModal()">Close</button>
          </div>

          <div class="summary-grid" style="margin-top:10px;">
            <div><div class="label">Status</div>${UI._statusBadge((step.status || "").toLowerCase())}</div>
            <div><div class="label">Attempts</div><div>${step.attempts ?? "-"}</div></div>
            <div><div class="label">Started</div><div>${UI._fmtDate(step.started_at)}</div></div>
            <div><div class="label">Finished</div><div>${UI._fmtDate(step.finished_at)}</div></div>
            <div><div class="label">Duration</div><div>${durTxt}</div></div>
          </div>

          ${err ? `<div class="error-panel" style="margin-top:12px;"><div class="error-title">Last Error</div><div class="error-text">${UI._escape(err)}</div></div>` : ""}

          <h3 class="section-title" style="margin-top:16px;">Meta</h3>
          <pre class="pre">${UI._escape(JSON.stringify(meta, null, 2))}</pre>
        </div>
      </div>
    `;
  },

  _renderSystemSummary(ai) {
    const summary = ai?.summary || "";
    const recs = ai?.recommendations || [];

    if (!summary && Array.isArray(recs) && !recs.length) return `<div class="muted">AI not available yet.</div>`;

    const recHtml = recs.length
      ? `<table class="data-table">
          <thead><tr><th>Priority</th><th>Type</th><th>Reason</th></tr></thead>
          <tbody>
            ${recs
        .map(
          (r) => `
              <tr>
                <td>${UI._escape(r.priority || "-")}</td>
                <td>${UI._escape(r.action_type || "-")}</td>
                <td>${UI._escape(r.reason_text || "-")}</td>
              </tr>`
        )
        .join("")}
          </tbody>
        </table>`
      : `<div class="muted">No recommendations yet.</div>`;
    console.log('...summary', typeof summary)
    return `
      ${`<div class="section-card" style="margin-bottom:12px;"><div class="label">Summary</div><div>${summary && typeof summary !== "object" ? UI._escape(summary) : 'No Summary'}</div></div>${recHtml}`}
    `;
  },

  _renderAI(sys) {
    const obj = sys || {};
    const keys = Object.keys(obj);
    if (!keys.length) return `<div class="muted">No system summary yet.</div>`;

    const rows = keys
      .map((k) => `<tr><td class="mono">${UI._escape(k)}</td><td>${obj[k] ? UI._escape(String(obj[k])): 'Empty'}</td></tr>`)
      .join("");

    return `
      <table class="data-table">
        <thead><tr><th>Key</th><th>Value</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  _statusBadge(status) {
    const s = (status || "queued").toLowerCase();
    return `<span class="status-badge status-${s}">${s}</span>`;
  },

  _escape(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  },
};

// store last payload for step modal
const _origLoad = UI._loadRunDashboard.bind(UI);
UI._loadRunDashboard = async (runId, opts) => {
  const before = Date.now();
  // call original
  await (async () => {
    let data;
    try {
      data = await API.getRunDashboard(runId);
      window.__LAST_RUN_DASHBOARD__ = data;
    } catch (e) {
      if (!opts?.silent) Toast.error(e.message || "Failed to load run");
      return;
    }

    // re-use logic by injecting into original rendering pipeline:
    // we’ll mimic original _loadRunDashboard by temporarily calling internal render function inline
    const run = data.run;
    const steps = (data.steps || []).map((s) => ({ ...s, step_name: s.step_name || s.step || s.name }));

    const counts = UI._countSteps(steps);
    const current = UI._currentStep(steps);

    document.getElementById("metricsBar").innerHTML = `
      <div class="metric-card"><p>Status</p><h3>${run.status}</h3></div>
      <div class="metric-card"><p>Steps</p><h3>${steps.length}</h3></div>
      <div class="metric-card"><p>Running</p><h3>${counts.running}</h3></div>
      <div class="metric-card"><p>Failed</p><h3>${counts.failed}</h3></div>
    `;

    document.getElementById("runSummary").innerHTML = UI._renderRunSummary(run, current);
    document.getElementById("stepTimeline").innerHTML = UI._renderTimeline(steps);
    document.getElementById("runErrorPanel").innerHTML = UI._renderErrorPanel(run, steps);
    document.getElementById("stepsTableWrap").innerHTML = UI._renderStepsTable(steps);
    document.getElementById("aiWrap").innerHTML = UI._renderAI(data.ai);
    document.getElementById("systemWrap").innerHTML = UI._renderSystemSummary(data.system);

    const terminal = ["success", "failed", "canceled"];
    if (terminal.includes((run.status || "").toLowerCase())) UI._stopRunPolling();
  })();

  const after = Date.now();
  // (optional) you can log load time: console.log("run load ms", after-before)
};