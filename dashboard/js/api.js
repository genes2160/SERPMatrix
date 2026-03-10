// js/api.js
const API_BASE = "http://localhost:8000/api";

function setButtonState(button, enabled, loadingText = "Loading...") {
    if (!button) return;

    if (enabled) {
        button.disabled = false;
        button.dataset.originalText && (button.innerText = button.dataset.originalText);
    } else {
        button.dataset.originalText = button.innerText;
        button.disabled = true;
        button.innerText = loadingText;
    }
}

const API = {
    async login(username, password) {
        try {
            const res = await fetch(`${API_BASE}/auth/login/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });

            if (!res.ok) {
                throw new Error("Invalid credentials");
            }

            return await res.json();

        } catch (error) {
            console.error("Login request failed", error);

            // Try health check fallback
            try {
                const healthRes = await fetch(`${API_BASE}/health/`);
                const healthData = await healthRes.json();

                return {
                    error: true,
                    fallback: "healthcheck",
                    health: healthData,
                };

            } catch {
                throw new Error("Backend unreachable");
            }
        }
    },

    async getSites() {
        return this.authFetch(`/sites`);
    },

    async createRun(siteId) {
        return this.authFetch(`/sites/${siteId}/runs`, { method: "POST" });
    },

    async getRunDashboard(runId) {
        return this.authFetch(`/runs/${runId}/dashboard`);
    },

    retryRun: (runId, force = false) =>
        API.authFetch(`/runs/${runId}/retry`, {
            method: "POST",
            body: JSON.stringify({ force }),
        }),

    async getHealth() {
        const res = await fetch(`${API_BASE}/health/`);
        return res.json();
    },

    async authFetch(path, options = {}) {
        const token = localStorage.getItem("access_token");

        try {
            const res = await fetch(`${API_BASE}${path}`, {
                ...options,
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                    ...(options.headers || {}),
                },
            });

            if (res.status === 401) {
                localStorage.removeItem("access_token");
                window.location.href = "index.html";
                return;
            }

            if (!res.ok) {
                let msg = "API Error";
                try {
                    const data = await res.json();
                    msg = data?.detail || data?.message || msg;
                } catch (error) {
                    if (error instanceof TypeError) {
                        console.log("Network-level failure XXX");
                    }
                }
                throw new Error(msg);
            }

            return await res.json();

        } catch (error) {
            if (error instanceof TypeError) {
                console.log("Network-level failure");
            }
            console.error("Primary API failed. Checking health...", error);

            // 🔍 Fallback health check
            try {
                const healthRes = await fetch(`${API_BASE}/health/`);
                const healthData = await healthRes.json();

                return {
                    error: true,
                    fallback: "healthcheck",
                    health: healthData,
                };

            } catch (healthError) {
                console.error("Health check also failed", healthError);
                throw new Error("Backend completely unreachable");
            }
        }
    },// add inside the API object, alongside getSites, createRun etc:

    async getNotifications(runId) {
        return this.authFetch(`/runs/${runId}/notifications`);
    },
    async getAllNotifications() {
        return this.authFetch("/notifications")
    },
    async markNotificationRead(notificationId) {
        return this.authFetch(`/notifications/${notificationId}/read`, {
            method: "PATCH",
        });
    },
};