/* Public translation links; subscription sessions stay on the original site. */
(() => {
    const settings = document.querySelector('[data-blog-languages]');
    if (!settings) return;
    const languages = JSON.parse(settings.dataset.blogLanguages);
    const isTranslatedSite = window.location.hostname.endsWith('.translate.goog');
    const selectedLanguage = () => {
        const params = new URLSearchParams(window.location.search);
        const candidate = (isTranslatedSite && params.get('_x_tr_tl')) ||
            settings.dataset.blogLanguage;
        return Object.hasOwn(languages, candidate) ? candidate : 'sl';
    };
    const originalUrl = (element) => {
        const url = new URL(decodeURIComponent(element.dataset.subscriptionUrl));
        url.searchParams.set('lang', selectedLanguage());
        return url.href;
    };
    const displayLanguage = isTranslatedSite ? selectedLanguage() : 'sl';
    const copyButton = document.querySelector('[data-copy-url]');
    if (copyButton) {
        // Shared native URLs open the requested free translation. On Google's
        // proxy the source is rendered normally, so this cannot redirect back.
        if (!isTranslatedSite && selectedLanguage() !== 'sl') {
            const translation = settings.querySelector(
                `a[data-language="${selectedLanguage()}"]`
            );
            if (translation) {
                window.location.replace(translation.href);
                return;
            }
        }
        const copy = languages[displayLanguage];
        const status = document.querySelector('[data-copy-status]');
        const icon = copyButton.querySelector('[data-copy-icon]');
        let resetCopy;
        copyButton.title = copy.copy_link;
        copyButton.lang = displayLanguage;
        status.lang = displayLanguage;
        status.dir = languages[displayLanguage].direction;
        copyButton.setAttribute('aria-label', copy.copy_link);
        copyButton.addEventListener('click', async () => {
            // Keep the configured public origin and path, never the proxy URL
            // or request parameters that might contain private information.
            const url = new URL(decodeURIComponent(copyButton.dataset.copyUrl));
            url.search = '';
            url.hash = '';
            const language = selectedLanguage();
            if (language !== 'sl') url.searchParams.set('lang', language);
            clearTimeout(resetCopy);
            status.textContent = '';
            copyButton.title = copy.copy_link;
            icon.className = 'bi bi-link-45deg';
            copyButton.disabled = true;
            try {
                await navigator.clipboard.writeText(url.href);
                status.textContent = copy.link_copied;
                copyButton.title = copy.link_copied;
                icon.className = 'bi bi-check-lg';
                resetCopy = setTimeout(() => {
                    status.textContent = '';
                    copyButton.title = copy.copy_link;
                    icon.className = 'bi bi-link-45deg';
                }, 2500);
            } catch {
                window.prompt(copy.copy_link_prompt, url.href);
            } finally {
                copyButton.disabled = false;
            }
        });
    }
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
