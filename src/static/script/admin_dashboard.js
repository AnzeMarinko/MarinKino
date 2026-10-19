(() => {
    const dataRoot = document.getElementById("adminData");
    if (!dataRoot) return;
    const stats = JSON.parse(dataRoot.dataset.stats);
    const el = id => document.getElementById(id);
    const empty = (id, text) => { const container = el(id); if (container) { container.classList.add("admin-empty"); container.textContent = text; } };
    const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    const colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#637939", "#8c6d31", "#843c39", "#7b4173", "#3182bd", "#e6550d", "#31a354", "#756bb1", "#636363"];
    const appearance = index => ({ line: { color: colors[index % colors.length], width: 2.5 }, marker: { color: colors[index % colors.length], size: 5 } });
    // Keep only non-zero points plus the neighbouring zero periods, so a lone point still draws a curve.
    // The following zero is omitted when it is the current (incomplete) period.
    const nonZero = (xs, ys, extra = {}) => {
        const monthly = xs.length > 0 && String(xs[0]).length === 7;
        const now = new Date(), pad = value => String(value).padStart(2, "0");
        const current = monthly ? `${now.getFullYear()}-${pad(now.getMonth() + 1)}` : `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
        const shift = (value, step) => {
            const date = new Date(Date.parse(monthly ? `${value}-01T00:00:00Z` : `${value}T00:00:00Z`));
            if (monthly) date.setUTCMonth(date.getUTCMonth() + step); else date.setUTCDate(date.getUTCDate() + step);
            return date.toISOString().slice(0, monthly ? 7 : 10);
        };
        const index = new Map(xs.map((value, position) => [value, position]));
        const points = new Set();
        xs.forEach((value, position) => {
            if (!(ys[position] > 0)) return;
            points.add(value); points.add(shift(value, -1));
            const next = shift(value, 1);
            if (next < current) points.add(next);
        });
        const keys = [...points].sort();
        const result = { x: keys, y: keys.map(key => index.has(key) ? ys[index.get(key)] : 0) };
        Object.entries(extra).forEach(([name, values]) => { result[name] = keys.map(key => index.has(key) ? values[index.get(key)] : ""); });
        return result;
    };
    const fillSelect = (id, allLabel, options) => {
        const select = el(id);
        select.replaceChildren(new Option(allLabel, ""), ...options.map(([value, label]) => new Option(label, value)));
        select.disabled = !options.length;
    };
    async function plot(id, traces, yTitle, layout = {}) {
        traces = traces.filter(trace => trace.x.length);
        if (!traces.length) { empty(id, "Za ta pregled še ni podatkov."); return; }
        if (!window.Plotly) { empty(id, "Grafa ni mogoče naložiti. Podatke preglej v tabelah ali osveži stran."); return; }
        el(id).classList.remove("admin-empty");
        try {
            await Plotly.newPlot(el(id), traces, {
                margin: { t: 65, b: 45, l: 45, r: 20 }, font: { family: "system-ui, sans-serif", size: 11, color: "#536779" },
                paper_bgcolor: "transparent", plot_bgcolor: "transparent", colorway: colors,
                legend: { orientation: "h", x: 0, y: 1.15 }, hovermode: "closest", dragmode: "pan",
                xaxis: { gridcolor: "#edf1f5", automargin: true, ...layout.xaxis },
                yaxis: { title: { text: yTitle }, gridcolor: "#edf1f5", rangemode: "tozero", automargin: true, ...layout.yaxis },
            }, {
                responsive: true, displaylogo: false, scrollZoom: false, displayModeBar: true,
                modeBarButtons: [["zoom2d", "pan2d"], ["zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"]],
            });
        } catch (_error) { empty(id, "Graf trenutno ni na voljo. Osveži stran ali uporabi podatke v tabelah."); }
    }
    const monthly = stats.accessMonthly || {};
    const months = Object.keys(monthly).sort();
    const routeTotals = {};
    Object.values(monthly).forEach(month => Object.entries(month).forEach(([route, count]) => { routeTotals[route] = (routeTotals[route] || 0) + count; }));
    const routes = Object.keys(routeTotals).filter(route => routeTotals[route] > 0).sort((a, b) => routeTotals[b] - routeTotals[a]);
    fillSelect("accessRoute", `Najpogostejše poti (${Math.min(routes.length, 8)})`, routes.map(route => [route, `${route} · ${routeTotals[route]}`]));
    function plotMonthly() {
        const chosen = el("accessRoute").value;
        const shown = chosen ? [chosen] : routes.slice(0, 8);
        plot("access-monthly-graph", shown.map(route => ({ ...appearance(routes.indexOf(route)), ...nonZero(months, months.map(month => monthly[month][route] || 0)), name: escape(route), mode: "lines+markers", type: "scatter" })), "Dostopi");
    }
    plotMonthly(); el("accessRoute").addEventListener("change", plotMonthly);
    const accessUsers = (stats.users || []).filter(user => Object.values(stats.accessUsers || {}).some(byDate => Object.values(byDate).some(row => row[user]?.count > 0)));
    fillSelect("accessUser", "Vsi uporabniki", accessUsers.map(user => [user, user]));
    function plotUsers() {
        const status = el("accessStatus").value;
        const user = el("accessUser").value;
        const dates = Object.keys(stats.accessUsers[status] || {}).sort();
        const traces = (user ? [user] : accessUsers).map(name => {
            const rows = dates.map(date => stats.accessUsers[status][date][name]);
            return {
                ...appearance(stats.users.indexOf(name)),
                ...nonZero(dates, rows.map(row => row?.count || 0), { text: rows.map(row => escape(row?.routes || "").replace(/\n/g, "<br>")) }),
                name: escape(name), mode: "lines+markers", type: "scatter",
                hovertemplate: "%{x} · %{fullData.name}<br>Dostopi: %{y}<br>%{text}<extra></extra>",
            };
        });
        plot("access-user-graph", traces, "Dostopi");
    }
    plotUsers(); el("accessStatus").disabled = !el("accessStatus").options.length;
    el("accessStatus").addEventListener("change", plotUsers);
    el("accessUser").addEventListener("change", plotUsers);
    const blogTraces = [["Vsi ogledi", stats.blogDaily || {}], ["Slovenija", stats.blogSiDaily || {}]].map(([name, values], index) => {
        const dates = Object.keys(values).sort();
        return { ...appearance(index), ...nonZero(dates, dates.map(date => values[date])), name, mode: "lines+markers", type: "scatter" };
    });
    plot("blog-views-graph", blogTraces, "Ogledi");
    const dayNumber = value => Math.floor(Date.parse(`${String(value).slice(0, 10)}T00:00:00Z`) / 86400000);
    const posts = Object.entries(stats.blogPosts || {}).filter(([, post]) => Object.entries(post.views).some(([date, count]) => count > 0 && Number.isFinite(dayNumber(date))));
    fillSelect("blogPostSelect", "Vse objave", posts.map(([id, post]) => [id, post.title]));
    function plotBlogGrowth() {
        const chosen = el("blogPostSelect").value;
        const maxDays = 1023, todayDay = dayNumber(new Date().toISOString());
        const traces = posts.filter(([id]) => !chosen || id === chosen).map(([id, post], index) => {
            const firstView = Math.min(...Object.entries(post.views).filter(([, count]) => count > 0).map(([date]) => dayNumber(date)));
            const perDay = {};
            Object.entries(post.views).forEach(([date, count]) => { const day = dayNumber(date) - firstView; perDay[day] = (perDay[day] || 0) + count; });
            const start = firstView;
            const last = Math.min(maxDays, Math.max(todayDay - start, ...Object.keys(perDay).map(Number)));
            const x = [], y = [], text = [];
            let total = 0;
            for (let day = 0; day <= last; day++) {
                total += perDay[day] || 0;
                if (total > 0) { x.push(Math.log2(day + 1)); y.push(Math.sqrt(total)); text.push(`dan ${day + 1} · skupaj ${total} ogledov`); }
            }
            return { ...appearance(posts.findIndex(([otherId]) => otherId === id)), x, y, text, name: escape(post.title), mode: "lines", type: "scatter", hovertemplate: "%{text}<extra>%{fullData.name}</extra>" };
        });
        const yMax = Math.max(0, ...traces.flatMap(trace => trace.y));
        const maxViews = yMax ** 2;
        const yTickCount = Math.max(2, Math.min(10, Math.floor(maxViews) + 1));
        const yTickLabels = Array.from(
            { length: yTickCount },
            (_, index) => Math.round((maxViews * index) / (yTickCount - 1)),
        );
        plot("blog-growth-graph", traces, "Skupaj ogledov", {
            xaxis: {
                type: "linear",
                title: { text: "Dnevi od prvega ogleda" },
                range: [0, 10],
                tickvals: Array.from({ length: 11 }, (_, index) => index),
                ticktext: Array.from({ length: 11 }, (_, index) => String(2 ** index)),
            },
            yaxis: {
                type: "linear",
                rangemode: "tozero",
                range: [0, yMax],
                tickvals: yTickLabels.map(value => Math.sqrt(value)),
                ticktext: yTickLabels.map(value => value.toLocaleString("sl-SI")),
            },
        });
    }
    plotBlogGrowth(); el("blogPostSelect").addEventListener("change", plotBlogGrowth);
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
