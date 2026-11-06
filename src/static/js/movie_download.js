(() => {
    const form = document.getElementById('movie-download-form');
    if (!form) return;
    const button = form.querySelector('button');
    const status = document.getElementById('movie-download-status');
    const link = document.getElementById('movie-download-link');
    let statusUrl = form.dataset.statusUrl || null;
    async function show(result) {
        if (result.page_url) history.replaceState(null, '', result.page_url);
        form.setAttribute('aria-busy', String(['pending', 'running'].includes(result.state)));
        if (result.state === 'done') {
            status.textContent = 'Film je pripravljen.';
            link.href = result.download_url;
            link.hidden = false;
            form.hidden = true;
            return;
        }
        if (['failed', 'uncertain'].includes(result.state)) {
            status.textContent = result.error || 'Priprava ni uspela. Poskusi znova.';
            button.disabled = false;
            button.textContent = 'Poskusi pripravo znova';
            statusUrl = null;
            return;
        }
        statusUrl = result.status_url || statusUrl;
        button.textContent = 'Priprava poteka …';
        status.textContent = result.state === 'running' ? 'Pripravljam film …' : 'Film čaka na pripravo …';
        setTimeout(poll, 2500);
    }
    async function poll() {
        if (!statusUrl) return;
        try {
            const response = await fetch(statusUrl, {headers: {Accept: 'application/json'}});
            if ([401, 403, 404].includes(response.status) || response.redirected) {
                statusUrl = null;
                status.textContent = 'Prenos ni več na voljo. Ponovno odpri film in preveri prijavo.';
                return;
            }
            if (!response.ok) throw new Error();
            await show(await response.json());
        } catch (_) {
            status.textContent = 'Stanja ni mogoče preveriti. Preverjanje se bo ponovilo.';
            setTimeout(poll, 10000);
        }
    }
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (button.disabled) return;
        form.setAttribute('aria-busy', 'true');
        button.disabled = true;
        status.textContent = 'Dodajam film v pripravo …';
        try {
            const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json'}});
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || (response.status === 429 ? 'Pripravo lahko začneš največ trikrat na uro. Poskusi pozneje.' : 'Priprave ni mogoče začeti. Poskusi pozneje.'));
            await show(result);
        } catch (error) {
            form.setAttribute('aria-busy', 'false');
            status.textContent = error instanceof SyntaxError || error instanceof TypeError ? 'Priprave ni mogoče začeti. Preveri povezavo in prijavo.' : error.message;
            button.disabled = false;
        }
    });
    if (statusUrl) poll();
})();
