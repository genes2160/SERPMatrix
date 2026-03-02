document.getElementById("loginBtn").onclick = async () => {
    const loginBtn = document.getElementById("loginBtn");
    try {
        const username = document.getElementById("username").value;
        const password = document.getElementById("password").value;

        setButtonState(loginBtn, false, "Logging in...");
        const data = await API.login(username, password);

        localStorage.setItem("access_token", data.access);

        window.location.href = "app.html";

    } catch (e) {
        document.getElementById("loginError").innerText = e.message;
    } finally {
        setButtonState(loginBtn, true);
    }
};