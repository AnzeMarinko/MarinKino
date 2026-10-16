// Optional anonymous browser identifier; never used for authentication or quotas.
(() => {
    if (document.cookie.split(';').some(value => value.trim().startsWith('fp_id='))) return;
    if (!window.crypto?.randomUUID) return;
    document.cookie = `fp_id=${crypto.randomUUID()};Max-Age=31536000;Path=/;SameSite=Lax${location.protocol === 'https:' ? ';Secure' : ''}`;
})();
