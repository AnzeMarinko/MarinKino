(() => {
    "use strict";
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (zone) document.cookie = `marinkino_device_timezone=${encodeURIComponent(zone)}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    const path = location.pathname;
    if (path === "/blog" || path.startsWith("/blog/") || path === "/admin/blog" || path.startsWith("/admin/blog/")) return;
    if (path === "/admin/fitness" || path.startsWith("/admin/fitness/") || ["/login", "/logout", "/welcome", "/admin/clear-view-as"].includes(path) || path.startsWith("/password/")) return;

    let timer, redirecting = false;
    function check() {
        clearTimeout(timer);
        const now = new Date();
        if (now.getHours() < 6) {
            if (!redirecting) {
                redirecting = true;
                document.querySelectorAll("audio, video").forEach(media => media.pause());
                location.replace("/admin/fitness/night-lock");
            }
            return;
        }
        const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        const warningAt = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 50);
        let banner = document.getElementById("admin-night-warning");
        if (now >= warningAt && document.body) {
            // Native video fullscreen cannot display an HTML warning overlay.
            if (document.fullscreenElement?.matches("video, audio")) {
                document.exitFullscreen().catch(() => {});
            }
            document.querySelectorAll("video").forEach(video => {
                if (video.webkitDisplayingFullscreen && typeof video.webkitExitFullscreen === "function") video.webkitExitFullscreen();
            });
            if (!banner) {
                banner = document.createElement("div");
                banner.id = "admin-night-warning";
                banner.setAttribute("role", "alert");
                banner.style.cssText = "position:fixed;bottom:0;left:0;right:0;z-index:2147483647;background:#fff3cd;color:#664d03;padding:16px 20px;text-align:center;font:600 16px/1.5 system-ui;box-shadow:0 -2px 12px #0002";
            }
            const host = document.fullscreenElement || document.body;
            if (banner.parentElement !== host) host.appendChild(banner);
            const minutes = Math.ceil((midnight - now) / 60000);
            banner.textContent = `Nočni počitek: zaklep ob 00:00 čez ${minutes} min. Filmi, glasba in druge razvedrilne vsebine bodo zaklenjene do 06:00; Gibanje in blog ostaneta dostopna.`;
        } else if (banner) banner.remove();
        const boundary = now < warningAt ? warningAt : midnight;
        timer = setTimeout(check, Math.max(1, Math.min(60000, boundary - now)));
    }
    check();
    document.addEventListener("DOMContentLoaded", check);
    document.addEventListener("visibilitychange", check);
    document.addEventListener("fullscreenchange", check);
    window.addEventListener("focus", check);
    window.addEventListener("pageshow", check);
})();
