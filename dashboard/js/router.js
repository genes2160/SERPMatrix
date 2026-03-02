// js/router.js
const Router = {
    go(view) {
        window.location.hash = view;
    },

    parseHash() {
        const h = (window.location.hash || "#overview").replace("#", "");
        if (h.startsWith("run:")) return { view: "run", runId: h.split("run:")[1] };
        return { view: h };
    },

    async loadFromHash() {
        const { view, runId } = this.parseHash();

        // active button highlight
        document.querySelectorAll(".sidebar button[data-view]").forEach((b) => {
            b.classList.toggle("active", b.dataset.view === view);
        });

        if (view === "overview") return UI.renderOverview();
        if (view === "sites") return UI.renderSites();
        if (view === "health") return UI.renderHealth();
        if (view === "run") return UI.renderRunDashboard(runId);

        // fallback
        return UI.renderOverview();
    },
};

window.addEventListener("hashchange", () => Router.loadFromHash());