/* Keep the blog navigation and notice together below translation toolbars. */
(() => {
    const header = document.getElementById('blog-site-header');
    const spacer = document.getElementById('blog-header-spacer');
    if (!header || !spacer) return;

    const toolbarSelector = [
        '#gt-nvframe',
        'iframe.goog-te-banner-frame',
        'iframe.VIpgJd-ZVi9od-ORHb-OEVmcd',
        '#blog-view-as-notice',
    ].join(',');
    const observedToolbars = new WeakSet();
    let scheduled = false;
    const scheduleLayout = () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(updateLayout);
    };
    const resizeObserver = new ResizeObserver(scheduleLayout);

    function updateLayout() {
        scheduled = false;
        let toolbarBottom = 0;
        document.querySelectorAll(toolbarSelector).forEach((toolbar) => {
            if (!observedToolbars.has(toolbar)) {
                resizeObserver.observe(toolbar);
                observedToolbars.add(toolbar);
            }
            const rect = toolbar.getBoundingClientRect();
            const style = getComputedStyle(toolbar);
            // Google's collapsed toolbar is a small floating button; its
            // language picker can cover the viewport. Neither reserves a row.
            if (toolbar.id !== 'blog-view-as-notice' && (
                rect.width < window.innerWidth * 0.8 || rect.top > 1 ||
                rect.height > window.innerHeight * 0.4
            )) return;
            if (rect.width && rect.height && style.visibility !== 'hidden' &&
                style.display !== 'none') {
                toolbarBottom = Math.max(toolbarBottom, rect.bottom);
            }
        });
        toolbarBottom = Math.max(0, Math.ceil(toolbarBottom));
        const headerBottom = `${Math.ceil(toolbarBottom + header.getBoundingClientRect().height)}px`;
        if (document.documentElement.style.getPropertyValue('--site-header-height') !== headerBottom) {
            document.documentElement.style.setProperty('--site-header-height', headerBottom);
        }
        const offset = `${toolbarBottom}px`;
        if (header.style.getPropertyValue('--blog-toolbar-offset') !== offset) {
            header.style.setProperty('--blog-toolbar-offset', offset);
        }

        // Google may already reserve toolbar space with body margin/top.
        // Subtract that document offset instead of adding the toolbar twice.
        const flowTop = spacer.getBoundingClientRect().top + window.scrollY;
        const height = Math.max(0, Math.ceil(
            toolbarBottom + header.getBoundingClientRect().height - flowTop
        ));
        const space = `${height}px`;
        if (spacer.style.height !== space) spacer.style.height = space;
    }

    resizeObserver.observe(header);
    resizeObserver.observe(document.body);
    const mutations = new MutationObserver(scheduleLayout);
    mutations.observe(document.body, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['style', 'class', 'hidden'],
    });
    mutations.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['style', 'class'],
    });
    window.addEventListener('resize', scheduleLayout, {passive: true});
    window.addEventListener('scroll', scheduleLayout, {passive: true});
    window.visualViewport?.addEventListener('resize', scheduleLayout);
    updateLayout();
})();
