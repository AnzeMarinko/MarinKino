(() => {
    const search = document.getElementById('blogSearch');
    if (search) {
        const form = document.getElementById('blogSearchForm');
        const results = document.getElementById('blog-results');
        const feedback = document.getElementById('blogSearchFeedback');
        const clear = document.getElementById('blogClearSearch');
        let timer;
        let pending;
        const searchUrl = () => {
            const url = new URL(form.action, location.href);
            url.search = new URLSearchParams(new FormData(form)).toString();
            return url;
        };
        async function load(url, historyMode = 'replace', scroll = false) {
            pending?.abort();
            const controller = new AbortController();
            pending = controller;
            results.setAttribute('aria-busy', 'true');
            feedback.textContent = 'Nalagam objave …';
            const requestUrl = new URL(url);
            requestUrl.searchParams.set('partial', '1');
            try {
                const response = await fetch(requestUrl, {signal: controller.signal});
                if (!response.ok) throw new Error();
                const html = await response.text();
                if (controller.signal.aborted) return;
                results.innerHTML = html;
                if (historyMode !== 'none') history[historyMode + 'State']({}, '', url);
                search.value = url.searchParams.get('q') || '';
                clear.hidden = !search.value;
                feedback.textContent = document.getElementById('blogSearchStatus').textContent;
                if (scroll) document.getElementById('blog-posts').scrollIntoView({block: 'start'});
            } catch (error) {
                if (error.name !== 'AbortError') feedback.textContent = 'Nalaganje ni uspelo. Za ponovni poskus pritisni gumb za iskanje.';
            } finally {
                if (pending === controller) results.setAttribute('aria-busy', 'false');
            }
        }
        search.addEventListener('input', () => {
            clearTimeout(timer);
            pending?.abort();
            clear.hidden = !search.value;
            timer = setTimeout(() => load(searchUrl()), 200);
        });
        form.addEventListener('submit', event => {
            event.preventDefault();
            clearTimeout(timer);
            load(searchUrl(), 'push');
        });
        clear.addEventListener('click', () => {
            clearTimeout(timer);
            search.value = '';
            clear.hidden = true;
            load(searchUrl());
            search.focus();
        });
        results.addEventListener('click', event => {
            const link = event.target.closest('.blog-pagination a');
            if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            clearTimeout(timer);
            load(new URL(link.href), 'push', true);
        });
        window.addEventListener('popstate', () => {
            clearTimeout(timer);
            load(new URL(location.href), 'none');
        });
    }
    const toc = document.getElementById('blogToc');
    if (!toc) return;
    const headings = [...document.querySelectorAll('.blog-content h2, .blog-content h3')];
    if (headings.length < 3) return;
    const links = document.getElementById('blogTocLinks');
    headings.forEach((heading, index) => {
        if (!heading.id) {
            let id = `blog-section-${index + 1}`;
            while (document.getElementById(id)) id += '-heading';
            heading.id = id;
        }
        const link = document.createElement('a');
        link.href = `#${encodeURIComponent(heading.id)}`;
        link.textContent = heading.textContent;
        if (heading.tagName === 'H3') link.className = 'blog-toc-subheading';
        links.appendChild(link);
    });
    toc.hidden = false;
})();
