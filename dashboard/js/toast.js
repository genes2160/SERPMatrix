const Toast = {
    show(message, type) {
        const container = document.getElementById("toastContainer");

        const div = document.createElement("div");
        div.className = `toast toast-${type}`;
        div.innerText = message;

        container.appendChild(div);

        setTimeout(() => div.remove(), 3000);
    },
    success(msg) { this.show(msg, "success"); },
    error(msg) { this.show(msg, "error"); }
};