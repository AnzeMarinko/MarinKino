(() => {
    "use strict";
    const root = document.getElementById("fitness-data");
    if (!root) return;
    let state = JSON.parse(root.textContent);
    const el = id => document.getElementById(id);
    const kinds = { cycling: "Kolesarjenje", running: "Tek", cardio: "Kardio", strength: "Uteži" };
    const icons = { cycling: "bi-bicycle", running: "bi-person-walking", cardio: "bi-person-arms-up" };
    const kindIcon = kind => kind === "strength"
        ? '<svg class="fitness-kind-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" focusable="false"><rect x="4" y="5" width="4" height="14" rx="1"/><rect x="16" y="5" width="4" height="14" rx="1"/><path d="M8 11h8v2H8M4 8H2v8h2m16-8h2v8h-2"/></svg>'
        : `<i class="bi ${icons[kind]} fitness-kind-icon" aria-hidden="true"></i>`;
    const colors = { cycling: "#256b73", running: "#c07c24", cardio: "#7565b3", strength: "#c35e73" };
    const escape = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
    const fmt = (value, digits = 1) => value == null ? "—" : Number(value).toLocaleString("sl-SI", { maximumFractionDigits: digits });
    const localParts = value => Object.fromEntries(new Intl.DateTimeFormat("sv-SE", {
        timeZone: "Europe/Ljubljana", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    }).formatToParts(new Date(value)).map(part => [part.type, part.value]));
    function localDateTime(value = new Date()) {
        const parts = localParts(value);
        return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
    }
    const dayDate = day => new Date(`${day}T12:00:00Z`);
    const dateLabel = day => dayDate(day).toLocaleDateString("sl-SI", { day: "numeric", month: "numeric", year: "numeric", timeZone: "UTC" });
    const timestampLabel = value => new Date(value).toLocaleString("sl-SI", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Ljubljana" });
    function addDays(day, offset) {
        const date = dayDate(day); date.setUTCDate(date.getUTCDate() + offset); return date.toISOString().slice(0, 10);
    }
    const boolLabel = value => value === true ? "Da" : value === false ? "Ne" : "Ne vem";
    const clock = seconds => {
        if (seconds == null) return "—";
        const total = Math.round(seconds), hours = Math.floor(total / 3600), minutes = Math.floor(total % 3600 / 60), remainder = total % 60;
        return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}` : `${minutes}:${String(remainder).padStart(2, "0")}`;
    };
    const paceClock = seconds => { const rounded = Math.round(seconds); return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`; };
    function parseClock(value) {
        const match = /^(\d{1,5}):([0-5]\d)(?::([0-5]\d))?$/.exec(value.trim());
        if (!match) return null;
        const seconds = match[3] === undefined ? Number(match[1]) * 60 + Number(match[2]) : Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
        return seconds > 0 && seconds <= 86400 ? seconds : null;
    }
    const sessionSeconds = row => row.duration_seconds ?? (row.duration_min == null ? null : Math.round(row.duration_min * 60));
    function performance(row, collection) {
        const seconds = sessionSeconds(row), distance = row.distance_km;
        if (!(seconds > 0) || !(distance > 0) || !["running", "cycling"].includes(row.kind)) return "";
        const prefix = collection === "activities" ? "" : "Predvideno: ";
        return row.kind === "running" ? `${prefix}${paceClock(seconds / distance)} min/km` : `${prefix}${fmt(distance * 3600 / seconds)} km/h`;
    }
    let editContext = null;
    let deleteContext = null;
    let profileDirty = false;

    function message(text, error = false) {
        const node = el("fitness-message"); node.textContent = text; node.hidden = !text; node.dataset.kind = error ? "error" : "success";
    }
    function formError(form, text = "") {
        const node = form.querySelector("[data-form-error]"); node.textContent = text; node.hidden = !text; node.dataset.kind = "error";
    }
    async function api(path, method = "GET", payload) {
        const response = await fetch(`/admin/fitness${path}`, {
            method, cache: "no-store", headers: { "Content-Type": "application/json", "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content },
            ...(payload !== undefined ? { body: JSON.stringify(payload) } : {})
        });
        const data = response.status === 204 ? {} : await response.json().catch(() => ({}));
        if (response.redirected) throw new Error("Seja je potekla. Osveži stran in se prijavi; podatki v obrazcu so ohranjeni.");
        if (!response.ok) throw new Error(data.error || (response.status === 400 ? "Zapis ni veljaven ali pa je seja potekla. Osveži stran in poskusi znova." : "Zahteva ni uspela. Podatki v obrazcu so ohranjeni."));
        if (method === "GET" && !data.profile) throw new Error("Pregleda ni mogoče naložiti. Osveži stran.");
        return data;
    }
    async function refresh(success) {
        try { state = await api("/data"); render(); message(success); }
        catch (_error) { message(`${success} Pregleda ni mogoče osvežiti; uporabi Osveži pregled.`, true); }
    }
    function actions(collection, row) {
        return `<div class="admin-actions"><button type="button" class="btn btn-sm btn-outline-secondary" data-edit="${collection}" data-id="${escape(row.id)}">Uredi</button><button type="button" class="btn btn-sm btn-outline-danger" data-delete="${collection}" data-id="${escape(row.id)}">Izbriši</button></div>`;
    }
    function sessionMeta(row) {
        const detail = performance(row, "activities");
        return `${sessionSeconds(row) == null ? "čas neznan" : clock(sessionSeconds(row))}${row.distance_km != null ? ` · ${fmt(row.distance_km, 3)} km` : ""}${detail ? ` · ${escape(detail)}` : ""}`;
    }
    function card(row, collection) {
        return `<article class="fitness-card fitness-activity-row" data-entry-id="${escape(row.id)}"><time datetime="${escape(row.timestamp)}">${escape(timestampLabel(row.timestamp))}</time><h3 title="${escape(row.title)}">${kindIcon(row.kind)} ${escape(row.title)}</h3><small class="fitness-activity-meta">${sessionMeta(row)}</small><span class="fitness-activity-note" title="${escape(row.description)}">${escape(row.description) || "—"}</span>${actions(collection, row)}</article>`;
    }
    function lastMeasurement(key) { return [...state.measurements].reverse().find(row => row[key] != null); }
    function renderSummary() {
        const weight = lastMeasurement("weight_kg"), waist = lastMeasurement("waist_cm");
        const bmiInfo = weight?.bmi == null
            ? "ITM = teža / višina². Za odrasle je splošni referenčni razpon 18,5–24,9. ITM ne razlikuje mišic od maščobe in ni diagnoza. Vnesi višino za izračun."
            : `ITM ${fmt(weight.bmi)}: ${weight.bmi < 18.5 ? "pod običajnim razponom" : weight.bmi < 25 ? "v običajnem razponu" : weight.bmi < 30 ? "povišan" : "visok"}. Splošni referenčni razpon za odrasle je 18,5–24,9; ITM ne razlikuje mišic od maščobe in ni diagnoza.`;
        const ratioInfo = waist?.waist_height_ratio == null
            ? "Razmerje pas / višina izračunamo iz iste meritve pasu in vnesene višine. Orientacija je namenjena odraslim z ITM pod 35."
            : weight?.bmi == null || weight.bmi >= 35
                ? "Razmerje pas / višina je izračunano, vendar ga brez ITM pod 35 ne razvrščamo."
                : `${waist.waist_height_ratio < 0.5 ? "Pas je manjši od polovice višine." : waist.waist_height_ratio < 0.6 ? "Razmerje 0,5 ali več je orientacija za povečano osrednjo zamaščenost." : "Razmerje 0,6 ali več je orientacija za večjo osrednjo zamaščenost."} To ni diagnoza; razlago upoštevaj skupaj z drugimi dejavniki.`;
        const goalCaption = (value, target, unit, digits) => {
            if (target == null) return "";
            const delta = value == null ? null : target - value;
            return `<small class="fitness-goal">Cilj: ${fmt(target, digits)} ${unit}${delta == null ? "" : Math.abs(delta) < .05 ? " · Pri cilju" : ` · do cilja ${delta > 0 ? "+" : "−"}${fmt(Math.abs(delta), digits)} ${unit}`}</small>`;
        };
        const height = state.profile.height_cm;
        const targetBmi = state.profile.target_weight_kg != null && height
            ? state.profile.target_weight_kg / (height / 100) ** 2
            : null;
        const targetRatio = state.profile.target_waist_cm != null && height
            ? state.profile.target_waist_cm / height
            : null;
        el("fitness-summary").innerHTML = [
            ["Zadnja teža", weight?.weight_kg, "kg", weight, 1, state.profile.target_weight_kg], ["Zadnji obseg pasu", waist?.waist_cm, "cm", waist, 1, state.profile.target_waist_cm],
            ["ITM", weight?.bmi, "", weight, 1, targetBmi, bmiInfo, "bmi"],
            ["Pas / višina", waist?.waist_height_ratio, "", waist, 3, targetRatio, ratioInfo, "ratio"]
        ].map(([label, value, unit, row, digits, target, info, infoId]) => `<div class="admin-stat"><div class="fitness-stat-heading"><span>${label}</span>${info ? `<span class="fitness-info-wrap"><button type="button" class="fitness-info" aria-describedby="fitness-info-${infoId}">i</button><span id="fitness-info-${infoId}" class="fitness-info-tooltip" role="tooltip">${escape(info)}</span></span>` : ""}</div><strong>${fmt(value, digits)}${value != null && unit ? ` <small class="fs-6">${unit}</small>` : ""}</strong><small class="fitness-caption">${value != null && row ? escape(timestampLabel(row.timestamp)) : "Ni podatkov"}</small>${goalCaption(value, target, unit, digits)}</div>`).join("");
        const reminder = el("fitness-weigh-reminder");
        const weighing = state.weighing_status;
        reminder.hidden = !weighing.reminder;
        reminder.dataset.kind = weighing.red
            ? "error"
            : weighing.orange
                ? "warning"
                : "";
        reminder.textContent = !weighing.reminder
            ? ""
            : weighing.days == null
                ? "Tehtanja še nisi zabeležil. Dodaj prvo meritev teže."
                : `Od zadnjega tehtanja je minilo ${weighing.days} dni. Čas je za novo meritev teže.`;
    }
    function renderMeasurements() {
        const rows = [...state.measurements].reverse();
        if (!rows.length) { el("fitness-measurements").innerHTML = '<p class="admin-empty">Meritev še ni. Dodaj težo, pas ali opombo.</p>'; return; }
        el("fitness-measurements").innerHTML = `<table class="table"><thead><tr>${["Datum in ura", "Teža (kg)", "Pas (cm)", "ITM", "Pas/višina", "Na tešče", "Zjutraj", "Po veliki potrebi", "Opomba", "Dejanja"].map(label => `<th scope="col">${label}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr data-entry-id="${escape(row.id)}"><td class="fitness-value">${escape(timestampLabel(row.timestamp))}</td><td>${fmt(row.weight_kg)}</td><td>${fmt(row.waist_cm)}</td><td>${fmt(row.bmi)}</td><td>${fmt(row.waist_height_ratio, 3)}</td><td>${boolLabel(row.fasting)}</td><td>${boolLabel(row.morning)}</td><td>${boolLabel(row.after_bowel)}</td><td style="min-width:140px;white-space:pre-wrap;overflow-wrap:anywhere">${escape(row.notes)}</td><td>${actions("measurements", row)}</td></tr>`).join("")}</tbody></table>`;
    }
    function renderSuggestions() {
        el("fitness-suggestions").innerHTML = state.suggestions.map(row => `<button type="button" class="fitness-card fitness-suggestion" data-use-suggestion="${escape(row.id)}">${kindIcon(row.kind)}<strong>${escape(row.title)}</strong><small>Zabeleži aktivnost</small></button>`).join("");
    }
    function renderDistanceSummary() {
        const period = el("fitness-distance-period").value;
        const cutoff = period === "week" ? state.current_week.date : period === "30" ? addDays(state.today, -29) : "";
        const rows = state.activities.filter(row => !cutoff || localDateTime(row.timestamp).date >= cutoff);
        el("fitness-distance-summary").innerHTML = ["running", "cycling"].map(kind => {
            const sessions = rows.filter(row => row.kind === kind), measured = sessions.filter(row => row.distance_km != null);
            const distance = measured.reduce((sum, row) => sum + row.distance_km, 0);
            const timed = sessions.filter(row => sessionSeconds(row) != null);
            const seconds = timed.reduce((sum, row) => sum + sessionSeconds(row), 0);
            const paired = sessions.filter(row => row.distance_km > 0 && sessionSeconds(row) > 0);
            const pairedDistance = paired.reduce((sum, row) => sum + row.distance_km, 0), pairedSeconds = paired.reduce((sum, row) => sum + sessionSeconds(row), 0);
            const average = !paired.length ? "—" : kind === "running" ? `${paceClock(pairedSeconds / pairedDistance)} min/km` : `${fmt(pairedDistance * 3600 / pairedSeconds)} km/h`;
            return `<div class="fitness-card"><h3>${kindIcon(kind)} ${kinds[kind]}</h3><strong class="fitness-distance-total">${measured.length ? fmt(distance, 3) : "—"} km</strong><p>Zabeleženi čas: <strong>${timed.length ? clock(seconds) : "—"}</strong></p><p>${kind === "running" ? "Skupni tempo" : "Povprečna hitrost"}: <strong>${average}</strong></p><small>${sessions.length} izvedb · ${sessions.length - measured.length} brez razdalje · ${sessions.length - timed.length} brez časa. Izračun tempa/hitrosti: ${paired.length} popolnih izvedb.</small></div>`;
        }).join("");
    }
    function renderAccess() {
        const progress = state.plan_progress;
        const weighing = state.weighing_status;
        el("fitness-access-status").textContent = progress.allowed ? "Oba pogoja za zadnjih 7 dni izpolnjena." : "Za odklep v zadnjih 7 dneh zabeleži vsaj en tek ali kolesarjenje in vsaj eno kardio vadbo ali vadbo za moč.";
        el("fitness-plan-progress").innerHTML = `<span>${progress.recent_endurance ? "✓" : "○"} Tek ali kolesarjenje</span><span>${progress.recent_cardio_or_strength ? "✓" : "○"} Kardio ali moč</span>`;
        const node = el("fitness-access-suggestions");
        node.hidden = !weighing.locked;
        node.innerHTML = weighing.locked ? '<p>Za odklep zabeleži novo meritev teže.</p><button type="button" class="btn btn-primary mb-3" data-new="measurements">Zabeleži tehtanje</button>' : "";
    }
    function emptyChart(id, text) { el(id).innerHTML = `<p class="admin-empty">${escape(text)}</p>`; }
    const svgText = (x, y, label, extra = "") => `<text x="${x}" y="${y}" font-size="11" fill="#627589" ${extra}>${escape(label)}</text>`;
    function lineChart(id, key, label, digits = 1, references = []) {
        const guides = references.map(reference => typeof reference === "number" ? { value: reference, label: `Orientacija ${fmt(reference, digits)}`, color: "#b47d35" } : reference);
        const period = el("fitness-period").value;
        const cutoff = period === "all" ? "" : addDays(state.today, -Number(period));
        const comparable = el("fitness-comparable").checked;
        const hasComparableConditions = row => row.fasting === true && row.morning === true && row.after_bowel === true;
        const periodRows = state.measurements.filter(row => row[key] != null && (!cutoff || localDateTime(row.timestamp).date >= cutoff));
        const rows = periodRows.filter(row => !comparable || hasComparableConditions(row));
        const comparableRows = comparable ? [] : periodRows.filter(hasComparableConditions);
        if (!rows.length) { emptyChart(id, (key === "bmi" || key === "waist_height_ratio") && !state.profile.height_cm ? "Za ta prikaz potrebujemo višino in ustrezne meritve." : "Za izbrano obdobje in pogoje ni meritev."); return; }
        const width = Math.max(320, Math.min(540, el(id).clientWidth || 540)), height = 245, left = 52, right = 20, top = 25, bottom = 35;
        const times = rows.map(row => +new Date(row.timestamp));
        let minTime = Math.min(...times), maxTime = Math.max(...times);
        if (minTime === maxTime) { minTime -= 43200000; maxTime += 43200000; }
        const values = [...rows.map(row => row[key]), ...comparableRows.map(row => row[key]), ...guides.map(reference => reference.value)];
        let minimum = Math.min(...values), maximum = Math.max(...values);
        const padding = Math.max((maximum - minimum) * .15, key === "waist_height_ratio" ? .02 : .5);
        minimum -= padding; maximum += padding;
        const x = time => left + (time - minTime) / (maxTime - minTime) * (width - left - right);
        const y = value => height - bottom - (value - minimum) / (maximum - minimum) * (height - top - bottom);
        let contents = `<title>${escape(label)}. ${rows.length} meritev. Posamezne točke imajo datum in vrednost.</title>`;
        for (let index = 0; index <= 4; index++) {
            const value = minimum + (maximum - minimum) * index / 4;
            contents += `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="#e5ecef"/>${svgText(left - 8, y(value) + 4, fmt(value, digits), 'text-anchor="end"')}`;
        }
        guides.forEach(({ value, label, color }) => { contents += `<line class="fitness-chart-guide" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="${color}" stroke-dasharray="5 4"><title>${escape(label)}</title></line>${svgText(width - right, y(value) - 5, label, 'text-anchor="end"')}`; });
        contents += `<polyline points="${rows.map((row, index) => `${x(times[index])},${y(row[key])}`).join(" ")}" fill="none" stroke="#256b73" stroke-width="2.5"/>`;
        if (comparableRows.length) contents += `<polyline class="fitness-chart-comparable" points="${comparableRows.map(row => `${x(+new Date(row.timestamp))},${y(row[key])}`).join(" ")}" fill="none" stroke="#39855f" stroke-width="2.5" stroke-dasharray="4 3"><title>Meritve zjutraj, na tešče in po veliki potrebi</title></polyline>`;
        rows.forEach((row, index) => {
            const caption = `${timestampLabel(row.timestamp)}: ${fmt(row[key], digits)}`;
            contents += `<circle class="fitness-chart-point" cx="${x(times[index])}" cy="${y(row[key])}" r="4" fill="#256b73" tabindex="0" aria-label="${escape(caption)}" data-caption="${escape(caption)}"><title>${escape(caption)}</title></circle>`;
        });
        contents += svgText(left, height - 8, dateLabel(localDateTime(rows[0].timestamp).date)) + svgText(width - right, height - 8, dateLabel(localDateTime(rows.at(-1).timestamp).date), 'text-anchor="end"');
        el(id).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(label)}">${contents}<g class="fitness-chart-tooltip" visibility="hidden" pointer-events="none" role="status" aria-live="polite"><rect rx="4" fill="#fff" stroke="#256b73"/><text x="8" y="18" font-size="11" fill="#21364b"></text></g></svg>`;
        const svg = el(id).querySelector("svg");
        const tooltip = svg.querySelector(".fitness-chart-tooltip");
        const tooltipText = tooltip.querySelector("text");
        const tooltipRect = tooltip.querySelector("rect");
        svg.querySelectorAll(".fitness-chart-point").forEach(point => {
            const showPoint = () => {
                const caption = point.dataset.caption;
                tooltipText.textContent = caption;
                const boxWidth = Math.min(width - 8, Math.max(120, caption.length * 6.2 + 16));
                const pointX = Number(point.getAttribute("cx"));
                const pointY = Number(point.getAttribute("cy"));
                const tooltipX = pointX + boxWidth + 12 > width
                    ? Math.max(4, pointX - boxWidth - 12)
                    : pointX + 12;
                const tooltipY = Math.max(4, Math.min(height - 32, pointY - 16));
                tooltipRect.setAttribute("x", tooltipX);
                tooltipRect.setAttribute("y", tooltipY);
                tooltipRect.setAttribute("width", boxWidth);
                tooltipRect.setAttribute("height", 26);
                tooltipText.setAttribute("x", tooltipX + 8);
                tooltipText.setAttribute("y", tooltipY + 17);
                tooltip.setAttribute("visibility", "visible");
            };
            point.addEventListener("click", showPoint);
            point.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    showPoint();
                }
            });
        });
    }
    function fitnessChart(kind) {
        const id = `chart-${kind}-fitness`;
        const rows = state.activities.filter(row => row.kind === kind && row.distance_km > 0 && row.average_speed_kmh > 0)
            .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        if (!rows.length) { emptyChart(id, "Za graf zabeleži aktivnost z razdaljo in časom."); return; }
        const width = 540, height = 300, left = 60, right = 22, top = 30, bottom = 55;
        const maxDistance = Math.max(...rows.map(row => row.distance_km)) * 1.12;
        const maxSpeed = Math.max(...rows.map(row => row.average_speed_kmh)) * 1.12;
        const firstTime = +new Date(rows[0].timestamp), lastTime = +new Date(rows.at(-1).timestamp);
        const x = distance => left + distance / maxDistance * (width - left - right);
        const y = speed => height - bottom - speed / maxSpeed * (height - top - bottom);
        let contents = `<title>${kinds[kind]}: razdalja in povprečna hitrost. Večja pika pomeni novejšo aktivnost.</title>`;
        for (let index = 0; index <= 4; index++) {
            const distance = maxDistance * index / 4, speed = maxSpeed * index / 4;
            contents += `<line x1="${left}" x2="${width - right}" y1="${y(speed)}" y2="${y(speed)}" stroke="#e5ecef"/>`;
            contents += svgText(left - 8, y(speed) + 4, fmt(speed), 'text-anchor="end"');
            contents += svgText(x(distance), height - bottom + 20, fmt(distance), 'text-anchor="middle"');
        }
        contents += svgText(left, 15, "Povprečna hitrost (km/h)") + svgText(width / 2, height - 8, "Razdalja (km)", 'text-anchor="middle"');
        rows.forEach(row => {
            const recency = lastTime === firstTime ? 1 : (+new Date(row.timestamp) - firstTime) / (lastTime - firstTime);
            const caption = `${timestampLabel(row.timestamp)} · ${fmt(row.distance_km, 3)} km · ${fmt(row.average_speed_kmh)} km/h`;
            contents += `<circle class="fitness-chart-point fitness-conditioning-point" cx="${x(row.distance_km)}" cy="${y(row.average_speed_kmh)}" r="${4 + 6 * recency}" fill="${colors[kind]}" fill-opacity="${.4 + .5 * recency}" stroke="white" stroke-width="1" tabindex="0" role="button" aria-label="${escape(caption)}" data-caption="${escape(caption)}"><title>${escape(caption)}</title></circle>`;
        });
        el(id).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="group" aria-label="Kondicija: ${kinds[kind]}">${contents}</svg><p class="fitness-scatter-detail small" role="status">${rows.length} aktivnosti · manjše pike = starejše</p>`;
        const detail = el(id).querySelector(".fitness-scatter-detail");
        el(id).querySelectorAll("circle").forEach(point => {
            const show = () => { detail.textContent = point.dataset.caption; };
            point.addEventListener("click", show);
            point.addEventListener("focus", show);
            point.addEventListener("mouseenter", show);
            point.addEventListener("keydown", event => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); show(); }
            });
        });
    }
    function renderCharts() {
        fitnessChart("cycling"); fitnessChart("running");
        const targetGuide = (value, unit) => value == null ? [] : [{ value, label: `Cilj ${fmt(value)} ${unit}`, color: "#a364ae" }];
        lineChart("chart-weight", "weight_kg", "Graf telesne teže", 1, targetGuide(state.profile.target_weight_kg, "kg"));
        lineChart("chart-waist", "waist_cm", "Graf obsega pasu", 1, targetGuide(state.profile.target_waist_cm, "cm"));
        lineChart("chart-bmi", "bmi", "Graf ITM");
        lineChart("chart-ratio", "waist_height_ratio", "Graf razmerja pas/višina", 2, [0.5, 0.6]);
        const weekly = state.weekly, width = 960, height = 265, left = 50, top = 20, baseline = 220;
        const maximum = Math.max(30, ...weekly.map(week => week.minutes));
        const step = (width - left - 20) / weekly.length;
        let contents = "<title>Opravljene minute po tednih in vrsti aktivnosti. Podrobnosti v tedenski tabeli.</title>";
        for (let index = 0; index <= 4; index++) {
            const value = maximum * index / 4, y = baseline - value / maximum * (baseline - top);
            contents += `<line x1="${left}" x2="${width - 20}" y1="${y}" y2="${y}" stroke="#e5ecef"/>${svgText(left - 8, y + 4, fmt(value, 0), 'text-anchor="end"')}`;
        }
        weekly.forEach((week, index) => {
            let offset = 0;
            Object.keys(kinds).forEach(kind => {
                const value = week.by_kind[kind], barHeight = value / maximum * (baseline - top);
                if (value > 0) contents += `<rect x="${left + index * step + step * .2}" y="${baseline - offset - barHeight}" width="${step * .6}" height="${barHeight}" fill="${colors[kind]}" tabindex="0" aria-label="${escape(`${dateLabel(week.date)}: ${kinds[kind]} ${fmt(value)} min`)}"><title>${escape(`${dateLabel(week.date)}: ${kinds[kind]} ${fmt(value)} min`)}</title></rect>`;
                offset += barHeight;
            });
            contents += svgText(left + (index + .5) * step, 242, dateLabel(week.date).replace(/\d{4}/, ""), 'text-anchor="middle"');
        });
        el("chart-activity").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Graf opravljenih minut aktivnosti">${contents}</svg>`;
        el("fitness-activity-legend").innerHTML = Object.entries(kinds).map(([kind, label]) => `<span style="--fitness-kind-color:${colors[kind]}">${kindIcon(kind)}${label}</span>`).join("");
        const weeklyDistance = (week, kind) => {
            const count = week.sessions_by_kind[kind], missing = week.missing_distance_by_kind[kind];
            return count && count === missing ? "—" : `${fmt(week.distance_by_kind[kind], 3)}${missing ? " + ?" : ""}`;
        };
        el("fitness-weekly-table").innerHTML = `<table class="table"><thead><tr>${["Teden od", "Minute skupaj", "Tek (km)", "Kolo (km)", "Dnevi za moč"].map(label => `<th scope="col">${label}</th>`).join("")}</tr></thead><tbody>${[...weekly].reverse().map(week => `<tr><td>${dateLabel(week.date)}</td><td>${fmt(week.minutes)}</td><td>${weeklyDistance(week, "running")}</td><td>${weeklyDistance(week, "cycling")}</td>${[week.recorded_strength_days].map(value => `<td>${fmt(value)}</td>`).join("")}</tr>`).join("")}</tbody></table><p class="form-text">»+ ?«: del razdalj ni znan. »—«: pri zabeleženih izvedbah ni znana nobena razdalja.</p>`;
    }
    function render() {
        renderAccess(); renderSummary(); renderMeasurements(); renderCharts(); renderSuggestions(); renderDistanceSummary();
        el("fitness-activities").innerHTML = [...state.activities].reverse().map(row => card(row, "activities")).join("") || '<p class="admin-empty">Izvedenih aktivnosti še ni. Dodaj prvo aktivnost.</p>';
        if (!profileDirty) Object.entries(state.profile).forEach(([name, value]) => { const input = el("fitness-profile").elements.namedItem(name); if (input) input.value = value ?? ""; });
    }
    function selectTab(key, focus = false) {
        document.querySelectorAll("[data-tab]").forEach(button => {
            const selected = button.dataset.tab === key; button.setAttribute("aria-selected", selected); button.tabIndex = selected ? 0 : -1;
            el(`panel-${button.dataset.tab}`).hidden = !selected;
            if (selected && focus) button.focus();
        });
        if (key === "overview") renderCharts();
    }
    document.querySelectorAll("[data-tab]").forEach(button => {
        button.addEventListener("click", () => selectTab(button.dataset.tab));
        button.addEventListener("keydown", event => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault(); const tabs = [...document.querySelectorAll("[data-tab]")], index = tabs.indexOf(button);
            const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
            selectTab(tabs[next].dataset.tab, true);
        });
    });
    function fillForm(form, row) {
        for (const [name, value] of Object.entries(row)) {
            const input = form.elements.namedItem(name); if (input) input.value = value == null ? "" : String(value);
        }
    }
    function initDate(form, prefix, timestamp) {
        const date = timestamp ? localDateTime(timestamp) : localDateTime();
        el(`${prefix}-date`).value = date.date; el(`${prefix}-date`).max = localDateTime().date;
        el(`${prefix}-time`).value = date.time;
    }
    function syncStandard() { el("measurement-standard").checked = ["fasting", "morning", "after_bowel"].every(name => el(`measurement-${name}`).value === "true"); }
    function openMeasurement(row) {
        const form = el("fitness-measurement-form"); form.reset(); formError(form); editContext = { collection: "measurements", id: row?.id };
        el("fitness-measurement-title").textContent = row ? "Uredi meritev" : "Nova meritev";
        if (row) fillForm(form, row); initDate(form, "measurement", row?.timestamp); syncStandard();
        el("fitness-measurement-dialog").showModal();
    }
    function openSession(collection, row, options = {}) {
        const form = el("fitness-session-form"); form.reset(); formError(form);
        editContext = { collection: "activities", id: row?.id };
        el("fitness-session-title").textContent = row ? "Uredi aktivnost" : "Nova aktivnost";
        const values = row || options.template;
        if (values) {
            fillForm(form, values);
            el("session-elapsed").value = sessionSeconds(values) == null ? "" : clock(sessionSeconds(values));
        }
        initDate(form, "session", row?.timestamp);
        updateSessionFields(); updatePerformance();
        el("fitness-session-dialog").showModal();
    }
    function serialize(form) { return Object.fromEntries(new FormData(form)); }
    function actualTimestamp(form) {
        const data = serialize(form), today = localDateTime();
        const day = data.date || today.date, time = data.time || (day === today.date ? today.time : "12:00");
        return `${day}T${time}:00`;
    }
    async function save(form, path, method, payload, dialog) {
        if (form.dataset.saving) return;
        form.dataset.saving = "true"; formError(form);
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        const label = button.textContent;
        button.textContent = "Shranjujem …";
        form.setAttribute("aria-busy", "true");
        try {
            await api(path, method, payload);
            if (dialog) dialog.close(); else profileDirty = false;
            await refresh("Podatki shranjeni.");
        } catch (error) { formError(form, error.message || "Povezava ni uspela. Vnos je ohranjen; poskusi znova."); }
        finally { button.disabled = false; button.textContent = label; form.removeAttribute("aria-busy"); delete form.dataset.saving; }
    }
    el("fitness-measurement-form").addEventListener("submit", event => {
        event.preventDefault(); const form = event.currentTarget, payload = serialize(form); payload.timestamp = actualTimestamp(form);
        ["fasting", "morning", "after_bowel"].forEach(name => { payload[name] = payload[name] === "" ? null : payload[name] === "true"; });
        save(form, `/measurements${editContext.id ? `/${editContext.id}` : ""}`, editContext.id ? "PUT" : "POST", payload, el("fitness-measurement-dialog"));
    });
    el("fitness-session-form").addEventListener("submit", event => {
        event.preventDefault(); const form = event.currentTarget, context = editContext;
        const original = state.activities.find(row => row.id === context.id);
        const payload = { ...original, ...serialize(form), timestamp: actualTimestamp(form) };
        // The visible clock/minutes fields replace any previously stored seconds.
        delete payload.duration_seconds;
        save(form, `/activities${context.id ? `/${context.id}` : ""}`, context.id ? "PUT" : "POST", payload, el("fitness-session-dialog"));
    });
    el("fitness-profile").addEventListener("input", () => { profileDirty = true; });
    el("fitness-profile").addEventListener("submit", event => { event.preventDefault(); save(event.currentTarget, "/profile", "PUT", { ...state.profile, ...serialize(event.currentTarget) }); });
    function updateSessionFields() {
        const usesDistance = ["cycling", "running"].includes(el("session-kind").value);
        el("session-distance-field").hidden = !usesDistance;
        el("session-distance").disabled = !usesDistance;
    }
    function updatePerformance() {
        const elapsed = el("session-elapsed").value;
        const minutes = el("session-duration").value;
        const seconds = elapsed ? parseClock(elapsed) : minutes ? Math.round(Number(minutes) * 60) : null;
        const value = performance({ kind: el("session-kind").value, duration_seconds: seconds, distance_km: Number(el("session-distance").value) }, "activities");
        el("session-performance").textContent = value; el("session-performance").hidden = !value;
    }
    el("session-kind").addEventListener("change", () => { updateSessionFields(); updatePerformance(); });
    el("session-duration").addEventListener("input", event => { const value = event.target.value; el("session-elapsed").value = value !== "" && Number(value) > 0 && Number(value) <= 1440 ? clock(Number(value) * 60) : ""; updatePerformance(); });
    el("session-elapsed").addEventListener("input", event => { const seconds = parseClock(event.target.value); el("session-duration").value = seconds == null ? "" : String(seconds / 60); updatePerformance(); });
    el("session-distance").addEventListener("input", updatePerformance);
    ["measurement", "session"].forEach(prefix => el(`${prefix}-date`).addEventListener("change", event => { el(`${prefix}-time`).value = event.target.value === localDateTime().date ? localDateTime().time : "12:00"; }));
    el("measurement-standard").addEventListener("change", event => { ["fasting", "morning", "after_bowel"].forEach(name => { el(`measurement-${name}`).value = event.target.checked ? "true" : ""; }); });
    ["fasting", "morning", "after_bowel"].forEach(name => el(`measurement-${name}`).addEventListener("change", syncStandard));
    document.querySelector(".admin-page").addEventListener("click", event => {
        const button = event.target.closest("button"); if (!button) return;
        if (button.hasAttribute("data-close")) { if (!button.closest("dialog").querySelector('[data-saving="true"]')) button.closest("dialog").close(); }
        if (button.dataset.new) button.dataset.new === "measurements" ? openMeasurement() : openSession(button.dataset.new);
        if (button.dataset.edit) {
            const row = state[button.dataset.edit].find(row => row.id === button.dataset.id);
            if (row) button.dataset.edit === "measurements" ? openMeasurement(row) : openSession(button.dataset.edit, row);
        }
        if (button.dataset.delete) {
            deleteContext = { collection: button.dataset.delete, id: button.dataset.id };
            const row = state[deleteContext.collection].find(row => row.id === deleteContext.id);
            el("fitness-delete-description").textContent = (row.title || `Meritev: ${timestampLabel(row.timestamp)}`);
            formError(el("fitness-delete-dialog")); el("fitness-delete-dialog").showModal();
        }
        if (button.dataset.useSuggestion) openSession("activities", null, { template: state.suggestions.find(row => row.id === button.dataset.useSuggestion) });
        if (button.hasAttribute("data-fitness-settings")) { selectTab("templates"); el("fitness-settings").scrollIntoView({ block: "start" }); el("fitness-target-weight").focus({ preventScroll: true }); }
    });
    el("fitness-confirm-delete").addEventListener("click", async event => {
        const button = event.currentTarget; button.disabled = true; button.dataset.saving = "true";
        try { await api(`/${deleteContext.collection}/${deleteContext.id}`, "DELETE"); el("fitness-delete-dialog").close(); await refresh("Zapis izbrisan."); }
        catch (error) { formError(el("fitness-delete-dialog"), error.message || "Brisanje ni uspelo. Poskusi znova."); }
        finally { button.disabled = false; delete button.dataset.saving; }
    });
    document.querySelectorAll(".fitness-dialog").forEach(dialog => dialog.addEventListener("cancel", event => { if (dialog.querySelector('[data-saving="true"]')) event.preventDefault(); }));
    el("fitness-period").addEventListener("change", renderCharts);
    el("fitness-comparable").addEventListener("change", renderCharts);
    el("fitness-distance-period").addEventListener("change", renderDistanceSummary);
    let resizeTimer;
    window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderCharts, 100); });
    el("fitness-refresh").addEventListener("click", async event => {
        const button = event.currentTarget; button.disabled = true;
        try { state = await api("/data"); render(); message("Pregled osvežen."); }
        catch (error) { message(error.message || "Pregleda ni mogoče osvežiti.", true); }
        finally { button.disabled = false; }
    });
    render();
})();
