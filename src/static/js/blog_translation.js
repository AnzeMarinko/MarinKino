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
    const displayLanguage = isTranslatedSite ? selectedLanguage() : 'sl';
    const flag = document.querySelector('[data-language-flag]');
    const name = document.querySelector('[data-language-name]');
    const languageCode = document.querySelector('[data-language-code]');
    if (flag && name && languageCode) {
        flag.textContent = languages[displayLanguage].flag;
        name.textContent = languages[displayLanguage].name;
        name.lang = displayLanguage;
        name.dir = languages[displayLanguage].direction;
        languageCode.textContent = displayLanguage.split('-')[0].toUpperCase();
        document.querySelector('#blog-language-toggle')?.setAttribute(
            'aria-label', `Jezik / Language: ${languages[displayLanguage].name}`
        );
    }
    document.querySelectorAll('.site-translation__options [data-language]').forEach((link) => {
        if (link.dataset.language === displayLanguage) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'true');
        }
    });
    const notice = document.querySelector('[data-translation-notice]');
    if (notice) {
        const language = selectedLanguage();
        if (isTranslatedSite && language !== 'sl') {
            notice.textContent = languages[language].notice;
            notice.lang = language;
            notice.dir = languages[language].direction;
            notice.parentElement.hidden = false;
            document.querySelector('#blog-language-toggle')
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
    document.querySelectorAll('a[data-original-url]').forEach((link) => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            window.open(decodeURIComponent(link.dataset.originalUrl), '_blank', 'noopener,noreferrer');
        });
    });
})();
