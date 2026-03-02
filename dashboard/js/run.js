// run.js

async function loadRun() {
    try {
        const data = await API.getRunDashboard(State.runId);
        State.data = data;

        renderRunStatus(data.run);
        renderStepTimeline(data.steps); // ← changed
        renderAISummary(data.ai?.summary);
        renderAIRecommendations(data.ai?.recommendations || []);
        renderMetrics(data.system_summary);
        renderMetricsChart(data.system_summary);

        if (data.run.status === "RUNNING") {
            startPolling();
        } else {
            stopPolling();
        }

    } catch (err) {
        console.error(err);
        stopPolling();
    }
}
function stopPolling() {
    if (State.pollingInterval) {
        clearInterval(State.pollingInterval);
        State.pollingInterval = null;
    }
}

function startPolling() {
    if (State.pollingInterval) return;

    State.pollingInterval = setInterval(async () => {
        await loadRun();
    }, 5000);
}

function stopPolling() {
    if (State.pollingInterval) {
        clearInterval(State.pollingInterval);
        State.pollingInterval = null;
    }
}

function init() {
    const params = new URLSearchParams(window.location.search);
    State.runId = params.get("run_id");

    if (!State.runId) {
        alert("Missing run_id");
        return;
    }

    loadRun();
    document.getElementById("retryBtn").onclick = async () => {
        API.retryRun(State.runId, { method: "POST" });
        stopPolling();
        loadRun();
    };
}
async function loadHealth() {
    const res = await fetch("/api/health/");
    const data = await res.json();

    document.getElementById("healthWidget").innerText =
        `DB: ${data.services.database} | Redis: ${data.services.redis}`;
}
document.addEventListener("DOMContentLoaded", init);