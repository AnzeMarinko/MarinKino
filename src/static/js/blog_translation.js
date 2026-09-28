/* Keep subscription sessions on the original site, outside Google's proxy. */
(() => {
    const settings = document.querySelector('[data-blog-languages]');
    if (!settings) return;
    const languages = JSON.parse(settings.dataset.blogLanguages);
    const isTranslatedSite = window.location.hostname.endsWith('.translate.goog');
    const selectedLanguage = () => {
        const params = new URLSearchParams(window.location.search);
        const candidate = params.get('_x_tr_tl') || settings.dataset.blogLanguage;
        return Object.hasOwn(languages, candidate) ? candidate : 'sl';
    };
    const originalUrl = (element) => {
        const url = new URL(decodeURIComponent(element.dataset.subscriptionUrl));
        url.searchParams.set('lang', selectedLanguage());
        return url.href;
    };
    const notice = document.querySelector('[data-translation-notice]');
    if (notice) {
        const language = selectedLanguage();
        if (isTranslatedSite && language !== 'sl') {
            notice.textContent = languages[language].notice;
            notice.lang = language;
            notice.dir = languages[language].direction;
            notice.parentElement.hidden = false;
            document.querySelector('.site-translation__options')
                ?.setAttribute('aria-describedby', 'translation-notice');
        }
    }
    // A copied/rewritten link to the form must return to the original origin
    // before the visitor enters an email or receives a CSRF/Turnstile token.
    if (settings.hasAttribute('data-native-subscription') && isTranslatedSite) {
        window.location.replace(originalUrl(settings));
        return;
    }
    document.querySelectorAll('a[data-subscription-url]').forEach((link) => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            window.open(originalUrl(link), '_blank', 'noopener,noreferrer');
        });
    });
})();
