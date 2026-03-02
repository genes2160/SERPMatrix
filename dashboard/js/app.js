// js/app.js
document.querySelectorAll(".sidebar button[data-view]").forEach((btn) => {
    btn.onclick = () => Router.go(btn.dataset.view);
});

document.getElementById("logoutBtn").onclick = () => {
    localStorage.removeItem("access_token");
    window.location.href = "index.html";
};

Router.loadFromHash();