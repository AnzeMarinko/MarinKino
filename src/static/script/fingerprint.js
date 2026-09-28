(() => {
    function getCookie(name) {
        const prefix = `${name}=`;
        const cookie = document.cookie.split(';')
            .map(value => value.trim())
            .find(value => value.startsWith(prefix));
        return cookie ? cookie.slice(prefix.length) : null;
    }

    async function initializeFingerprint() {
        try {
            if (typeof FingerprintJS === 'undefined') {
                console.warn('FingerprintJS could not be loaded; fp_id was not updated.');
                return;
            }

            const agent = await FingerprintJS.load();
            const { visitorId } = await agent.get();
            if (!visitorId || getCookie('fp_id') === visitorId) {
                return;
            }

            const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000);
            document.cookie = `fp_id=${visitorId};expires=${expires.toUTCString()};path=/;SameSite=Lax`;

            // Cookies may be disabled. Do not enter a reload loop if the write failed.
            if (getCookie('fp_id') !== visitorId) {
                console.warn('The fp_id cookie could not be stored; skipping reload.');
                return;
            }

            // Flask receives the new cookie on the next request, not the current one.
            window.location.reload();
        } catch (error) {
            console.warn('FingerprintJS initialization failed; fp_id was not updated.', error);
        }
    }

    // Both scripts use defer, so the library and DOM are ready at this point.
    initializeFingerprint();
})();
