(() => {
    const root = document.getElementById('memesPage');
    if (!root) return;
    const initial = JSON.parse(root.dataset.meme);
    let history = initial.empty ? [] : [initial];
    let position = history.length - 1;
    let remaining = initial.remaining;
    let busy = false;
    let limited = false;
    const media = document.getElementById('memeMedia');
    const stage = document.getElementById('mediaContainer');
    const message = document.getElementById('memeMessage');
    const previous = document.getElementById('previousMeme');
    const next = document.getElementById('nextButton');
    const remove = document.getElementById('deleteMemeButton');
    const dialog = document.getElementById('deleteMemeDialog');
    const fullscreen = document.getElementById('memeFullscreen');
    const current = () => history[position];
    function notify(text = '', error = false) {
        message.textContent = text;
        message.hidden = !text;
        message.dataset.kind = error ? 'error' : 'info';
    }
    function controls() {
        previous.disabled = busy || position <= 0;
        next.disabled = busy || ((limited || remaining === 0) && position >= history.length - 1);
        next.querySelector('span').textContent = busy ? 'Nalagam …' : current() ? 'Naslednja šala' : 'Preveri zbirko';
        stage.setAttribute('aria-busy', String(busy));
        if (remove) { remove.disabled = busy; remove.hidden = !current(); }
        document.getElementById('memeProgress').textContent = remaining == null
            ? `V zbirki: ${current()?.total ?? 0}` : `Danes lahko odpreš še ${remaining} šal`;
    }
    function watch(element) {
        element.addEventListener('error', () => notify('Vsebine ni mogoče prikazati. Poskusi naslednjo šalo ali osveži stran.', true), { once: true });
    }
    function render() {
        media.querySelector('video')?.pause();
        media.replaceChildren();
        const data = current();
        if (!data) {
            const empty = document.createElement('div'); empty.className = 'meme-empty';
            const title = document.createElement('h2'); title.textContent = 'Nov nasmeh še pripravljamo.';
            const text = document.createElement('p'); text.textContent = 'Zbirka je trenutno prazna. Vrni se kasneje ali preveri znova.';
            empty.append(title, text); media.append(empty);
        } else {
            const element = document.createElement(data.is_video ? 'video' : 'img');
            if (data.is_video) { element.controls = true; element.playsInline = true; element.preload = 'metadata'; }
            else { element.alt = 'Slika iz zbirke šal in navdiha'; element.decoding = 'async'; }
            watch(element); element.src = data.media_url; media.append(element);
        }
        document.getElementById('memeKind').textContent = !data ? 'Zbirka šal' : data.is_video ? 'Video šala' : 'Šala v sliki';
        controls();
    }
    async function fetchNext() {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
            const query = new URLSearchParams({ format: 'json' });
            if (current()) query.set('previous', current().meme_file_name);
            const response = await fetch(`/memes?${query}`, { signal: controller.signal, cache: 'no-store' });
            const data = await response.json();
            if (response.status === 429) { limited = true; remaining = 0; throw new Error(data.message || 'Dnevna omejitev je dosežena. Vrni se jutri.'); }
            if (!response.ok || (!data.empty && (typeof data.media_url !== 'string' || typeof data.meme_file_name !== 'string'))) throw new Error('Nove šale ni mogoče naložiti. Poskusi znova.');
            remaining = data.remaining;
            if (data.empty) { history = []; position = -1; }
            else { history.push(data); position = history.length - 1; }
            render();
            if (remaining === 0) notify('Za danes si odprl vse dovoljene šale. Prejšnje lahko še prelistaš; nove te čakajo jutri.');
        } finally { clearTimeout(timeout); }
    }
    async function forward() {
        if (busy) return;
        notify();
        if (position < history.length - 1) { position++; render(); return; }
        if (limited || remaining === 0) return;
        busy = true; controls();
        try { await fetchNext(); }
        catch (error) { notify(error.name === 'AbortError' ? 'Nalaganje traja predolgo. Poskusi znova.' : error instanceof TypeError || error instanceof SyntaxError ? 'Nove šale ni mogoče naložiti. Poskusi znova.' : error.message, true); }
        finally { busy = false; controls(); }
    }
    previous.addEventListener('click', () => { if (!busy && position > 0) { position--; notify(); render(); } });
    next.addEventListener('click', forward);
    async function toggleFullscreen() {
        try {
            if (document.fullscreenElement || document.webkitFullscreenElement) {
                await (document.exitFullscreen?.() ?? document.webkitExitFullscreen?.());
            } else if (root.requestFullscreen) await root.requestFullscreen();
            else if (root.webkitRequestFullscreen) root.webkitRequestFullscreen();
            else notify('Brskalnik ne podpira celozaslonskega prikaza.', true);
        } catch (_error) { notify('Celozaslonskega prikaza ni mogoče odpreti.', true); }
    }
    fullscreen.addEventListener('click', toggleFullscreen);
    function fullscreenState() {
        const active = !!(document.fullscreenElement || document.webkitFullscreenElement);
        fullscreen.setAttribute('aria-pressed', String(active));
        fullscreen.querySelector('span').textContent = active ? 'Zapri celozaslonsko' : 'Celozaslonsko';
    }
    document.addEventListener('fullscreenchange', fullscreenState);
    document.addEventListener('webkitfullscreenchange', fullscreenState);
    document.addEventListener('keydown', event => {
        if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || document.querySelector('dialog[open]') || event.target.closest('input, textarea, select, video, [contenteditable="true"]')) return;
        if (event.key === 'ArrowRight') { event.preventDefault(); next.click(); }
        if (event.key === 'ArrowLeft') { event.preventDefault(); previous.click(); }
    });
    if (dialog && remove) {
        let deleting;
        remove.addEventListener('click', () => { if (!busy && current()) { deleting = current(); dialog.showModal(); } });
        document.getElementById('cancelDeleteMeme').addEventListener('click', () => dialog.close());
        document.getElementById('confirmDeleteMeme').addEventListener('click', async () => {
            if (busy || !deleting) return;
            dialog.close(); busy = true; controls(); notify();
            try {
                const response = await fetch(deleting.delete_url, { method: 'DELETE', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content } });
                if (!response.ok) throw new Error('Brisanje ni uspelo. Šala ostaja v zbirki.');
                history = history.filter(item => item.meme_file_name !== deleting.meme_file_name);
                position = Math.min(position, history.length - 1);
                render();
                if (!history.length) await fetchNext();
                notify('Šala odstranjena iz zbirke.');
            } catch (_error) { notify('Brisanja ali nalaganja naslednje šale ni bilo mogoče potrditi. Preveri zbirko in poskusi znova.', true); }
            finally { busy = false; controls(); }
        });
    }
    media.querySelectorAll('img, video').forEach(watch);
    controls(); fullscreenState();
    window.pojdiNaNaslednjega = forward;
    window.preklopiFullscreen = toggleFullscreen;
    window.izbrisiMeme = () => remove?.click();
})();
