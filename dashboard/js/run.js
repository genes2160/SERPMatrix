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
function getRunIdFromHash() {
    const hash = window.location.hash; // "#run:0476f2a5-518c-45bb-b616-69ae4c4fe3a7"
    if (!hash.startsWith("#run:")) return null;
    return hash.replace("#run:", "");
}
function init() {
    const params = new URLSearchParams(window.location.search);
    State.runId = params.get("run_id");
    // ← ADD: start watching if page loads on a run URL
    State.runId = getRunIdFromHash();
    if (State.runId) Notifications.watchRun(State.runId);

    if (!State.runId) {
        console.log("Missing run_id");
        return;
    }

    // loadRun();
    Notifications.watchRun(State.runId);
    // document.getElementById("retryBtn").onclick = async () => {
    //     API.retryRun(State.runId, { method: "POST" });
    //     stopPolling();
    //     loadRun();
    // };
}
async function loadHealth() {
    const res = await fetch("/api/health/");
    const data = await res.json();

    document.getElementById("healthWidget").innerText =
        `DB: ${data.services.database} | Redis: ${data.services.redis}`;
}
document.addEventListener("DOMContentLoaded", init);