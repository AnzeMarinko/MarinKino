(() => {
    const search = document.getElementById('blogSearch');
    if (search) {
        const posts = [...document.querySelectorAll('[data-blog-post]')];
        const status = document.getElementById('blogSearchStatus');
        const clear = document.getElementById('blogClearSearch');
        const normalize = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim();
        search.closest('.blog-search').hidden = false;
        const filter = () => {
            const terms = normalize(search.value).split(/\s+/).filter(Boolean);
            let count = 0;
            posts.forEach(post => {
                post.hidden = !terms.every(term => normalize(post.dataset.postSearch).includes(term));
                if (!post.hidden) count += 1;
            });
            clear.hidden = !search.value;
            status.hidden = !terms.length;
            status.textContent = `Najdenih zapisov: ${count}`;
            document.getElementById('blogNoResults').hidden = !terms.length || count > 0;
        };
        search.addEventListener('input', filter);
        clear.addEventListener('click', () => {
            search.value = '';
            filter();
            search.focus();
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
