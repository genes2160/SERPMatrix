const Notifications = (() => {
    const POLL_INTERVAL_MS = 10000; // 10 seconds
    const MAX_DISPLAY = 20;

    let pollTimer = null;
    let currentRunId = null;
    let allNotifications = [];

    // ── DOM refs ──────────────────────────────────────────────
    const btn = () => document.getElementById("notifBtn");
    const badge = () => document.getElementById("notifBadge");
    const dropdown = () => document.getElementById("notifDropdown");
    const list = () => document.getElementById("notifList");
    const markAllBtn = () => document.getElementById("markAllRead");
    const wrapper = () => document.getElementById("notifWrapper");
    // ── General (user-wide) notifications ────────────────────────
    async function fetchGeneral() {
        try {
            const data = await API.getAllNotifications(); // new endpoint
            allNotifications = data || [];
            render(allNotifications);
            updateBadge(allNotifications);
        } catch (err) {
            console.warn("[Notifications] General fetch failed:", err);
        }
    }
    // ── Public: set which run to poll ─────────────────────────
    function watchRun(runId) {
        console.log("...running....notifications", runId)
        currentRunId = runId;
        allNotifications = [];
        render([]);
        stopPolling();
        startPolling();
    }

    function stopWatching() {
        currentRunId = null;
        stopPolling();
    }

    // ── Polling ───────────────────────────────────────────────
    function startPolling() {
        if (!currentRunId) return;
        fetchAndRender(); // immediate first fetch
        pollTimer = setInterval(fetchAndRender, POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    async function fetchAndRender() {
        if (!currentRunId) return;
        try {
            const data = await API.getNotifications(currentRunId);
            allNotifications = data || [];
            render(allNotifications);
            updateBadge(allNotifications);

            // stop polling once run is complete or failed
            const terminal = allNotifications.find(n =>
                n.event_type === "run_complete" || n.event_type === "run_failed"
            );
            if (terminal) stopPolling();

        } catch (err) {
            console.warn("[Notifications] Poll failed:", err);
        }
    }

    // ── Render ────────────────────────────────────────────────
    function render(notifications) {
        const el = list();
        if (!el) return;

        if (!notifications.length) {
            el.innerHTML = `<div class="notif-empty">No notifications yet</div>`;
            return;
        }

        el.innerHTML = notifications
            .slice(0, MAX_DISPLAY)
            .map(n => notifItem(n))
            .join("");
    }

    function notifItem(n) {
        const icon = eventIcon(n.event_type);
        const time = formatTime(n.created_at);
        const unread = !n.read ? "unread" : "";

        return `
            <div class="notif-item ${unread}" data-id="${n.id}">
                <span class="notif-icon">${icon}</span>
                <div class="notif-content">
                    <div class="notif-title">${escapeHtml(n.title)}</div>
                    <div class="notif-body">${escapeHtml(n.body)}</div>
                    <div class="notif-time">${time}</div>
                </div>
            </div>
        `;
    }

    function updateBadge(notifications) {
        const unreadCount = notifications.filter(n => !n.read).length;
        const b = badge();
        if (!b) return;

        if (unreadCount > 0) {
            b.textContent = unreadCount > 99 ? "99+" : unreadCount;
            b.classList.remove("hidden");
        } else {
            b.classList.add("hidden");
        }
    }

    // ── Toggle dropdown ───────────────────────────────────────
    function toggle() {
        const d = dropdown();
        if (!d) return;
        d.classList.toggle("hidden");
    }

    function close() {
        dropdown()?.classList.add("hidden");
    }

    // ── Mark all read ─────────────────────────────────────────
    async function markAllAsRead() {
        const unread = allNotifications.filter(n => !n.read);
        await Promise.allSettled(
            unread.map(async (n) => await API.markNotificationRead(n.id))
        );
        allNotifications = allNotifications.map(n => ({ ...n, read: true }));
        render(allNotifications);
        updateBadge(allNotifications);
    }

    // ── Helpers ───────────────────────────────────────────────
    function eventIcon(type) {
        const icons = {
            run_started: "🚀",
            step_success: "✅",
            step_failed: "❌",
            run_complete: "🎉",
            run_failed: "🔴",
        };
        return icons[type] || "🔔";
    }

    function formatTime(iso) {
        if (!iso) return "";
        const d = new Date(iso);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return "just now";
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        return d.toLocaleDateString();
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // ── Event listeners ───────────────────────────────────────
    async function init() {
        await fetchGeneral(); // ← auto-load on page load
        document.addEventListener("click", (e) => {
            const w = wrapper();
            if (w && !w.contains(e.target)) {
                close(); // click outside → close
            }
        });

        document.addEventListener("click", (e) => {
            if (e.target.closest("#notifBtn")) {
                toggle();
            }
        });

        document.addEventListener("click", (e) => {
            if (e.target.closest("#markAllRead")) {
                markAllAsRead();
            }
        });
    }

    return { init, watchRun, stopWatching };
})();

// when user opens a run dashboard:
// 

// when user navigates away:
// Notifications.stopWatching();

// on page init:
Notifications.init();