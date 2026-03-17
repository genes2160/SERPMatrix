// js/router.js
const Router = {
    go(view, { pushState = true, _fromUI = false } = {}) {
        // Update active nav
        document.querySelectorAll(".sidebar nav button").forEach(btn => {
            btn.classList.toggle(
                "active",
                btn.dataset.view === view || (view.startsWith("run:") && btn.dataset.view === "runs")
            );
        });

        // Persist to URL hash
        if (pushState) {
            history.replaceState(null, "", "#" + view);
        }

        // If called from UI.renderRunDashboard directly, skip re-invoking it
        if (_fromUI && view.startsWith("run:")) return;

        // Stop polling only when navigating AWAY from a run view
        if (!view.startsWith("run:") && UI._stopRunPolling) UI._stopRunPolling();

        if (view === "overview") return UI.renderOverview();
        if (view === "sites") return UI.renderSites();
        if (view === "health") return UI.renderHealth();
        if (view === "runs") return UI.renderRunHistory();
        if (view === "recommendations") return UI.renderRecommendations();
        if (view === "keywords") return UI.renderKeywords();
        if (view.startsWith("run:")) return UI.renderRunDashboard(view.slice(4));

        return UI.renderOverview();
    }
};

document.addEventListener("DOMContentLoaded", () => {
    // Wire sidebar buttons
    document.querySelectorAll(".sidebar nav button").forEach(btn => {
        btn.addEventListener("click", () => Router.go(btn.dataset.view));
    });

    // On load: restore from hash, else default to overview
    const hash = location.hash.slice(1);
    Router.go(hash || "overview", { pushState: true });
});