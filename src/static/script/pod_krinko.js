(() => {
    const root = document.getElementById("podKrinko");
    if (!root) return;
    const el = id => document.getElementById(id);
    const storageKey = "podKrinko_data";
    const count = el("nPlayersSlider");
    const spies = el("nUndercoversSlider");
    const whites = el("nWhitesSlider");
    const roleNames = { prebivalec: "Prebivalec", vohun: "Vohun", beli: "Gospod v belem" };
    const scoreValues = { prebivalec: 2, vohun: 5, beli: 7 };
    const normalize = value => String(value || "").trim().normalize("NFC").toLocaleLowerCase("sl");
    const clamp = (value, min, max) => Math.max(min, Math.min(max, Math.trunc(Number(value) || 0)));
    let profiles = [];
    let scores = new Map();
    let pendingAction = null;
    let loading = false;
    let state = { phase: "setup", players: [], words: [], revealIndex: 0, round: 0, starter: -1, mime: -1, eliminated: -1 };

    function message(text = "") {
        el("gameMessage").textContent = text;
        el("gameMessage").hidden = !text;
    }

    function captureProfiles() {
        root.querySelectorAll(".pk-name-row").forEach((row, index) => {
            profiles[index] = { ime: row.querySelector('input[type="text"]').value.trim(), spol: row.querySelector('input[type="radio"]:checked').value };
        });
    }

    function persist() {
        captureProfiles();
        try {
            localStorage.setItem(storageKey, JSON.stringify({
                version: 2, nPlayers: Number(count.value), nUndercovers: Number(spies.value), nWhites: Number(whites.value),
                nemec: el("nemec").checked, igralci: profiles.slice(0, Number(count.value)),
                tocke: Array.from(scores, ([ime, tocke]) => ({ ime, tocke })),
            }));
        } catch (_error) {
            el("storageNote").textContent = "Shranjevanje v tem brskalniku ni na voljo. Igro lahko vseeno odigrate.";
        }
    }

    function renderNames() {
        captureProfiles();
        el("namesInput").replaceChildren();
        for (let index = 0; index < Number(count.value); index++) {
            const profile = profiles[index] || { ime: "", spol: "f" };
            const row = document.createElement("div");
            row.className = "pk-name-row";
            row.innerHTML = `<span aria-hidden="true">${index + 1}</span><input type="text" id="playerName${index}" maxlength="30" autocomplete="off" placeholder="Igralec ${index + 1}" aria-label="Ime igralca ${index + 1}" required><div class="pk-avatar-options"><label><input type="radio" name="avatar${index}" value="f" aria-label="Ženski avatar, igralec ${index + 1}"><img src="/static/pod_krinko_avatars/neznanka.png" alt=""></label><label><input type="radio" name="avatar${index}" value="m" aria-label="Moški avatar, igralec ${index + 1}"><img src="/static/pod_krinko_avatars/neznanec.png" alt=""></label></div>`;
            row.querySelector('input[type="text"]').value = profile.ime;
            row.querySelector(`input[value="${profile.spol === "m" ? "m" : "f"}"]`).checked = true;
            el("namesInput").appendChild(row);
        }
    }

    function suggestRoles() {
        count.value = clamp(count.value, 3, 20);
        const hiddenRoles = Math.floor(Number(count.value) / 2);
        spies.value = Math.ceil(hiddenRoles / 2);
        whites.value = Math.floor(hiddenRoles / 2);
        constrainRoles();
    }

    function constrainRoles(changed = spies) {
        count.value = clamp(count.value, 3, 20);
        const max = Math.floor(Number(count.value) / 2);
        const other = changed === whites ? spies : whites;
        changed.value = clamp(changed.value, 0, max);
        other.value = clamp(other.value, 0, max - Number(changed.value));
        if (Number(spies.value) + Number(whites.value) === 0) other.value = 1;
        spies.max = whites.max = max;
        el("nPlayersText").value = count.value;
        const residents = Number(count.value) - Number(spies.value) - Number(whites.value);
        el("teamSummary").textContent = `Prebivalci: ${residents} · Vohuni: ${spies.value} · Gospodje v belem: ${whites.value}`;
        root.querySelectorAll("[data-adjust]").forEach(button => {
            const input = el(button.dataset.adjust);
            button.disabled = Number(button.dataset.delta) < 0 ? Number(input.value) <= Number(input.min) : Number(input.value) >= Number(input.max);
        });
    }

    function readStorage(key) {
        try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (_error) { return null; }
    }

    function restore() {
        const saved = readStorage(storageKey) || readStorage("podKrinkoData");
        suggestRoles();
        if (saved && typeof saved === "object") {
            count.value = clamp(saved.nPlayers || 5, 3, 20);
            suggestRoles();
            spies.value = clamp(saved.nUndercovers ?? spies.value, 0, 10);
            whites.value = clamp(saved.nWhites ?? whites.value, 0, 10);
            el("nemec").checked = saved.nemec === true;
            const savedProfiles = saved.igralci || readStorage("podKrinko_zadnjaImena") || saved.tocke;
            if (Array.isArray(savedProfiles)) profiles = savedProfiles.slice(0, 20).map(p => ({ ime: String(p?.ime || "").slice(0, 30), spol: p?.spol === "m" ? "m" : "f" }));
            if (Array.isArray(saved.tocke)) scores = new Map(saved.tocke.filter(p => p && typeof p.ime === "string").map(p => [normalize(p.ime), clamp(p.tocke, 0, 1000000)]));
        }
        constrainRoles();
        renderNames();
    }

    function setPhase(phase) {
        state.phase = phase;
        const step = phase === "discussion" || phase === "voting" ? "play" : phase;
        el("nastavitve").hidden = phase !== "setup";
        el("igra").hidden = phase === "setup" || phase === "results";
        el("resultsPanel").hidden = phase !== "results";
        el("revealPanel").hidden = phase !== "reveal";
        el("playPanel").hidden = phase !== "discussion" && phase !== "voting";
        root.querySelectorAll("[data-step]").forEach(item => {
            if (item.dataset.step === step) item.setAttribute("aria-current", "step");
            else item.removeAttribute("aria-current");
        });
    }

    function openDialog(id) {
        const dialog = el(id);
        if (!dialog.open) dialog.showModal();
    }

    function confirmAction(title, text, label, action) {
        pendingAction = action;
        el("actionTitle").textContent = title;
        el("actionText").textContent = text;
        el("confirmActionButton").textContent = label;
        openDialog("actionDialog");
    }

    function setLoading(value) {
        loading = value;
        root.setAttribute("aria-busy", String(value));
        el("setupForm").inert = value;
        el("revealPanel").inert = value;
        el("playPanel").inert = value;
        el("resultsPanel").inert = value;
        root.querySelectorAll("[data-start-game]").forEach(button => {
            if (value) { button.dataset.label = button.innerHTML; button.textContent = "Pridobivam besede …"; }
            else button.innerHTML = button.dataset.label || button.innerHTML;
            button.disabled = value;
        });
        root.querySelectorAll("[data-open-settings]").forEach(button => { button.disabled = value; });
    }

    async function startGame() {
        if (loading) return;
        captureProfiles();
        const team = profiles.slice(0, Number(count.value));
        const fields = [...root.querySelectorAll('.pk-name-row input[type="text"]')];
        fields.forEach(field => field.removeAttribute("aria-invalid"));
        const emptyIndex = team.findIndex(p => !p.ime);
        const duplicateIndex = team.findIndex((p, index) => team.findIndex(other => normalize(other.ime) === normalize(p.ime)) !== index);
        const invalidIndex = emptyIndex >= 0 ? emptyIndex : duplicateIndex;
        if (invalidIndex >= 0) {
            message(emptyIndex >= 0 ? "Vnesi ime vsakega igralca, da bo vsak našel svojo kartico." : "Vsak igralec potrebuje svoje ime. Podvojeno ime spremeni.");
            fields[invalidIndex].setAttribute("aria-invalid", "true");
            fields[invalidIndex].focus();
            return;
        }
        constrainRoles();
        message();
        setLoading(true);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const response = await fetch("/pod_krinko/new_words", { signal: controller.signal, cache: "no-store" });
            if (response.status === 429) {
                message("Dosežena je urna omejitev novih besed. Počakaj ali se prijavi za nadaljevanje.");
                const link = document.createElement("a");
                link.href = "/login"; link.textContent = " Prijava";
                el("gameMessage").appendChild(link);
                return;
            }
            if (!response.ok) throw new Error("words_unavailable");
            const words = await response.json();
            if (!Array.isArray(words) || words.length < 2 || words.some(word => typeof word !== "string" || !word.trim())) throw new Error("invalid_words");
            const roles = [
                ...Array(Number(count.value) - Number(spies.value) - Number(whites.value)).fill("prebivalec"),
                ...Array(Number(spies.value)).fill("vohun"), ...Array(Number(whites.value)).fill("beli"),
            ];
            for (let index = roles.length - 1; index > 0; index--) {
                const swap = Math.floor(Math.random() * (index + 1));
                [roles[index], roles[swap]] = [roles[swap], roles[index]];
            }
            state = { phase: "reveal", words: words.map(word => word.trim()), revealIndex: 0, round: 0, starter: -1,
                mime: el("nemec").checked ? Math.floor(Math.random() * team.length) : -1, eliminated: -1,
                players: team.map((p, index) => ({ ...p, role: roles[index], active: true, points: scores.get(normalize(p.ime)) || 0, gained: 0 })),
            };
            persist();
            setPhase("reveal");
            renderReveal();
            el("gameTitle").focus();
        } catch (_error) {
            message("Besed ni bilo mogoče pridobiti. Preveri povezavo in poskusi znova. Ekipa in točke so ohranjene.");
        } finally {
            clearTimeout(timeout);
            setLoading(false);
        }
    }

    function requestStart() {
        if (loading) return;
        if (["reveal", "discussion", "voting"].includes(state.phase)) confirmAction("Začneš novo igro?", "Trenutna igra se bo končala brez novih točk. Ekipa in dosedanje točke se ohranijo.", "Nove besede", startGame);
        else startGame();
    }

    function renderReveal() {
        el("phaseLabel").textContent = "Skrivne besede";
        el("gameTitle").textContent = "Podaj napravo";
        el("revealPlayer").textContent = state.players[state.revealIndex].ime;
        el("revealProgress").max = state.players.length;
        el("revealProgress").value = state.revealIndex;
        el("revealCount").textContent = `${state.revealIndex} od ${state.players.length} igralcev je že pogledalo besedo`;
    }

    function revealSecret() {
        if (state.phase !== "reveal" || el("secretDialog").open) return;
        const player = state.players[state.revealIndex];
        el("secretName").textContent = player.ime;
        el("secretLabel").textContent = player.role === "beli" ? "Tvoja skrivna vloga" : "Tvoja skrivna beseda";
        el("secretWord").textContent = player.role === "beli" ? "Gospod v belem" : state.words[player.role === "vohun" ? 1 : 0];
        el("secretHelp").textContent = player.role === "beli" ? "Besede nimaš. Poslušaj namige in blefiraj. Ob izločitvi lahko enkrat ugibaš." : "Zapomni si besedo. Svoje vloge še ne poznaš.";
        openDialog("secretDialog");
    }

    function hideSecret() {
        if (!el("secretDialog").open) return;
        el("secretWord").textContent = "";
        el("secretName").textContent = "";
        el("secretDialog").close();
        state.revealIndex += 1;
        if (state.revealIndex >= state.players.length) beginRound();
        else { renderReveal(); el("revealButton").focus(); }
    }

    function avatar(player, reveal = false) {
        const file = reveal ? (player.role === "vohun" ? "pod_krinko" : player.role === "beli" ? "gospod_v_belem" : player.spol === "m" ? "civilist" : "civilistka") : player.spol === "m" ? "neznanec" : "neznanka";
        return `/static/pod_krinko_avatars/${file}.png`;
    }

    function renderCards() {
        el("kartice").replaceChildren();
        state.players.forEach((player, index) => {
            const card = document.createElement("article");
            card.className = `pk-card${player.active ? "" : " is-eliminated"}${index === state.starter && state.phase === "discussion" ? " is-first" : ""}`;
            const image = document.createElement("img"); image.src = avatar(player, !player.active); image.alt = "";
            const name = document.createElement("h3"); name.textContent = player.ime;
            const status = document.createElement("p"); status.textContent = !player.active ? `Izločen · ${roleNames[player.role]}` : index === state.starter && state.phase === "discussion" ? "Poda prvi namig" : "V igri";
            card.append(image, name, status);
            if (player.active && state.phase === "voting") {
                const button = document.createElement("button");
                button.type = "button"; button.className = "pk-button pk-button-quiet"; button.textContent = "Izloči";
                button.setAttribute("aria-label", `Izloči igralca ${player.ime}`);
                button.addEventListener("click", () => confirmAction("Izločitev igralca", `Je ${player.ime} dobil največ glasov? Po potrditvi se njegova vloga razkrije.`, "Izloči igralca", () => eliminate(index)));
                card.appendChild(button);
            }
            el("kartice").appendChild(card);
        });
    }

    function renderRound() {
        const voting = state.phase === "voting";
        el("phaseLabel").textContent = voting ? "Glasovanje" : "Namigi";
        el("gameTitle").textContent = voting ? "Kdo je najbolj sumljiv?" : "Poslušaj. Poveži. Posumi.";
        el("roundLabel").textContent = `Krog ${state.round}`;
        el("navodilo").textContent = voting ? "Pogovorite se in izberite igralca." : `Prvi namig poda ${state.players[state.starter].ime}.`;
        el("roundHelp").textContent = voting ? "Glasujte v živo. Izločite igralca z največ glasovi; ob izenačenju glasujte znova." : "Nato nadaljujte po vrsti. Vsak aktivni igralec naj z eno besedo opiše svojo skrivno besedo. Ne izgovorite je!";
        el("voteButton").hidden = voting;
        const mime = state.players[state.mime];
        el("mimeNotice").hidden = !mime?.active;
        el("mimeNotice").textContent = mime?.active ? `${mime.ime} je gospod Nemec: namig poda s pantomimo.` : "";
        const roles = ["prebivalec", "vohun", "beli"];
        el("stanje").replaceChildren(...roles.map(role => {
            const badge = document.createElement("span");
            badge.textContent = `${{ prebivalec: "Prebivalci", vohun: "Vohuni", beli: "Gospodje v belem" }[role]}: ${state.players.filter(p => p.active && p.role === role).length}`;
            return badge;
        }));
        renderCards();
    }

    function beginRound() {
        state.round += 1;
        const candidates = state.players.map((p, index) => ({ ...p, index })).filter(p => p.active && (state.round > 1 || p.role !== "beli"));
        state.starter = candidates[Math.floor(Math.random() * candidates.length)].index;
        setPhase("discussion"); renderRound(); el("gameTitle").focus();
    }

    function eliminate(index) {
        if (state.phase !== "voting" || !state.players[index]?.active) return;
        const player = state.players[index];
        player.active = false; state.eliminated = index;
        el("eliminationAvatar").src = avatar(player, true);
        el("eliminationTitle").textContent = `${player.ime} je izločen.`;
        el("eliminationRole").textContent = `Razkrita vloga: ${roleNames[player.role]}`;
        el("guessForm").hidden = player.role !== "beli";
        el("continueRoundButton").hidden = player.role === "beli";
        el("guessFeedback").hidden = true;
        el("ugibanje").value = "";
        renderCards(); openDialog("eliminationDialog");
        if (player.role === "beli") el("ugibanje").focus();
    }

    function guess(skip = false) {
        if (el("guessForm").hidden) return;
        const success = !skip && normalize(el("ugibanje").value) === normalize(state.words[0]);
        el("guessForm").hidden = true;
        if (success) {
            el("eliminationDialog").close(); finishGame("white", state.eliminated);
        } else {
            el("guessFeedback").hidden = false;
            el("guessFeedback").textContent = skip ? "Ugibanje je preskočeno. Igra se nadaljuje." : "Beseda ni prava. Igra se nadaljuje.";
            el("continueRoundButton").hidden = false; el("continueRoundButton").focus();
        }
    }

    function continueRound() {
        if (!el("guessForm").hidden) return;
        el("eliminationDialog").close();
        const alive = state.players.filter(p => p.active);
        const residents = alive.filter(p => p.role === "prebivalec");
        const enemies = alive.filter(p => p.role !== "prebivalec");
        if (!enemies.length) finishGame("residents");
        else if (residents.length <= 1) finishGame("enemies");
        else beginRound();
    }

    function renderScores(container, revealRoles = false) {
        container.replaceChildren();
        [...state.players].sort((a, b) => b.points - a.points).forEach((player, index) => {
            const row = document.createElement("div"); row.className = "pk-score-row";
            row.innerHTML = `<span>${index + 1}</span><div><strong></strong><small></small></div><div class="pk-score-total"></div>`;
            row.querySelector("strong").textContent = player.ime;
            row.querySelector("small").textContent = revealRoles ? `${roleNames[player.role]}${player.active ? "" : " · izločen"}` : "";
            row.querySelector(".pk-score-total").textContent = `${player.points} tč.`;
            if (revealRoles && player.gained) {
                const gain = document.createElement("small"); gain.textContent = `+${player.gained} v tej igri`; row.querySelector(".pk-score-total").appendChild(gain);
            }
            container.appendChild(row);
        });
    }

    function finishGame(winner, whiteIndex = -1) {
        if (state.phase === "results") return;
        const mime = state.players[state.mime];
        state.players.forEach((player, index) => {
            const won = winner === "white" ? index === whiteIndex : player.active && (winner === "residents" ? player.role === "prebivalec" : player.role !== "prebivalec");
            player.gained = won ? scoreValues[player.role] : 0;
            if (won && mime && mime.role === player.role && (winner === "white" ? state.mime === whiteIndex : mime.active)) player.gained += 2;
            player.points += player.gained;
            scores.set(normalize(player.ime), player.points);
        });
        el("resultsTitle").textContent = winner === "white" ? `${state.players[whiteIndex].ime} je uganil besedo!` : winner === "residents" ? "Prebivalci so razkrinkali vse!" : "Skrivne vloge so zmagale!";
        el("winnerDescription").textContent = winner === "white" ? "Gospod v belem je s pravilnim ugibanjem zaključil igro." : winner === "residents" ? "Vsi vohuni in gospodje v belem so izločeni." : "V igri je ostal največ en prebivalec.";
        el("besedi_rezultati").replaceChildren();
        ["Beseda prebivalcev", "Beseda vohunov"].forEach((label, index) => {
            const box = document.createElement("div"); const title = document.createElement("span"); const word = document.createElement("strong");
            title.textContent = label; word.textContent = index === 1 && !state.players.some(p => p.role === "vohun") ? "Brez vohunov" : state.words[index];
            box.append(title, word); el("besedi_rezultati").appendChild(box);
        });
        renderScores(el("osebe_rezultati"), true); persist(); setPhase("results"); el("resultsTitle").focus();
    }

    count.addEventListener("input", () => { suggestRoles(); renderNames(); persist(); });
    [spies, whites].forEach(input => input.addEventListener("input", () => { constrainRoles(input); persist(); }));
    root.querySelectorAll("[data-adjust]").forEach(button => button.addEventListener("click", () => {
        const input = el(button.dataset.adjust); input.value = Number(input.value) + Number(button.dataset.delta); input.dispatchEvent(new Event("input"));
    }));
    el("setupForm").addEventListener("input", event => { if (event.target.matches('input[type="text"]')) { event.target.removeAttribute("aria-invalid"); message(); } persist(); });
    el("setupForm").addEventListener("submit", event => { event.preventDefault(); requestStart(); });
    root.querySelectorAll("[data-start-game]:not([type='submit'])").forEach(button => button.addEventListener("click", requestStart));
    root.querySelectorAll("[data-open-settings]").forEach(button => button.addEventListener("click", () => {
        const open = () => { message(); setPhase("setup"); el("setupTitle").scrollIntoView({ block: "start" }); };
        if (state.phase === "results") open();
        else confirmAction("Urediš ekipo?", "Trenutna igra se bo končala brez novih točk. Imena in dosedanje točke se ohranijo.", "Uredi ekipo", open);
    }));
    el("resetButton").addEventListener("click", () => confirmAction("Ponastaviš ekipo in točke?", "Shranjena imena, nastavitve in vse dosedanje točke v tem brskalniku bodo izbrisani.", "Ponastavi", () => {
        el("namesInput").replaceChildren(); profiles = []; scores.clear(); count.value = 5; el("nemec").checked = false;
        state.players = []; suggestRoles(); renderNames(); persist(); message();
    }));
    el("rulesButton").addEventListener("click", () => openDialog("rulesDialog"));
    root.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
    el("confirmActionButton").addEventListener("click", () => { const action = pendingAction; pendingAction = null; el("actionDialog").close(); action?.(); });
    el("actionDialog").addEventListener("close", () => { pendingAction = null; });
    el("revealButton").addEventListener("click", revealSecret);
    el("hideSecretButton").addEventListener("click", hideSecret);
    el("secretDialog").addEventListener("cancel", event => { event.preventDefault(); hideSecret(); });
    el("voteButton").addEventListener("click", () => { setPhase("voting"); renderRound(); el("gameTitle").focus(); });
    el("eliminationDialog").addEventListener("cancel", event => { event.preventDefault(); if (el("guessForm").hidden) continueRound(); });
    el("guessForm").addEventListener("submit", event => { event.preventDefault(); guess(); });
    el("skipGuessButton").addEventListener("click", () => guess(true));
    el("continueRoundButton").addEventListener("click", continueRound);
    el("scoresButton").addEventListener("click", () => { renderScores(el("liveScores")); openDialog("scoresDialog"); });
    restore();
})();
