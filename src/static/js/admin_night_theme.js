(() => {
    "use strict";
    const root = document.documentElement;
    const previousBootstrapTheme = root.getAttribute("data-bs-theme");
    let timer;
    function update() {
        clearTimeout(timer);
        const now = new Date();
        const hour = now.getHours(), dark = hour >= 23 || hour < 5;
        root.toggleAttribute("data-admin-night-theme", dark);
        if (dark) root.setAttribute("data-bs-theme", "dark");
        else if (previousBootstrapTheme === null) root.removeAttribute("data-bs-theme");
        else root.setAttribute("data-bs-theme", previousBootstrapTheme);
        const boundary = new Date(now.getFullYear(), now.getMonth(), now.getDate() + (hour >= 22 ? 1 : 0), dark ? 5 : 22);
        timer = setTimeout(update, Math.max(1, Math.min(60000, boundary - now)));
    }
    update();
    window.addEventListener("focus", update);
    window.addEventListener("pageshow", update);
    document.addEventListener("visibilitychange", update);
})();
