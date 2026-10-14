(() => {
    "use strict";
    const root = document.getElementById("fitness-data");
    if (!root) return;
    let state = JSON.parse(root.textContent);
    const el = id => document.getElementById(id);
    const kinds = { cycling: "Kolesarjenje", running: "Tek", cardio: "Kardio vaje", strength: "Vaje za moč" };
    const intensities = { light: "lahka", moderate: "zmerna", vigorous: "visoka" };
    const colors = { cycling: "#256b73", running: "#c07c24", cardio: "#7565b3", strength: "#c35e73" };
    const weekdays = ["Ponedeljek", "Torek", "Sreda", "Četrtek", "Petek", "Sobota", "Nedelja"];
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
    const monday = day => addDays(day, -(dayDate(day).getUTCDay() + 6) % 7);
    function isoWeek(day) {
        const thursday = dayDate(addDays(monday(day), 3));
        const first = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1, 12));
        return Math.ceil(((thursday - first) / 86400000 + 1) / 7);
    }
    const parityLabel = day => `${isoWeek(day) % 2 ? "Lihi" : "Sodi"} teden · ${isoWeek(day)}`;
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
    const workout = id => [...state.templates, ...state.suggestions].find(row => row.id === id);
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
        try { state = await api(`/data?start=${monday(el("fitness-week").value || state.today)}`); render(); message(success); }
        catch (_error) { message(`${success} Pregleda ni mogoče osvežiti; uporabi Osveži pregled.`, true); }
    }
    function actions(collection, row) {
        return `<div class="admin-actions"><button type="button" class="btn btn-sm btn-outline-secondary" data-edit="${collection}" data-id="${escape(row.id)}">Uredi</button><button type="button" class="btn btn-sm btn-outline-danger" data-delete="${collection}" data-id="${escape(row.id)}">Izbriši</button></div>`;
    }
    function sessionMeta(row, collection) {
        const detail = performance(row, collection);
        return `${escape(kinds[row.kind])} · ${sessionSeconds(row) == null ? "čas neznan" : `čas ${clock(sessionSeconds(row))}`} · ${escape(intensities[row.intensity] || "intenzivnost neznana")}${row.distance_km != null ? ` · ${fmt(row.distance_km, 3)} km` : ""}${detail ? ` · ${escape(detail)}` : ""}${row.training_style ? ` · ${escape(state.styles[row.training_style])}` : ""}${row.equipment ? ` · ${escape(state.equipment[row.equipment])}` : ""}${row.cadence_rpm != null ? ` · ${fmt(row.cadence_rpm)} obr./min` : ""}`;
    }
    function card(row, collection) {
        const status = collection === "plan" ? { planned: "Načrtovano", completed: "Opravljeno", skipped: "Preskočeno" }[row.status] : "";
        const advice = row.advice || (collection === "templates" ? state.general_advice[row.kind] : "");
        const controls = collection === "suggestions" ? `<div class="admin-actions"><button type="button" class="btn btn-sm btn-primary" data-use-suggestion="${escape(row.id)}">Dodaj v plan</button><button type="button" class="btn btn-sm btn-outline-secondary" data-save-suggestion="${escape(row.id)}">Prilagodi in shrani predlogo</button></div>` : actions(collection, row);
        return `<article class="fitness-card${row.status ? ` is-${escape(row.status)}` : ""}" data-entry-id="${escape(row.id)}"><h3>${escape(row.title)}</h3><small>${sessionMeta(row, collection)}</small>${row.timestamp ? `<small class="d-block mt-1">${escape(timestampLabel(row.timestamp))}</small>` : ""}${status ? `<strong class="d-block small mt-2">${status}</strong>` : ""}${row.description ? `<p>${escape(row.description)}</p>` : ""}${advice ? `<details class="fitness-advice"${collection === "suggestions" ? " open" : ""}><summary>Nasvet in razporeditev</summary><p>${escape(advice)}</p></details>` : ""}${row.tutorial_url ? `<a class="small" href="${escape(row.tutorial_url)}" target="_blank" rel="noopener noreferrer">Odpri tutorial ↗</a>` : ""}${controls}${collection === "templates" ? `<button type="button" class="btn btn-sm btn-primary mt-2" data-use-template="${escape(row.id)}">Dodaj v plan</button>` : ""}${collection === "plan" && row.status !== "completed" ? `<button type="button" class="btn btn-sm btn-primary mt-2" data-complete="${escape(row.id)}">Zabeleži izvedbo</button>` : ""}</article>`;
    }
    function lastMeasurement(key) { return [...state.measurements].reverse().find(row => row[key] != null); }
    function renderSummary() {
        const weight = lastMeasurement("weight_kg"), waist = lastMeasurement("waist_cm");
        const goalCaption = (value, target, unit) => {
            if (target == null) return "";
            const delta = value == null ? null : target - value;
            return `<small class="fitness-goal">Cilj: ${fmt(target)} ${unit}${delta == null ? "" : Math.abs(delta) < .05 ? " · Pri cilju" : ` · do cilja ${delta > 0 ? "+" : "−"}${fmt(Math.abs(delta))} ${unit}`}</small>`;
        };
        el("fitness-summary").innerHTML = [
            ["Zadnja teža", weight?.weight_kg, "kg", weight, 1, state.profile.target_weight_kg], ["Zadnji obseg pasu", waist?.waist_cm, "cm", waist, 1, state.profile.target_waist_cm],
            ["ITM", weight?.bmi, "", weight, 1], ["Pas / višina", waist?.waist_height_ratio, "", waist, 3]
        ].map(([label, value, unit, row, digits, target]) => `<div class="admin-stat"><span>${label}</span><strong>${fmt(value, digits)}${value != null && unit ? ` <small class="fs-6">${unit}</small>` : ""}</strong><small class="fitness-caption">${value != null && row ? escape(timestampLabel(row.timestamp)) : "Ni podatkov"}</small>${goalCaption(value, target, unit)}</div>`).join("");
        const week = state.current_week, profile = state.profile;
        el("fitness-week-label").textContent = `${dateLabel(week.date)}–${dateLabel(addDays(week.date, 6))}`;
        el("fitness-progress").innerHTML = [["Aerobna vadba", week.aerobic_equivalent, profile.aerobic_goal, "enakovrednih min"], ["Vadba za moč", week.strength_days, profile.strength_goal, "dni"]].map(([label, value, goal, unit]) => `<div class="fitness-progress-item"><div><span>${label}</span><strong>${fmt(value)} / ${fmt(goal)} ${unit}</strong></div><progress max="${goal}" value="${Math.min(value, goal)}" aria-label="${label}">${fmt(value)} / ${fmt(goal)}</progress></div>`).join("");
        const notices = [];
        if (week.sessions) notices.push(`${week.sessions} zabeleženih aktivnosti ta teden. Vsaka izvedba šteje k rednosti.`);
        else notices.push("Začni z izvedljivo aktivnostjo in jo dodaj v plan. Ta teden še ni zabeležene izvedbe.");
        if (week.aerobic_equivalent >= profile.aerobic_goal) notices.push("Tedenski aerobni cilj dosežen. Dobro opravljeno!");
        else notices.push(`Do tvojega aerobnega cilja manjka ${fmt(profile.aerobic_goal - week.aerobic_equivalent)} enakovrednih minut.`);
        if (week.strength_days >= profile.strength_goal) notices.push("Tudi cilj dni za moč je dosežen.");
        else notices.push(`Za cilj moči dodaj še ${fmt(profile.strength_goal - week.strength_days)} dni vadbe.`);
        if (week.missing_duration || week.unknown_intensity || week.unknown_strength_intensity) notices.push(`Nepopolni podatki: ${week.missing_duration} aktivnosti brez trajanja, ${week.unknown_intensity} aerobnih aktivnosti in ${week.unknown_strength_intensity} vadb za moč brez intenzivnosti. Aerobni seštevek vključuje le znane minute in intenzivnost. Cilj moči vključuje dneve z zmerno ali visoko intenzivnostjo.`);
        el("fitness-encouragement").innerHTML = notices.map(text => `<p class="small text-muted">${escape(text)}</p>`).join("");
        const insights = [];
        if (!profile.height_cm) insights.push("Vnesi višino v Predloge in nastavitve za izračun ITM in razmerja pas/višina.");
        if (weight?.bmi != null) {
            const bmi = weight.bmi;
            const category = bmi < 18.5 ? "pod običajnim razponom" : bmi < 25 ? "v običajnem razponu" : bmi < 30 ? "povišan" : "visok";
            insights.push(`ITM ${fmt(bmi)}: ${category}. Splošni referenčni razpon za odrasle je 18,5–24,9; razlaga je odvisna tudi od telesne sestave in okoliščin.`);
        }
        if (waist?.waist_height_ratio != null) {
            const ratio = waist.waist_height_ratio;
            if (weight?.bmi != null && weight.bmi < 35) {
                insights.push(ratio >= 0.6 ? "Pas/višina je 0,6 ali več: orientacija za večjo osrednjo zamaščenost. Smiselna je strokovna razlaga v kontekstu drugih dejavnikov." : ratio >= 0.5 ? "Pas/višina je 0,5 ali več: orientacija za povečano osrednjo zamaščenost. Spremljaj trend in ga po potrebi obravnavaj z zdravnikom." : "Pas je manjši od polovice višine. Spremljaj dolgoročen trend.");
            } else insights.push("Razmerje pas/višina je izračunano. Razvrstitve ne prikazujemo brez ITM pod 35.");
        }
        for (const [key, label, unit] of [["weight_kg", "teže", "kg"], ["waist_cm", "obsega pasu", "cm"]]) {
            const rows = state.measurements.filter(row => row[key] != null);
            if (rows.length > 1) {
                const last = rows.at(-1), previous = rows.at(-2), delta = last[key] - previous[key];
                insights.push(`Sprememba ${label} od ${timestampLabel(previous.timestamp)}: ${delta > 0 ? "+" : ""}${fmt(delta)} ${unit}. Primerjaj meritve v podobnih pogojih.`);
            }
        }
        if (!state.measurements.length) insights.push("Dodaj prvo meritev. Težo in pas lahko beležiš ločeno.");
        else if (weight && localDateTime(weight.timestamp).date < addDays(state.today, -14)) insights.push("Zadnja teža je starejša od dveh tednov. Nova meritev bo osvežila pregled.");
        el("fitness-insights").innerHTML = insights.map(text => `<p class="small">${escape(text)}</p>`).join("");
    }
    function renderMeasurements() {
        const rows = [...state.measurements].reverse();
        if (!rows.length) { el("fitness-measurements").innerHTML = '<p class="admin-empty">Meritev še ni. Dodaj težo, pas ali opombo.</p>'; return; }
        el("fitness-measurements").innerHTML = `<table class="table"><thead><tr>${["Datum in ura", "Teža (kg)", "Pas (cm)", "ITM", "Pas/višina", "Na tešče", "Zjutraj", "Po veliki potrebi", "Opomba", "Dejanja"].map(label => `<th scope="col">${label}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr data-entry-id="${escape(row.id)}"><td class="fitness-value">${escape(timestampLabel(row.timestamp))}</td><td>${fmt(row.weight_kg)}</td><td>${fmt(row.waist_cm)}</td><td>${fmt(row.bmi)}</td><td>${fmt(row.waist_height_ratio, 3)}</td><td>${boolLabel(row.fasting)}</td><td>${boolLabel(row.morning)}</td><td>${boolLabel(row.after_bowel)}</td><td style="min-width:140px;white-space:pre-wrap;overflow-wrap:anywhere">${escape(row.notes)}</td><td>${actions("measurements", row)}</td></tr>`).join("")}</tbody></table>`;
    }
    function renderSuggestions() {
        const kind = el("fitness-suggestion-kind").value;
        el("fitness-suggestions").innerHTML = state.suggestions.filter(row => kind === "all" || row.kind === kind).map(row => card(row, "suggestions")).join("");
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
            return `<div class="fitness-card"><h3>${kinds[kind]}</h3><strong class="fitness-distance-total">${measured.length ? fmt(distance, 3) : "—"} km</strong><p>Zabeleženi čas: <strong>${timed.length ? clock(seconds) : "—"}</strong></p><p>${kind === "running" ? "Skupni tempo" : "Povprečna hitrost"}: <strong>${average}</strong></p><small>${sessions.length} izvedb · ${sessions.length - measured.length} brez razdalje · ${sessions.length - timed.length} brez časa. Izračun tempa/hitrosti: ${paired.length} popolnih izvedb.</small></div>`;
        }).join("");
    }
    function renderAccess() {
        const progress = state.plan_progress;
        el("fitness-access-status").textContent = `${parityLabel(state.today)} · ${progress.week_completed} izvedb iz plana v tekočem tednu.`;
        el("fitness-plan-progress").innerHTML = `<strong>Načrti zadnjih 7 dni: ${progress.recent_completed} / ${progress.recent_total} opravljenih</strong><p class="small text-muted">${dateLabel(progress.recent_start)}–${dateLabel(progress.recent_end)} · šteje tudi izvedba na drug dan.</p>`;
        const node = el("fitness-access-suggestions");
        node.hidden = progress.allowed;
        if (progress.allowed) { node.innerHTML = ""; return; }
        const due = progress.due.length ? progress.due : progress.upcoming;
        const heading = progress.due.length ? "Za opraviti · načrtovano v zadnjih treh dneh" : "V zadnjih treh dneh ni neopravljene vadbe. Izberi iz plana tega tedna";
        node.innerHTML = due.length ? `<h3>${heading}</h3><div class="fitness-template-grid">${due.map(row => `<article class="fitness-card"><h3>${escape(row.title)}</h3><small>Načrtovano: ${dateLabel(row.date)} · ${sessionMeta(row, "plan")}</small>${row.description ? `<p>${escape(row.description)}</p>` : ""}${row.advice ? `<details class="fitness-advice"><summary>Nasvet</summary><p>${escape(row.advice)}</p></details>` : ""}${row.tutorial_url ? `<a href="${escape(row.tutorial_url)}" target="_blank" rel="noopener noreferrer">Tutorial ↗</a>` : ""}<div class="admin-actions"><button class="btn btn-primary btn-sm" type="button" data-complete-due="${escape(row.id)}">Zabeleži izvedbo</button></div></article>`).join("")}</div>` : '<p>Za ta teden še nimaš neopravljene aktivnosti v planu. Razporedi predlog vadbe ali dodaj svojo aktivnost v dvotedenski plan.</p>';
    }
    function renderCycle() {
        el("fitness-cycle-library").innerHTML = state.suggestions.map(row => `<button type="button" class="btn btn-sm btn-outline-primary" data-schedule-suggestion="${escape(row.id)}">${escape(row.title)}</button>`).join("");
        el("fitness-cycle-plan").innerHTML = ["odd", "even"].map(parity => {
            const current = state.plan_progress.parity === parity;
            return `<section class="fitness-cycle-week${current ? " is-current" : ""}" data-parity="${parity}"><h3>${parity === "odd" ? "Lihi tedni" : "Sodi tedni"}${current ? " · ta teden" : ""}</h3><div class="fitness-week-grid">${weekdays.map((day, index) => `<div class="fitness-day"><h3>${day}</h3>${state.schedule.filter(row => row.parity === parity && row.weekday === index).map(row => card(row, "schedule")).join("")}<button type="button" class="btn btn-sm btn-outline-primary" data-schedule-day="${parity}:${index}" aria-label="Dodaj vadbo: ${parity === "odd" ? "lihi" : "sodi"} tedni, ${day}">+ Vadba</button></div>`).join("")}</div></section>`;
        }).join("");
    }
    function renderPlan() {
        const start = monday(el("fitness-week").value || state.today), end = addDays(start, 13);
        el("fitness-plan-range").textContent = `${dateLabel(start)}–${dateLabel(end)}`;
        const rows = state.plan.filter(row => row.date >= start && row.date <= end);
        const planned = rows.filter(row => row.status === "planned");
        const minutes = planned.reduce((sum, row) => sum + (row.duration_min || 0), 0);
        const unknown = planned.filter(row => row.duration_min == null).length;
        el("fitness-plan-summary").textContent = `${planned.length} načrtovanih aktivnosti · ${fmt(minutes)} znanih minut${unknown ? ` · ${unknown} brez trajanja` : ""} · ${rows.filter(row => row.status === "completed").length} opravljenih · ${rows.filter(row => row.status === "skipped").length} preskočenih`;
        el("fitness-plan").innerHTML = [0, 7].map(offset => {
            const first = addDays(start, offset);
            return `<section class="fitness-cycle-week"><h3>${parityLabel(first)} · ${dateLabel(first)}–${dateLabel(addDays(first, 6))}</h3><div class="fitness-week-grid">${weekdays.map((name, index) => {
                const day = addDays(first, index), daily = rows.filter(row => row.date === day);
                return `<div class="fitness-day${day === state.today ? " is-today" : ""}"><h3>${name}</h3><small>${dateLabel(day)}</small>${daily.map(row => card(row, "plan")).join("")}<button type="button" class="btn btn-sm btn-outline-primary mt-2" data-plan-day="${day}" aria-label="Dodaj aktivnost: ${name}, ${dateLabel(day)}">+ Aktivnost</button></div>`;
            }).join("")}</div></section>`;
        }).join("");
    }
    function emptyChart(id, text) { el(id).innerHTML = `<p class="admin-empty">${escape(text)}</p>`; }
    const svgText = (x, y, label, extra = "") => `<text x="${x}" y="${y}" font-size="11" fill="#627589" ${extra}>${escape(label)}</text>`;
    function lineChart(id, key, label, digits = 1, references = []) {
        const guides = references.map(reference => typeof reference === "number" ? { value: reference, label: `Orientacija ${fmt(reference, digits)}`, color: "#b47d35" } : reference);
        const period = el("fitness-period").value;
        const cutoff = period === "all" ? "" : addDays(state.today, -Number(period));
        const comparable = el("fitness-comparable").checked;
        const allRows = state.measurements.filter(row => row[key] != null && (!comparable || (row.fasting === true && row.morning === true && row.after_bowel === true)));
        const rows = allRows.filter(row => !cutoff || localDateTime(row.timestamp).date >= cutoff);
        if (!rows.length) { emptyChart(id, (key === "bmi" || key === "waist_height_ratio") && !state.profile.height_cm ? "Za ta prikaz potrebujemo višino in ustrezne meritve." : "Za izbrano obdobje in pogoje ni meritev."); return; }
        const width = Math.max(320, Math.min(540, el(id).clientWidth || 540)), height = 245, left = 52, right = 20, top = 25, bottom = 35;
        const times = rows.map(row => +new Date(row.timestamp));
        let minTime = Math.min(...times), maxTime = Math.max(...times);
        if (minTime === maxTime) { minTime -= 43200000; maxTime += 43200000; }
        const averages = key === "weight_kg" ? rows.map(row => {
            const end = +new Date(row.timestamp), start = end - 7 * 86400000;
            const samples = allRows.filter(sample => +new Date(sample.timestamp) > start && +new Date(sample.timestamp) <= end);
            return samples.reduce((sum, sample) => sum + sample[key], 0) / samples.length;
        }) : [];
        const values = [...rows.map(row => row[key]), ...averages, ...guides.map(reference => reference.value)];
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
        if (averages.length) contents += `<polyline points="${averages.map((value, index) => `${x(times[index])},${y(value)}`).join(" ")}" fill="none" stroke="#587dcc" stroke-width="2" stroke-dasharray="5 3"><title>Povprečje meritev v preteklih 7 dneh</title></polyline>`;
        rows.forEach((row, index) => {
            const caption = `${timestampLabel(row.timestamp)}: ${fmt(row[key], digits)}${averages.length ? `; 7-dnevno povprečje ${fmt(averages[index])}` : ""}`;
            contents += `<circle class="fitness-chart-point" cx="${x(times[index])}" cy="${y(row[key])}" r="4" fill="#256b73" tabindex="0" aria-label="${escape(caption)}"><title>${escape(caption)}</title></circle>`;
        });
        contents += svgText(left, height - 8, dateLabel(localDateTime(rows[0].timestamp).date)) + svgText(width - right, height - 8, dateLabel(localDateTime(rows.at(-1).timestamp).date), 'text-anchor="end"');
        el(id).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(label)}">${contents}</svg>`;
    }
    function renderCharts() {
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
        el("fitness-activity-legend").innerHTML = Object.entries(kinds).map(([kind, label]) => `<span><i style="background:${colors[kind]}"></i>${label}</span>`).join("");
        const weeklyDistance = (week, kind) => {
            const count = week.sessions_by_kind[kind], missing = week.missing_distance_by_kind[kind];
            return count && count === missing ? "—" : `${fmt(week.distance_by_kind[kind], 3)}${missing ? " + ?" : ""}`;
        };
        el("fitness-weekly-table").innerHTML = `<table class="table"><thead><tr>${["Teden od", "Minute skupaj", "Tek (km)", "Kolo (km)", "Aerobne enakovredne minute", "Dnevi za moč", "Brez trajanja", "Brez aerobne intenzivnosti"].map(label => `<th scope="col">${label}</th>`).join("")}</tr></thead><tbody>${[...weekly].reverse().map(week => `<tr><td>${dateLabel(week.date)}</td><td>${fmt(week.minutes)}</td><td>${weeklyDistance(week, "running")}</td><td>${weeklyDistance(week, "cycling")}</td>${[week.aerobic_equivalent, week.strength_days, week.missing_duration, week.unknown_intensity].map(value => `<td>${fmt(value)}</td>`).join("")}</tr>`).join("")}</tbody></table><p class="form-text">»+ ?«: del razdalj ni znan. »—«: pri zabeleženih izvedbah ni znana nobena razdalja.</p>`;
    }
    function render() {
        renderAccess(); renderCycle(); renderSummary(); renderMeasurements(); renderPlan(); renderCharts(); renderSuggestions(); renderDistanceSummary();
        el("fitness-activities").innerHTML = [...state.activities].reverse().map(row => card(row, "activities")).join("") || '<p class="admin-empty">Izvedenih aktivnosti še ni. Dodaj prvo vadbo ali potrdi izvedbo iz plana.</p>';
        el("fitness-templates").innerHTML = state.templates.map(row => card(row, "templates")).join("") || '<p class="admin-empty">Ustvari predlogo svojih priljubljenih aktivnosti.</p>';
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
    function applyTemplate(row) {
        if (!row) return;
        const copy = { ...row }; delete copy.date; delete copy.timestamp; delete copy.status; fillForm(el("fitness-session-form"), copy);
        el("session-elapsed").value = sessionSeconds(row) == null ? "" : clock(sessionSeconds(row));
        updateSessionFields(); updatePerformance();
    }
    function openSession(collection, row, options = {}) {
        const form = el("fitness-session-form"); form.reset(); formError(form);
        editContext = { collection, id: row?.id, complete: options.complete };
        const title = options.complete ? "Zabeleži izvedbo" : `${row ? "Uredi" : "Nova"} ${collection === "templates" ? "predloga" : collection === "schedule" ? "ponavljajoča vadba" : collection === "plan" ? "aktivnost v planu" : "aktivnost"}`;
        el("fitness-session-title").textContent = title;
        el("session-template-field").hidden = collection === "templates" || !!row;
        el("session-template").innerHTML = '<option value="">Lastna aktivnost</option>' + [["Moje predloge", state.templates], ["Predlagane oblike vadbe", state.suggestions]].map(([label, rows]) => `<optgroup label="${label}">${rows.map(template => `<option value="${escape(template.id)}">${escape(template.title)}</option>`).join("")}</optgroup>`).join("");
        el("session-actual-date").hidden = collection !== "activities" && !options.complete;
        el("session-plan-date").hidden = collection !== "plan" || !!options.complete;
        el("session-status-field").hidden = collection !== "plan" || !!options.complete || row?.status === "completed";
        el("session-repeat-fields").hidden = !["plan", "schedule"].includes(collection) || !!options.complete || (collection === "plan" && !!row);
        el("session-save").textContent = options.complete ? "Shrani izvedbo" : collection === "templates" ? "Shrani predlogo" : ["plan", "schedule"].includes(collection) ? "Shrani v plan" : "Shrani aktivnost";
        if (row) { fillForm(form, row); el("session-elapsed").value = sessionSeconds(row) == null ? "" : clock(sessionSeconds(row)); if (row.status === "completed") el("session-status").value = "planned"; }
        initDate(form, "session", options.complete ? null : row?.timestamp);
        el("session-planned-context").hidden = !options.complete;
        el("session-planned-context").textContent = options.complete ? `Načrtovano: ${dateLabel(row.date)}. Zgoraj vnesi dejanski datum izvedbe; privzeto je danes.` : "";
        const selectedWeek = monday(el("fitness-week").value || state.today);
        const defaultPlanDay = selectedWeek === monday(state.today) ? state.today : selectedWeek;
        el("plan-date").value = row?.date || options.date || defaultPlanDay;
        el("session-repeat").value = row?.parity || options.parity || (collection === "schedule" ? state.plan_progress.parity : "");
        el("session-repeat").querySelector('option[value=""]').disabled = collection === "schedule";
        el("session-weekday").value = row?.weekday ?? options.weekday ?? ((dayDate(el("plan-date").value).getUTCDay() + 6) % 7);
        if (options.template) { el("session-template").value = options.template.id; applyTemplate(options.template); }
        updatePlanFields(); updateSessionFields(); updatePerformance();
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
        try {
            await api(path, method, payload);
            if (dialog) dialog.close(); else profileDirty = false;
            if (path === "/plan" || /^\/plan\/[^/]+$/.test(path)) { el("fitness-week").value = payload.date; selectTab("plan"); }
            if (path === "/schedule" || /^\/schedule\/[^/]+$/.test(path)) selectTab("plan");
            await refresh("Podatki shranjeni.");
        } catch (error) { formError(form, error.message || "Povezava ni uspela. Vnos je ohranjen; poskusi znova."); }
        finally { button.disabled = false; delete form.dataset.saving; }
    }
    el("fitness-measurement-form").addEventListener("submit", event => {
        event.preventDefault(); const form = event.currentTarget, payload = serialize(form); payload.timestamp = actualTimestamp(form);
        ["fasting", "morning", "after_bowel"].forEach(name => { payload[name] = payload[name] === "" ? null : payload[name] === "true"; });
        save(form, `/measurements${editContext.id ? `/${editContext.id}` : ""}`, editContext.id ? "PUT" : "POST", payload, el("fitness-measurement-dialog"));
    });
    el("fitness-session-form").addEventListener("submit", event => {
        event.preventDefault(); const form = event.currentTarget, payload = serialize(form), context = editContext;
        payload.timestamp = actualTimestamp(form); payload.date = payload.plan_date;
        const recurring = ["plan", "schedule"].includes(context.collection) && !context.complete && payload.parity;
        const collection = recurring ? "schedule" : context.collection;
        save(form, context.complete ? `/plan/${context.id}/complete` : `/${collection}${context.id ? `/${context.id}` : ""}`, context.complete || !context.id ? "POST" : "PUT", payload, el("fitness-session-dialog"));
    });
    el("fitness-profile").addEventListener("input", () => { profileDirty = true; });
    el("fitness-profile").addEventListener("submit", event => { event.preventDefault(); save(event.currentTarget, "/profile", "PUT", serialize(event.currentTarget)); });
    el("session-template").addEventListener("change", event => applyTemplate(workout(event.target.value)));
    function updatePlanFields() {
        const planning = ["plan", "schedule"].includes(editContext?.collection) && !editContext?.complete;
        const recurring = planning && !!el("session-repeat").value;
        el("session-plan-date").hidden = !planning || recurring;
        el("plan-date").disabled = !planning || recurring;
        el("plan-date").required = planning && !recurring;
        el("session-weekday-field").hidden = !recurring;
        el("session-weekday").disabled = !recurring;
        el("session-repeat").disabled = !planning;
        if (recurring) el("session-status-field").hidden = true;
        else el("session-status-field").hidden = !planning || editContext?.collection === "schedule" || !!state.plan.find(row => row.id === editContext?.id)?.activity_id;
    }
    el("session-repeat").addEventListener("change", updatePlanFields);
    function updateSessionFields() {
        const kind = el("session-kind").value, usesEquipment = ["cardio", "strength"].includes(kind);
        el("session-equipment-field").hidden = !usesEquipment; el("session-equipment").disabled = !usesEquipment;
        el("session-cadence-field").hidden = kind !== "cycling"; el("session-cadence").disabled = kind !== "cycling";
    }
    function updatePerformance() {
        const elapsed = el("session-elapsed").value;
        const minutes = el("session-duration").value;
        const seconds = elapsed ? parseClock(elapsed) : minutes ? Math.round(Number(minutes) * 60) : null;
        const value = performance({ kind: el("session-kind").value, duration_seconds: seconds, distance_km: Number(el("session-distance").value) }, editContext?.collection === "activities" || editContext?.complete ? "activities" : "plan");
        el("session-performance").textContent = value; el("session-performance").hidden = !value;
    }
    el("session-kind").addEventListener("change", () => { updateSessionFields(); updatePerformance(); });
    el("session-insert-advice").addEventListener("click", () => { el("session-advice").value = state.general_advice[el("session-kind").value] || ""; });
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
            el("fitness-delete-description").textContent = (row.title || `Meritev: ${timestampLabel(row.timestamp)}`) + (deleteContext.collection === "schedule" ? ". Odstrani ponavljanje in še neopravljene kopije od tega tedna naprej. Opravljene izvedbe ostanejo." : "");
            formError(el("fitness-delete-dialog")); el("fitness-delete-dialog").showModal();
        }
        if (button.dataset.planDay) openSession("plan", null, { date: button.dataset.planDay });
        if (button.dataset.scheduleDay) { const [parity, weekday] = button.dataset.scheduleDay.split(":"); openSession("schedule", null, { parity, weekday: Number(weekday) }); }
        if (button.dataset.scheduleSuggestion) openSession("schedule", null, { template: workout(button.dataset.scheduleSuggestion) });
        if (button.hasAttribute("data-open-plan")) { selectTab("plan"); el("panel-plan").scrollIntoView({ block: "start" }); }
        if (button.dataset.useTemplate) openSession("plan", null, { template: state.templates.find(row => row.id === button.dataset.useTemplate) });
        if (button.dataset.useSuggestion) openSession("plan", null, { template: workout(button.dataset.useSuggestion) });
        if (button.dataset.saveSuggestion) openSession("templates", null, { template: workout(button.dataset.saveSuggestion) });
        if (button.hasAttribute("data-fitness-settings")) { selectTab("templates"); el("fitness-settings").scrollIntoView({ block: "start" }); el("fitness-target-weight").focus({ preventScroll: true }); }
        if (button.dataset.complete) openSession("plan", state.plan.find(row => row.id === button.dataset.complete), { complete: true });
        if (button.dataset.completeDue) openSession("plan", state.plan.find(row => row.id === button.dataset.completeDue), { complete: true });
    });
    el("fitness-confirm-delete").addEventListener("click", async event => {
        const button = event.currentTarget; button.disabled = true; button.dataset.saving = "true";
        try { await api(`/${deleteContext.collection}/${deleteContext.id}`, "DELETE"); el("fitness-delete-dialog").close(); await refresh("Zapis izbrisan."); }
        catch (error) { formError(el("fitness-delete-dialog"), error.message || "Brisanje ni uspelo. Poskusi znova."); }
        finally { button.disabled = false; delete button.dataset.saving; }
    });
    document.querySelectorAll(".fitness-dialog").forEach(dialog => dialog.addEventListener("cancel", event => { if (dialog.querySelector('[data-saving="true"]')) event.preventDefault(); }));
    el("fitness-week").value = state.today;
    let planRequest = 0;
    async function loadPlan() {
        const request = ++planRequest;
        try { const data = await api(`/data?start=${monday(el("fitness-week").value || state.today)}`); if (request === planRequest) { state = data; render(); } }
        catch (error) { if (request === planRequest) message(error.message || "Plana ni mogoče naložiti.", true); }
    }
    el("fitness-week").addEventListener("change", loadPlan);
    el("fitness-prev-week").addEventListener("click", () => { el("fitness-week").value = addDays(el("fitness-week").value || state.today, -7); loadPlan(); });
    el("fitness-next-week").addEventListener("click", () => { el("fitness-week").value = addDays(el("fitness-week").value || state.today, 7); loadPlan(); });
    el("fitness-this-week").addEventListener("click", () => { el("fitness-week").value = state.today; loadPlan(); });
    el("fitness-period").addEventListener("change", renderCharts);
    el("fitness-comparable").addEventListener("change", renderCharts);
    el("fitness-suggestion-kind").addEventListener("change", renderSuggestions);
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
