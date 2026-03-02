function renderStepTimeline(steps = []) {
    const container = document.getElementById("stepsContainer");
    container.innerHTML = "";

    const maxDuration = Math.max(...steps.map(s => s.duration_seconds || 1), 1);

    steps.forEach(step => {
        const percent = ((step.duration_seconds || 0) / maxDuration) * 100;

        const div = document.createElement("div");
        div.className = `timeline-step step-${step.status.toLowerCase()}`;

        div.innerHTML = `
            <div class="timeline-header">
                <strong>${step.step_name}</strong>
                <span>${step.duration_seconds || 0}s</span>
            </div>
            <div class="timeline-bar">
                <div class="timeline-fill" style="width:${percent}%"></div>
            </div>
        `;

        if (step.status === "FAILED") {
            div.onclick = () => alert(step.error_message || "Unknown error");
        }

        container.appendChild(div);
    });
}