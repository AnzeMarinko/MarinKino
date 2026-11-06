(() => {
    const log = document.getElementById('adminLog');
    const search = document.getElementById('logSearch');
    const clear = document.getElementById('logClear');
    const lines = log.textContent.trimEnd().split('\n');
    document.getElementById('logControls').hidden = false;
    function filter() {
        const query = search.value.trim().toLocaleLowerCase('sl');
        const matching = lines.filter(line => line.toLocaleLowerCase('sl').includes(query));
        log.textContent = matching.join('\n');
        log.hidden = matching.length === 0;
        document.getElementById('logEmpty').hidden = matching.length !== 0;
        document.getElementById('logCount').textContent = `${matching.length} od ${lines.length} vrstic`;
        clear.hidden = !query;
    }
    search.addEventListener('input', filter);
    clear.addEventListener('click', () => { search.value = ''; filter(); search.focus(); });
    document.getElementById('logLatest').addEventListener('click', () => {
        search.value = ''; filter(); log.scrollTop = log.scrollHeight; log.focus();
    });
    filter();
})();
