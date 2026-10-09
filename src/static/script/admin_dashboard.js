(() => {
    const dataRoot = document.getElementById("adminData");
    if (!dataRoot) return;
    const stats = JSON.parse(dataRoot.dataset.stats);
    const el = id => document.getElementById(id);
    const empty = (id, text) => { const container = el(id); if (container) { container.classList.add("admin-empty"); container.textContent = text; } };
    const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    async function plot(id, traces, yTitle) {
        if (!traces.length || !traces.some(trace => trace.x.length)) { empty(id, "Za ta pregled še ni podatkov."); return; }
        if (!window.Plotly) { empty(id, "Grafa ni mogoče naložiti. Podatke preglej v tabelah ali osveži stran."); return; }
        el(id).classList.remove("admin-empty");
        try {
            await Plotly.newPlot(el(id), traces, {
                margin: { t: 65, b: 45, l: 45, r: 20 }, font: { family: "system-ui, sans-serif", size: 11, color: "#536779" },
                paper_bgcolor: "transparent", plot_bgcolor: "transparent", colorway: ["#29757b", "#d89c45", "#647ad0", "#589775"],
                legend: { orientation: "h", x: 0, y: 1.15 }, hovermode: "x unified",
                xaxis: { gridcolor: "#edf1f5", automargin: true }, yaxis: { title: { text: yTitle }, gridcolor: "#edf1f5", rangemode: "tozero", automargin: true },
            }, { responsive: true, displayModeBar: false, scrollZoom: false });
        } catch (_error) { empty(id, "Graf trenutno ni na voljo. Osveži stran ali uporabi podatke v tabelah."); }
    }
    const monthly = stats.accessMonthly || {};
    const months = Object.keys(monthly).sort();
    const routes = [...new Set(Object.values(monthly).flatMap(month => Object.keys(month)))];
    plot("access-monthly-graph", routes.map(route => ({ x: months, y: months.map(month => monthly[month][route] || 0), name: escape(route), mode: "lines+markers", type: "scatter" })), "Dostopi");
    function plotUsers() {
        const status = el("accessStatus").value;
        const dates = Object.keys(stats.accessUsers[status] || {}).sort();
        const traces = (stats.users || []).map(user => ({
            x: dates, y: dates.map(date => stats.accessUsers[status][date][user]?.count || 0),
            text: dates.map(date => escape(stats.accessUsers[status][date][user]?.routes || "").replace(/\n/g, "<br>")),
            name: escape(user), mode: "lines+markers", type: "scatter",
            hovertemplate: "%{x}<br>Dostopi: %{y}<br>%{text}<extra>%{fullData.name}</extra>",
        })).filter(trace => trace.y.some(value => value > 0));
        plot("access-user-graph", traces, "Dostopi");
    }
    plotUsers(); el("accessStatus").disabled = !el("accessStatus").options.length;
    el("accessStatus").addEventListener("change", plotUsers);
    const blogTraces = [["Vsi ogledi", stats.blogDaily || {}], ["Slovenija", stats.blogSiDaily || {}]].map(([name, values]) => ({ x: Object.keys(values).sort(), y: Object.keys(values).sort().map(date => values[date]), name, mode: "lines+markers", type: "scatter" }));
    plot("blog-views-graph", blogTraces, "Ogledi");
    if (el("geo-map")) {
        if (!window.L) empty("geo-map", "Zemljevida ni mogoče naložiti. Lokacije so prikazane v tabeli.");
        else {
            const map = L.map("geo-map").setView([46.119944, 14.815333], 8);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap contributors" }).addTo(map);
            Object.entries(stats.geoCities || {}).forEach(([city, entry]) => {
                const coords = entry.geolocation;
                if (!Array.isArray(coords) || coords.length < 2 || coords.some(value => !Number.isFinite(Number(value))) || (!Number(coords[0]) && !Number(coords[1]))) return;
                const popup = document.createElement("div");
                const title = document.createElement("strong"); title.textContent = city;
                const count = document.createElement("div"); count.textContent = `Obiskovalci: ${entry.count}`;
                popup.append(title, count); L.marker(coords).addTo(map).bindPopup(popup);
            });
        }
    }
    let goldStarted = false;
    el("goldDetails").addEventListener("toggle", () => {
        if (!el("goldDetails").open || goldStarted) return;
        goldStarted = true;
        const script = document.createElement("script"); script.src = "https://www.bullionvault.com/chart/bullionvaultchart.js";
        script.onerror = () => empty("gold-price-chart", "Graf cene zlata trenutno ni na voljo.");
        script.onload = () => {
            try {
                if (!window.BullionVaultChart) throw new Error("unavailable");
                el("gold-price-chart").replaceChildren();
                new window.BullionVaultChart({ bullion: "gold", currency: "EUR", timeframe: "1y", chartType: "line", miniChartModeAxis: "kg", referrerID: null, containerDefinedSize: true, miniChartMode: false, displayLatestPriceLine: true, switchBullion: false, switchCurrency: false, switchTimeframe: true, switchChartType: false, exportButton: false }, "gold-price-chart");
            } catch (_error) { empty("gold-price-chart", "Graf cene zlata trenutno ni na voljo."); }
        };
        document.head.appendChild(script);
    });

    let comments = [];
    const drafts = new Map();
    let loading = false;
    const responseMessage = (text, error = false) => { el("commentsMessage").textContent = text; el("commentsMessage").hidden = !text; el("commentsMessage").dataset.kind = error ? "error" : "success"; };
    async function loadComments() {
        if (loading) return;
        loading = true; el("refreshComments").disabled = true;
        try {
            const response = await fetch("/movies/get-comments", { cache: "no-store" });
            if (!response.ok) throw new Error("unavailable");
            const data = await response.json();
            if (!Array.isArray(data.comments)) throw new Error("invalid");
            comments = data.comments; renderComments();
        } catch (_error) {
            if (!comments.length) el("comments-container").replaceChildren();
            responseMessage("Komentarjev ni bilo mogoče naložiti. Poskusi z gumbom Osveži.", true);
        }
        finally { loading = false; el("refreshComments").disabled = false; }
    }
    function renderComments() {
        const filter = el("commentFilter").value;
        const visible = comments.filter(comment => filter === "all" || (filter === "answered" ? !!comment.admin_response : !comment.admin_response));
        const container = el("comments-container"); container.replaceChildren();
        if (!visible.length) { const notice = document.createElement("p"); notice.className = "admin-empty mt-3"; notice.textContent = filter === "unanswered" ? "Vsi komentarji imajo odgovor. Ni odprtih vprašanj." : "V tem prikazu ni komentarjev."; container.appendChild(notice); return; }
        visible.forEach(comment => {
            const card = document.createElement("article"); card.className = `admin-comment${comment.admin_response ? " has-response" : ""}`;
            const heading = document.createElement("div"); heading.className = "admin-comment-heading";
            const identity = document.createElement("div"); const author = document.createElement("strong"); author.textContent = comment.author;
            const meta = document.createElement("small"); meta.textContent = `${comment.email || ""} · ${comment.date || ""}`; identity.append(author, meta);
            const movie = document.createElement("a"); movie.href = comment.movie_folder === "Splošno" ? "/suggestions" : `/movies/play${String(comment.movie_folder || "").split("/").map(encodeURIComponent).join("/")}`; movie.textContent = comment.movie_title;
            heading.append(identity, movie); const body = document.createElement("p"); body.textContent = comment.text; card.append(heading, body);
            if (comment.admin_response) { const answer = document.createElement("div"); answer.className = "admin-comment-response"; answer.textContent = `Odgovor: ${comment.admin_response}`; card.appendChild(answer); }
            else {
                const form = document.createElement("form");
                const label = document.createElement("label"); label.className = "form-label"; label.textContent = "Tvoj odgovor";
                const textarea = document.createElement("textarea"); textarea.className = "form-control"; textarea.rows = 3; textarea.required = true; textarea.setAttribute("aria-label", `Odgovor za ${comment.author}`);
                const draftKey = `${comment.movie_folder}:${comment.comment_index}`;
                textarea.value = drafts.get(draftKey) || "";
                textarea.addEventListener("input", () => drafts.set(draftKey, textarea.value));
                const button = document.createElement("button"); button.className = "btn btn-primary"; button.type = "submit"; button.textContent = "Pošlji odgovor";
                const status = document.createElement("div"); status.setAttribute("role", "status"); status.hidden = true;
                form.append(label, textarea, button, status); card.appendChild(form);
                form.addEventListener("submit", async event => {
                    event.preventDefault();
                    if (!textarea.value.trim() || button.disabled) return;
                    button.disabled = true; button.textContent = "Pošiljam …"; status.hidden = true;
                    try {
                        const result = await fetch("/movies/admin-comment", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content }, body: JSON.stringify({ movieFolder: comment.movie_folder, commentIndex: comment.comment_index, response: textarea.value.trim() }) });
                        if (!result.ok) throw new Error("unavailable");
                        const data = await result.json(); if (data.status !== "success") throw new Error(data.message || "unavailable");
                        comment.admin_response = textarea.value.trim(); drafts.delete(draftKey); responseMessage("Odgovor je shranjen."); renderComments(); el("commentFilter").focus();
                    } catch (_error) { status.textContent = "Odgovora ni bilo mogoče poslati. Besedilo je ohranjeno; poskusi znova."; status.className = "admin-notice"; status.dataset.kind = "error"; status.hidden = false; }
                    finally { button.disabled = false; button.textContent = "Pošlji odgovor"; }
                });
            }
            container.appendChild(card);
        });
    }
    el("refreshComments").addEventListener("click", () => { responseMessage(""); loadComments(); });
    el("commentFilter").addEventListener("change", renderComments);
    loadComments();
})();
