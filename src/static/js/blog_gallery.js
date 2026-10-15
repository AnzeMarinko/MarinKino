(() => {
    document.querySelectorAll('[data-blog-gallery]').forEach(root => {
        const items = [...root.querySelectorAll('[data-gallery-index]')];
        if (items.length < 2) return;
        const image = root.querySelector('[data-gallery-main]');
        const caption = root.querySelector('[data-gallery-caption]');
        const play = root.querySelector('[data-gallery-play]');
        const counter = root.querySelector('[data-gallery-counter]');
        const announcement = root.querySelector('[data-gallery-announcement]');
        const motion = matchMedia('(prefers-reduced-motion: reduce)');
        let index = 0, timer = null, paused = motion.matches, visible = true;
        function stop() { clearInterval(timer); timer = null; }
        function schedule() {
            stop();
            const action = paused ? 'Predvajaj menjavanje' : 'Zaustavi menjavanje';
            play.setAttribute('aria-label', action);
            play.title = action;
            play.setAttribute('aria-pressed', String(!paused));
            play.querySelector('i').className = paused
                ? 'bi bi-play-fill'
                : 'bi bi-pause-fill';
            if (!paused && visible && !document.hidden) {
                timer = setInterval(
                    () => show((index + 1) % items.length),
                    5000
                );
            }
        }
        function show(next, manual = false) {
            index = (next + items.length) % items.length;
            image.src = items[index].href;
            image.alt = items[index].dataset.alt;
            caption.textContent = items[index].dataset.description;
            caption.hidden = !caption.textContent;
            counter.textContent = `${index + 1} / ${items.length}`;
            root.dataset.currentIndex = String(index);
            items.forEach((item, itemIndex) => { if (itemIndex === index) item.setAttribute('aria-current', 'true'); else item.removeAttribute('aria-current'); });
            if (manual) { paused = true; announcement.textContent = `Slika ${index + 1} od ${items.length}: ${image.alt}`; schedule(); }
        }
        items.forEach((item, itemIndex) => item.addEventListener('click', event => {
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault(); show(itemIndex, true);
        }));
        root.querySelector('[data-gallery-prev]').addEventListener('click', () => show(index - 1, true));
        root.querySelector('[data-gallery-next]').addEventListener('click', () => show(index + 1, true));
        play.addEventListener('click', () => { paused = !paused; schedule(); });
        root.addEventListener('focusin', event => { if (event.target !== play) { paused = true; schedule(); } });
        document.addEventListener('visibilitychange', schedule);
        motion.addEventListener('change', event => { if (event.matches) { paused = true; schedule(); } });
        if (window.IntersectionObserver) new IntersectionObserver(entries => { visible = entries[0].isIntersecting; schedule(); }).observe(root);
        root.querySelector('[data-gallery-controls]').hidden = false;
        root.dataset.currentIndex = '0';
        schedule();
    });
})();
