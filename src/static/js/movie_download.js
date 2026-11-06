(() => {
    const form = document.getElementById('movie-download-form');
    if (!form) return;
    const button = form.querySelector('button');
    const status = document.getElementById('movie-download-status');
    const link = document.getElementById('movie-download-link');
    let statusUrl = form.dataset.statusUrl || null;
    async function show(result) {
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
            statusUrl = null;
            return;
        }
        statusUrl = result.status_url || statusUrl;
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
        button.disabled = true;
        status.textContent = 'Dodajam film v pripravo …';
        try {
            const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json'}});
            if (!response.ok) throw new Error();
            await show(await response.json());
        } catch (_) {
            status.textContent = 'Priprave ni mogoče začeti. Poskusi pozneje.';
            button.disabled = false;
        }
    });
    if (statusUrl) poll();
})();
