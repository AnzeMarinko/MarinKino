(() => {
    const root = document.getElementById("weather-root");
    if (!root) return;
    const weather = JSON.parse(root.dataset.weather || "{}");
    const el = id => document.getElementById(id);
    const graph = el("weatherChart");
    const cookieName = "marinkino_weather_locations";
    const weekdays = ["nedelja", "ponedeljek", "torek", "sreda", "četrtek", "petek", "sobota"];
    const hasCoordinates = location => location && location.lat !== null && location.lon !== null
        && location.lat !== "" && location.lon !== "" && Number.isFinite(Number(location.lat)) && Number.isFinite(Number(location.lon))
        && Math.abs(Number(location.lat)) <= 90 && Math.abs(Number(location.lon)) <= 180;
    const locationKey = location => `${Number(location.lat).toFixed(4)},${Number(location.lon).toFixed(4)}`;
    const validLocation = location => hasCoordinates(location) && typeof location.name === "string" && location.name.trim()
        && !["trenutna lokacija", "moja lokacija"].includes(location.name.toLowerCase());

    function localClock() {
        const options = { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", hour12: false };
        if (weather.timezone && weather.timezone !== "auto") options.timeZone = weather.timezone;
        try { el("weatherCurrentEpochSeconds").textContent = new Intl.DateTimeFormat("sl-SI", options).format(new Date()); }
        catch (_error) { el("weatherCurrentEpochSeconds").textContent = weather.current?.time?.replace("T", " · ") || "Čas ni na voljo"; }
    }
    localClock();
    setInterval(localClock, 30000);

    function readLocations() {
        try {
            const cookie = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith(`${cookieName}=`));
            const locations = JSON.parse(decodeURIComponent(cookie?.slice(cookieName.length + 1) || "[]"));
            return Array.isArray(locations) ? locations.filter(validLocation).slice(0, 8) : [];
        } catch (_error) { return []; }
    }

    function writeLocations(locations) {
        document.cookie = `${cookieName}=${encodeURIComponent(JSON.stringify(locations.slice(0, 8)))}; max-age=31536000; path=/; samesite=lax`;
    }

    function renderLocations() {
        const container = el("savedLocations");
        container.replaceChildren();
        const locations = readLocations();
        if (!locations.length) {
            const hint = document.createElement("span"); hint.className = "weather-source";
            hint.textContent = "Poišči prvi kraj. Tukaj ga boš naslednjič odprl z enim klikom.";
            container.appendChild(hint);
        }
        locations.forEach(location => {
            const chip = document.createElement("span"); chip.className = "saved-location-chip";
            const link = document.createElement("a"); link.className = "saved-location";
            link.href = `/weather?${new URLSearchParams({ location: location.name, lat: location.lat, lon: location.lon })}`;
            link.innerHTML = '<i class="bi bi-geo-alt" aria-hidden="true"></i><span></span>';
            link.querySelector("span").textContent = location.name;
            if (location.name === weather.location && Math.abs(Number(location.lat) - Number(weather.latitude)) < .1 && Math.abs(Number(location.lon) - Number(weather.longitude)) < .1) {
                chip.classList.add("is-active"); link.setAttribute("aria-current", "location");
            }
            const remove = document.createElement("button"); remove.type = "button"; remove.className = "saved-location-remove";
            remove.textContent = "×"; remove.setAttribute("aria-label", `Odstrani shranjeni kraj ${location.name}`);
            remove.addEventListener("click", () => {
                writeLocations(readLocations().filter(saved => locationKey(saved) !== locationKey(location)));
                renderLocations();
                container.querySelector("a, button")?.focus();
            });
            chip.append(link, remove); container.appendChild(chip);
        });
    }
    const currentLocation = { name: weather.location, lat: weather.latitude, lon: weather.longitude };
    if (validLocation(currentLocation)) {
        writeLocations([currentLocation, ...readLocations().filter(saved => locationKey(saved) !== locationKey(currentLocation))]);
    }
    renderLocations();

    function locationMessage(text) {
        el("weatherLocationMessage").textContent = text;
        el("weatherLocationMessage").hidden = !text;
    }
    const locate = el("weatherLocationButton");
    locate.addEventListener("click", () => {
        if (!navigator.geolocation) { locationMessage("Brskalnik ne podpira lokacije. Vnesi ime kraja v iskalnik."); return; }
        if (!window.isSecureContext) { locationMessage("Lokacija naprave potrebuje povezavo HTTPS. Kraj lahko poiščeš ročno."); return; }
        locate.disabled = true; locate.textContent = "Določam lokacijo …";
        locationMessage("Dovoli dostop do lokacije, da prikažemo napoved tam, kjer si.");
        navigator.geolocation.getCurrentPosition(position => {
            const params = new URLSearchParams({ location: "Trenutna lokacija", lat: position.coords.latitude.toFixed(6), lon: position.coords.longitude.toFixed(6) });
            window.location.assign(`/weather?${params}`);
        }, error => {
            locate.disabled = false; locate.innerHTML = '<i class="bi bi-crosshair" aria-hidden="true"></i> Moja lokacija';
            const messages = {
                1: "Dostop do lokacije je zavrnjen. Dovoljenje spremeni v nastavitvah brskalnika ali poišči kraj ročno.",
                2: "Naprava trenutno ne more določiti lokacije. Poskusi znova ali poišči kraj ročno.",
                3: "Določanje lokacije je trajalo predolgo. Poskusi znova ali poišči kraj ročno.",
            };
            locationMessage(messages[error.code] || "Lokacije ni bilo mogoče določiti. Poišči kraj ročno.");
        }, { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
    });
    el("weatherSearchForm").addEventListener("submit", event => {
        const input = el("weatherSearch"); input.value = input.value.trim();
        if (!input.value) { event.preventDefault(); input.focus(); locationMessage("Vnesi ime kraja, na primer Ljubljana."); }
    });

    const extraDays = [...document.querySelectorAll(".weather-day-extra")];
    const toggle = document.querySelector(".weather-more-toggle");
    if (extraDays.length) {
        extraDays.forEach(day => { day.hidden = true; });
        toggle.hidden = false;
        toggle.addEventListener("click", () => {
            const expanded = toggle.getAttribute("aria-expanded") !== "true";
            extraDays.forEach(day => { day.hidden = !expanded; });
            toggle.setAttribute("aria-expanded", String(expanded));
            toggle.textContent = expanded ? "Prikaži manj dni" : `Prikaži vse dni (${document.querySelectorAll(".weather-day").length})`;
        });
    }

    const radar = el("weatherRadar");
    const radarError = () => { radar.hidden = true; el("weatherRadarStatus").hidden = false; };
    radar.addEventListener("error", radarError);
    if (radar.complete && radar.naturalWidth === 0) radarError();

    const minutely = weather.minutely_15?.time?.length ? weather.minutely_15 : weather.hourly || {};
    const units = weather.minutely_15?.time?.length ? weather.minutely_15_units || {} : weather.hourly_units || {};
    const times = minutely.time || [];
    const night = document.querySelector(".weather-page--night") !== null;
    const ink = night ? "#edf4ff" : "#213b51";
    const gridColor = night ? "rgba(190,215,240,.12)" : "rgba(40,80,115,.1)";
    const now = () => new Date(Date.now() + Number(weather.utc_offset_seconds || 0) * 1000).toISOString().slice(0, 19);
    const series = key => times.map((time, index) => ({ time, value: minutely[key]?.[index] })).filter(p => p.value !== null && p.value !== undefined && Number.isFinite(Number(p.value)));
    function line(key, name, color, axis) {
        const points = series(key);
        return points.length ? { x: points.map(p => p.time), y: points.map(p => p.value), type: "scatter", mode: "lines", name, line: { color, width: 2.5 }, yaxis: axis, hovertemplate: `${name}: %{y:.1f} ${units[key] || ""}<extra></extra>` } : null;
    }
    const traces = [
        line("temperature_2m", "Temperatura", night ? "#ff8b9b" : "#bc3154", "y"),
        line("wind_speed_10m", "Veter", night ? "#70d5b6" : "#1b806d", "y3"),
        line("global_tilted_irradiance", "Obsevanje", night ? "#f6d178" : "#eea317", "y4"),
    ].filter(Boolean);
    const rain = series("precipitation");
    if (rain.length) {
        const hourly = new Map();
        rain.forEach(p => { const hour = `${p.time.slice(0, 13)}:00`; hourly.set(hour, (hourly.get(hour) || 0) + Number(p.value)); });
        traces.push({ x: [...hourly.keys()], y: [...hourly.values()], type: "bar", name: "Padavine", marker: { color: night ? "#83baff" : "#468cc5", opacity: .7 }, yaxis: "y2", hovertemplate: "Padavine: %{y:.1f} mm / uro<extra></extra>" });
    }
    const status = el("weatherChartStatus");
    if (!traces.length) { status.textContent = "Podrobni podatki trenutno niso na voljo. Poskusi osvežiti stran."; graph.hidden = true; return; }
    if (typeof Plotly === "undefined") { status.textContent = "Grafa ni bilo mogoče naložiti. Dnevna napoved je prikazana zgoraj; za graf poskusi osvežiti stran."; graph.hidden = true; return; }
    const nightShapes = [];
    let nightStart = null;
    times.forEach((time, index) => {
        if (minutely.is_day?.[index] === 0 && nightStart === null) nightStart = time;
        if (nightStart !== null && (minutely.is_day?.[index] !== 0 || index === times.length - 1)) {
            nightShapes.push({ type: "rect", x0: nightStart, x1: time, y0: 0, y1: 1, yref: "paper", fillcolor: night ? "rgba(5,15,28,.25)" : "rgba(70,100,145,.07)", line: { width: 0 }, layer: "below" }); nightStart = null;
        }
    });
    const compact = window.matchMedia("(max-width: 575.98px)").matches;
    const rangeButtons = [...document.querySelectorAll("[data-chart-hours]")];
    function rangeFor(hours) {
        if (hours === "all") return [times[0], times[times.length - 1]];
        const start = now();
        const startDate = new Date(`${start}Z`);
        const end = new Date(startDate.getTime() + Number(hours) * 3600000).toISOString().slice(0, 19);
        return [start, end];
    }
    const dateLabel = time => {
        const date = new Date(`${time.slice(0, 19)}Z`);
        return `${weekdays[date.getUTCDay()].slice(0, 3)} ${date.getUTCDate()}. ${date.getUTCMonth() + 1}.<br>${time.slice(11, 16)}`;
    };
    function ticksFor(range) {
        const span = (new Date(`${range[1]}Z`) - new Date(`${range[0]}Z`)) / 3600000;
        const spacing = span > 72 ? (compact ? 48 : 24) : compact ? 12 : 6;
        const ticks = times.filter(time => Number(time.slice(11, 13)) % spacing === 0 && time.slice(14, 16) === "00");
        const dailyTicks = spacing >= 24 ? times.filter(time => time.slice(11, 16) === "12:00").filter((_, index) => spacing === 24 || index % 2 === 0) : ticks;
        return { "xaxis.tickvals": dailyTicks, "xaxis.ticktext": dailyTicks.map(dateLabel) };
    }
    const initialRange = rangeFor("24");
    const initialTicks = ticksFor(initialRange);
    Promise.resolve(Plotly.newPlot(graph, traces, {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "system-ui, sans-serif", color: ink, size: 11 },
        margin: { t: compact ? 90 : 65, r: 45, b: 55, l: 40 }, dragmode: "pan", hovermode: "x unified", bargap: .2,
        hoverlabel: { bgcolor: night ? "#20364c" : "#fff", font: { color: ink }, namelength: -1 },
        legend: { orientation: "h", x: 0, y: 1.12, xanchor: "left", yanchor: "bottom", font: { size: compact ? 10 : 12 } },
        xaxis: { type: "date", range: initialRange, tickmode: "array", tickvals: initialTicks["xaxis.tickvals"], ticktext: initialTicks["xaxis.ticktext"], gridcolor: gridColor, zeroline: false, fixedrange: false, automargin: true },
        yaxis: { title: { text: "°C" }, gridcolor: gridColor, zeroline: false, fixedrange: true, automargin: true },
        yaxis2: { title: { text: "mm" }, overlaying: "y", side: "right", rangemode: "tozero", showgrid: false, zeroline: false, fixedrange: true, automargin: true },
        yaxis3: { overlaying: "y", side: "right", showticklabels: false, showgrid: false, zeroline: false, fixedrange: true },
        yaxis4: { overlaying: "y", side: "right", showticklabels: false, showgrid: false, zeroline: false, fixedrange: true },
        shapes: [...nightShapes, { type: "line", x0: now(), x1: now(), y0: 0, y1: 1, yref: "paper", line: { color: night ? "#f6d178" : "#ad7708", width: 2, dash: "dot" } }],
        annotations: [{ x: now(), y: 1, yref: "paper", text: "Zdaj", showarrow: false, yshift: 12, font: { color: ink } }],
    }, { responsive: true, displayModeBar: false, displaylogo: false, scrollZoom: false })).then(() => {
        status.hidden = true;
        rangeButtons.forEach(button => {
            button.disabled = false;
            button.addEventListener("click", () => {
                const range = rangeFor(button.dataset.chartHours);
                Plotly.relayout(graph, { "xaxis.range": range, ...ticksFor(range) });
                rangeButtons.forEach(other => other.setAttribute("aria-pressed", String(other === button)));
            });
        });
        graph.on("plotly_relayout", event => {
            if (event["xaxis.range[0]"] || event["xaxis.autorange"]) rangeButtons.forEach(button => button.setAttribute("aria-pressed", "false"));
        });
    }).catch(() => { graph.hidden = true; status.hidden = false; status.textContent = "Grafa ni bilo mogoče prikazati. Uporabi dnevno napoved zgoraj."; });
})();
