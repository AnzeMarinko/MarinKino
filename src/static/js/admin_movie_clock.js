(() => {
    "use strict";
    const configNode = document.getElementById("admin-movie-timing");
    const warning = document.getElementById("admin-movie-duration-warning");
    if (!configNode || !warning) return;
    const config = JSON.parse(configNode.textContent);
    const filmVideo = () => document.getElementById("videoPlayer") || document.getElementById("hlsVideoPlayer") || document.querySelector(".plyr-container video");
    let timer;

    function update() {
        clearTimeout(timer);
        const video = filmVideo();
        const selected = document.querySelector(".video-btn.selected");
        const measured = video && Number.isFinite(video.duration) && video.duration > 0;
        const minutes = selected ? Number(selected.dataset.runtimeMin) : Number(config.duration_min);
        const duration = measured ? video.duration : minutes * 60;
        const saved = selected ? Number(selected.dataset.resumeSeconds) : Number(config.resume_seconds);
        const position = measured ? video.currentTime : (Number.isFinite(saved) && saved > 0 && saved < duration ? saved : 0);
        const rate = video && Number.isFinite(video.playbackRate) && video.playbackRate > 0 ? video.playbackRate : 1;
        const remaining = Math.max(0, duration - position) / rate;
        const now = new Date();
        const limit = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 45);
        const finish = new Date(now.getTime() + remaining * 1000);
        const late = video && (!config.collection || selected) && Number.isFinite(remaining) && remaining > 0 && finish > limit;
        warning.hidden = !late;
        if (late) {
            const time = finish.toLocaleString("sl-SI", { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
            warning.textContent = `Predvideni konec filma: ${time} po uri naprave, kar presega 23:45. Stran se ob polnoči zapre in te preusmeri na Gibanje. Izračun upošteva preostali čas in hitrost predvajanja, brez dodatnih postankov.`;
        }
        timer = setTimeout(update, 60000);
    }

    ["loadedmetadata", "durationchange", "play", "pause", "seeked", "ratechange", "ended", "emptied"].forEach(type => {
        document.addEventListener(type, event => {
            if (event.target === filmVideo()) queueMicrotask(update);
        }, true);
    });
    document.addEventListener("click", event => {
        if (event.target.closest(".video-btn")) queueMicrotask(update);
    });
    document.addEventListener("visibilitychange", update);
    window.addEventListener("focus", update);
    window.addEventListener("pageshow", update);
    update();
})();
