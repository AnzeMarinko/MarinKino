
document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("videoPlayer");
    if (!video) return;

    video.addEventListener("dblclick", () => {
        if (!document.fullscreenElement) {
            // Vklopi celozaslonski način
            if (video.requestFullscreen) {
                video.requestFullscreen();
            } else if (video.webkitRequestFullscreen) { // Safari
                video.webkitRequestFullscreen();
            } else if (video.msRequestFullscreen) { // IE11
                video.msRequestFullscreen();
            }
        } else {
            // Izhod iz celozaslonskega načina
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) { // Safari
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) { // IE11
                document.msExitFullscreen();
            }
        }
    });

    // Nastavi interval (v milisekundah)
    const intervalMillis = 20 * 1000;
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    setInterval(() => {
            if (video && !video.paused && !video.ended) {
                fetch("/video-progress", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        filename: video.currentSrc,
                        currentTime: video.currentTime,
                        duration: video.duration
                    })
                }).catch(() => {});
                const selectedButton = document.querySelector('.video-btn.selected');
                if (selectedButton) {
                    selectedButton.style.setProperty('--watch', Math.round(video.currentTime / video.duration * 100) + '%');
                }
            }
        }, intervalMillis);
});
