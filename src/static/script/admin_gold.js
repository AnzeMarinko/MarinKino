(() => {
    const chart = document.getElementById('gold-price-chart');
    if (!chart) return;
    const message = document.getElementById('goldMessage');
    const retry = document.getElementById('retryGold');
    let loading = false;
    let library;
    function loadLibrary() {
        if (window.BullionVaultChart) return Promise.resolve();
        if (!library) library = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://www.bullionvault.com/chart/bullionvaultchart.js';
            script.onload = resolve;
            script.onerror = () => { script.remove(); reject(new Error('unavailable')); };
            document.head.appendChild(script);
        }).catch(error => { library = null; throw error; });
        return library;
    }
    async function render() {
        if (loading) return;
        loading = true; retry.disabled = true; chart.setAttribute('aria-busy', 'true');
        message.hidden = false; message.dataset.kind = 'success'; message.textContent = 'Nalagam graf cene zlata …';
        try {
            await loadLibrary();
            if (!window.BullionVaultChart) throw new Error('unavailable');
            chart.replaceChildren();
            new window.BullionVaultChart({ bullion: 'gold', currency: 'EUR', timeframe: '1y', chartType: 'line', miniChartModeAxis: 'kg', referrerID: null, containerDefinedSize: true, miniChartMode: false, displayLatestPriceLine: true, switchBullion: false, switchCurrency: false, switchTimeframe: true, switchChartType: false, exportButton: false }, 'gold-price-chart');
            message.hidden = true;
        } catch (_error) {
            message.dataset.kind = 'error'; message.textContent = 'Grafa trenutno ni mogoče naložiti. Poskusi z gumbom Osveži graf ali odpri graf pri BullionVault.';
        } finally { loading = false; retry.disabled = false; chart.setAttribute('aria-busy', 'false'); }
    }
    retry.addEventListener('click', render);
    render();
})();
