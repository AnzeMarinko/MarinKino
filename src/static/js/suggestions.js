(() => {
    const root = document.getElementById('suggestionsPage');
    if (!root) return;
    const form = document.getElementById('suggestionForm');
    const type = document.getElementById('suggestionType');
    const text = document.getElementById('suggestionText');
    const submit = document.getElementById('sendSuggestion');
    const clear = document.getElementById('clearSuggestion');
    const status = document.getElementById('suggestionStatus');
    const draftStatus = document.getElementById('suggestionDraftStatus');
    const hints = {
        'predlog za film': ['Dodaj naslov filma ali risanke, leto in povezavo, če jo imaš. Napiši tudi, zakaj ga priporočaš.', 'Na primer: naslov filma, leto izida in zakaj ga priporočaš …'],
        'predlog za glasbo': ['Napiši ime izvajalca in naslov pesmi ali albuma. Povezava pomaga najti pravo različico.', 'Izvajalec, naslov pesmi ali albuma, povezava …'],
        'nova funkcionalnost': ['Opiši, kaj bi rad naredil, kje bi funkcija pomagala in kako naj deluje.', 'Rad bi lahko … To bi pomagalo, ker …'],
        'izboljsava': ['Povej, na kateri podstrani bi nekaj spremenil in kaj bi bilo lažje za uporabo.', 'Na podstrani … bi izboljšal …'],
        'napaka': ['Dodaj podstran, korake pred napako ter kaj se je zgodilo. Napiši tudi, ali uporabljaš telefon ali računalnik.', 'Na strani … sem izbral … Pričakoval sem … Zgodilo se je …'],
        'komentar': ['Napiši vprašanje, povratno informacijo ali drugo sporočilo za skrbnika.', 'Tvoje sporočilo za skrbnika …'],
    };
    let busy = false;
    function notify(message, error = false) {
        status.textContent = message; status.dataset.kind = error ? 'error' : 'success'; status.hidden = !message;
    }
    function update() {
        const hint = hints[type.value];
        document.querySelector('#suggestionHint span').textContent = hint?.[0] || 'Namig za pisanje se prikaže, ko izbereš vrsto predloga.';
        text.placeholder = hint?.[1] || 'Opiši, kaj želiš dodati ali izboljšati …';
        const length = text.value.trim().length;
        document.getElementById('suggestionCount').textContent = `${length} znakov`;
        clear.disabled = busy || !(text.value || type.value);
    }
    function saveDraft() {
        try {
            if (type.value || text.value) {
                localStorage.setItem(root.dataset.draftKey, JSON.stringify({ type: type.value, text: text.value }));
                draftStatus.textContent = 'Osnutek shranjen v tem brskalniku.';
            } else {
                localStorage.removeItem(root.dataset.draftKey);
                draftStatus.textContent = 'Osnutek se med pisanjem shrani v tem brskalniku.';
            }
        } catch (_error) { draftStatus.textContent = 'Brskalnik ne omogoča shranjevanja osnutka. Besedilo ostane v odprtem obrazcu.'; }
    }
    try {
        const draft = JSON.parse(localStorage.getItem(root.dataset.draftKey) || 'null');
        if (draft && typeof draft.text === 'string' && typeof draft.type === 'string') {
            type.value = hints[draft.type] ? draft.type : ''; text.value = draft.text;
            draftStatus.textContent = 'Obnovljen tvoj zadnji osnutek iz tega brskalnika.';
        }
    } catch (_error) { /* The form remains usable when storage is unavailable. */ }
    [type, text].forEach(input => input.addEventListener('input', () => {
        text.setCustomValidity(''); notify(); update(); saveDraft();
    }));
    clear.addEventListener('click', () => {
        if (busy || !confirm('Počistim besedilo in vrsto predloga?')) return;
        form.reset(); text.setCustomValidity(''); notify(); update(); saveDraft(); type.focus();
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        const comment = text.value.trim();
        if (comment.length < 10) {
            text.setCustomValidity('Napiši vsaj 10 znakov predloga, brez presledkov na začetku in koncu.'); text.reportValidity(); return;
        }
        if (!form.reportValidity()) return;
        const payload = { comment_type: type.value, movieFolder: 'Splošno', comment };
        busy = true; submit.disabled = true; type.disabled = true; text.disabled = true; clear.disabled = true;
        form.setAttribute('aria-busy', 'true'); submit.querySelector('span').textContent = 'Pošiljam …';
        notify('Pošiljam predlog. Počakaj na potrditev.');
        try {
            const response = await fetch('/movies/add-comment', {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }, body: JSON.stringify(payload),
            });
            if (response.status === 401 || response.status === 403 || (response.redirected && response.url.includes('/login'))) throw new Error('Seja je potekla ali nimaš dovoljenja. Znova se prijavi; osnutek je ohranjen.');
            const result = await response.json();
            if (!response.ok || result.status !== 'success') throw new Error(result.message || 'Predloga ni bilo mogoče poslati. Osnutek je ohranjen; poskusi znova.');
            form.reset(); saveDraft();
            notify('Predlog je uspešno shranjen. Hvala! Skrbnik ga lahko pregleda med sporočili.');
            status.focus();
        } catch (error) {
            notify(error instanceof TypeError || error instanceof SyntaxError ? 'Pošiljanja ni bilo mogoče potrditi. Osnutek je ohranjen; pred ponovitvijo preveri povezavo.' : error.message, true);
            status.focus();
        } finally {
            busy = false; submit.disabled = false; type.disabled = false; text.disabled = false;
            form.setAttribute('aria-busy', 'false'); submit.querySelector('span').textContent = 'Pošlji predlog'; update();
        }
    });
    update();
})();
