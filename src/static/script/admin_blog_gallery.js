window.createBlogGalleryEditor = ({ input, list, empty, retry, coverDescription, onSelect, onStatus, onChange }) => {
    let entries = JSON.parse(document.getElementById('blogGalleryData').textContent).map(item => ({
        key: `saved-${item.filename}`, filename: item.filename, description: item.description || '', status: 'ready',
        url: `/blog/image/${encodeURIComponent(item.filename)}`, thumbnailUrl: item.thumbnail ? `/blog/image/${encodeURIComponent(item.thumbnail)}` : null, name: item.filename
    }));
    let selected = entries[0]?.key;
    const active = () => entries.find(entry => entry.key === selected);
    function status() {
        const entry = active();
        retry.hidden = !entry?.error;
        if (entry?.error) onStatus(entry.error, true);
        else if (entry?.file && entry.status === 'loading') onStatus('Pripravljam sliko in pretvarjam format …');
        else if (entry?.file && entry.status === 'ready') onStatus(`Predogled pripravljen (${entry.format}). Izberi izrez 6:5.`);
        else onStatus('');
    }
    function button(label, action, entry, disabled = false) {
        const node = document.createElement('button'); node.type = 'button'; node.className = 'btn btn-sm btn-outline-secondary';
        node.textContent = label; node.dataset.galleryAction = action; node.dataset.galleryKey = entry.key; node.disabled = disabled;
        return node;
    }
    function render() {
        const focus = list.contains(document.activeElement) && document.activeElement.dataset.captionKey ? { key: document.activeElement.dataset.captionKey, start: document.activeElement.selectionStart, end: document.activeElement.selectionEnd } : null;
        list.replaceChildren(); empty.hidden = entries.length > 0;
        entries.forEach((entry, index) => {
            const card = document.createElement('article'); card.className = entry.key === selected ? 'is-selected' : ''; card.dataset.galleryKey = entry.key; card.dataset.pending = String(!!entry.file);
            const select = button('', 'select', entry); select.className = 'blog-gallery-select';
            if (entry.url) { const image = document.createElement('img'); image.src = entry.thumbnailUrl || entry.url; image.alt = entry.description || entry.name; select.append(image); }
            const title = document.createElement('strong'); title.textContent = `${index + 1}. ${index === 0 ? 'Naslovna slika' : 'Slika v galeriji'}`;
            const note = document.createElement('small'); note.textContent = entry.error || (entry.status === 'loading' ? 'Pripravljam predogled …' : entry.name);
            select.append(title, note); card.append(select);
            const label = document.createElement('label'); label.className = 'form-label'; label.htmlFor = `gallery-caption-${entry.key}`; label.textContent = 'Opis slike';
            const caption = document.createElement('input'); caption.id = label.htmlFor; caption.className = 'form-control'; caption.type = 'text'; caption.maxLength = 2000; caption.value = entry.description; caption.dataset.captionKey = entry.key;
            const actions = document.createElement('div'); actions.className = 'admin-actions';
            actions.append(button('↑', 'up', entry, index === 0), button('↓', 'down', entry, index === entries.length - 1), button('Naslovna', 'cover', entry, index === 0), button('Odstrani', 'remove', entry));
            actions.children[0].setAttribute('aria-label', `Premakni sliko ${index + 1} navzgor`); actions.children[1].setAttribute('aria-label', `Premakni sliko ${index + 1} navzdol`);
            card.append(label, caption, actions); list.append(card);
        });
        if (focus) {
            const node = [...list.querySelectorAll('[data-caption-key]')].find(node => node.dataset.captionKey === focus.key);
            if (node) { node.focus({ preventScroll: true }); node.setSelectionRange(focus.start, focus.end); }
        }
        status();
    }
    function select(key) { selected = key; render(); onSelect(active()); }
    function syncCover() { coverDescription.value = entries[0]?.description || ''; }
    async function process(entry) {
        entry.controller?.abort();
        entry.controller = new AbortController(); entry.status = 'loading'; entry.error = '';
        render(); if (entry.key === selected) onSelect(entry);
        try {
            if (entry.file.size > 30 * 1024 * 1024) throw new Error('Slika je prevelika. Največja velikost je 30 MB.');
            const data = new FormData(); data.append('image_file', entry.file);
            const response = await fetch('/admin/blog/image-preview', { method: 'POST', body: data, signal: entry.controller.signal, headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content } });
            if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/')) {
                const data = await response.json().catch(() => ({})); throw new Error(data.message || 'Slike ni mogoče pripraviti. Poskusi ponovno.');
            }
            const blob = await response.blob();
            if (!entries.includes(entry)) return;
            if (entry.url) URL.revokeObjectURL(entry.url);
            entry.url = URL.createObjectURL(blob); entry.format = blob.type === 'image/png' ? 'PNG' : 'JPEG';
            const decoded = new Image(); decoded.src = entry.url; await decoded.decode();
            if (!entries.includes(entry)) return;
            const width = Math.min(.8, decoded.naturalHeight * 1.2 / decoded.naturalWidth);
            const height = width * decoded.naturalWidth / 1.2 / decoded.naturalHeight;
            entry.crop ||= { x: (1 - width) / 2, y: (1 - height) / 2, w: width, h: height };
            entry.status = 'ready'; render(); if (entry.key === selected) onSelect(entry);
        } catch (error) {
            if (error.name === 'AbortError' || !entries.includes(entry)) return;
            entry.status = 'error'; entry.error = error.message || 'Nalaganje ni uspelo. Besedilo je ohranjeno.';
            render(); if (entry.key === selected) onSelect(entry);
        }
    }
    input.addEventListener('change', () => {
        const files = [...input.files]; input.value = '';
        if (entries.length + files.length > 20) { onStatus('Galerija lahko vsebuje največ 20 slik.', true); return; }
        const added = files.map(file => ({ key: crypto.randomUUID(), file, name: file.name, description: '', status: 'loading', crop: null, url: null }));
        entries.push(...added); if (added[0]) selected = added[0].key; syncCover(); render(); onChange();
        // Decode sequentially to keep large phone photos within one conversion.
        (async () => { for (const entry of added) if (entries.includes(entry)) await process(entry); })();
    });
    retry.addEventListener('click', () => { const entry = active(); if (entry?.file) process(entry); });
    list.addEventListener('input', event => {
        const entry = entries.find(entry => entry.key === event.target.dataset.captionKey);
        if (entry) { entry.description = event.target.value; if (entry === entries[0]) syncCover(); onChange(); }
    });
    coverDescription.addEventListener('input', () => { if (entries[0]) { entries[0].description = coverDescription.value; render(); } });
    list.addEventListener('click', event => {
        const button = event.target.closest('[data-gallery-action]'); if (!button) return;
        const index = entries.findIndex(entry => entry.key === button.dataset.galleryKey), entry = entries[index]; if (!entry) return;
        const action = button.dataset.galleryAction;
        if (action === 'select') { select(entry.key); return; }
        if (action === 'remove') { entry.controller?.abort(); if (entry.file && entry.url) URL.revokeObjectURL(entry.url); entries.splice(index, 1); if (selected === entry.key) selected = entries[Math.min(index, entries.length - 1)]?.key; }
        else { const target = action === 'cover' ? 0 : action === 'up' ? index - 1 : index + 1; entries.splice(index, 1); entries.splice(target, 0, entry); }
        syncCover(); render(); onSelect(active()); onChange();
    });
    render();
    return {
        active,
        setCrop(crop) { const entry = active(); if (entry?.file && entry.status === 'ready') entry.crop = crop; },
        validate() {
            const pending = entries.find(entry => entry.file && entry.status !== 'ready');
            if (pending) return `Slika »${pending.name}« še ni pripravljena. Počakaj, poskusi ponovno ali jo odstrani.`;
            return entries.some(entry => entry.file && !entry.crop) ? 'Vsaka nova slika potrebuje izrez 6:5.' : '';
        },
        serialize(data) {
            data.delete('image_file');
            data.set('gallery_manifest', JSON.stringify(entries.map(entry => entry.file ? { upload_id: entry.key, crop: entry.crop, description: entry.description } : { filename: entry.filename, description: entry.description })));
            entries.filter(entry => entry.file).forEach(entry => data.append(`gallery_file_${entry.key}`, entry.file));
        },
        acceptSaved(data, changed) {
            for (const entry of entries) {
                const filename = data.image_uploads?.[entry.key];
                if (filename) { if (entry.url) URL.revokeObjectURL(entry.url); entry.file = null; entry.filename = filename; entry.url = `/blog/image/${encodeURIComponent(filename)}`; const saved = data.images.find(item => item.filename === filename); entry.thumbnailUrl = saved?.thumbnail ? `/blog/image/${encodeURIComponent(saved.thumbnail)}` : null; entry.status = 'ready'; }
            }
            if (!changed) {
                for (const entry of entries) if (entry.file && entry.url) URL.revokeObjectURL(entry.url);
                entries = (data.images || []).map(item => ({ key: `saved-${item.filename}`, filename: item.filename, description: item.description || '', name: item.filename, url: `/blog/image/${encodeURIComponent(item.filename)}`, thumbnailUrl: item.thumbnail ? `/blog/image/${encodeURIComponent(item.thumbnail)}` : null, status: 'ready' }));
                selected = entries[0]?.key; syncCover();
            }
            render(); onSelect(active());
        }
    };
};
