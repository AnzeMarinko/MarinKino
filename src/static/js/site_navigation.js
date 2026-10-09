(() => {
    const menu = document.getElementById('mainNavbar');
    const toggle = document.querySelector('.site-menu-toggle');
    if (!menu || !toggle) return;
    const greeting = document.getElementById('greeting');
    if (greeting) {
        const hour = new Date().getHours();
        greeting.textContent = hour < 4 ? 'lahko noč' : hour < 10 ? 'dobro jutro' : hour < 18 ? 'dober dan' : 'dober večer';
    }
    menu.addEventListener('shown.bs.collapse', () => toggle.setAttribute('aria-label', 'Zapri glavni meni'));
    menu.addEventListener('hidden.bs.collapse', () => toggle.setAttribute('aria-label', 'Odpri glavni meni'));
    function closeMenu() {
        if (!menu.classList.contains('show') || !window.bootstrap) return;
        bootstrap.Collapse.getOrCreateInstance(menu, { toggle: false }).hide();
    }
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || document.querySelector('dialog[open]') || document.querySelector('.site-account .dropdown-menu.show') || document.querySelector('.site-translation .dropdown-menu.show')) return;
        if (menu.classList.contains('show')) { closeMenu(); toggle.focus(); }
    });
    document.addEventListener('click', event => {
        if (!event.target.closest('.site-header') && !event.target.closest('#blog-view-as-notice')) closeMenu();
    });
    window.matchMedia('(min-width: 1400px)').addEventListener('change', event => { if (event.matches) closeMenu(); });
})();
