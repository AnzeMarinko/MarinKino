(() => {
  'use strict';
  let tracks = JSON.parse(document.getElementById('music-data').textContent);
  const drafts = new Map(), statuses = new Map();
  const rows = document.getElementById('track-rows'), search = document.getElementById('search');
  const status = document.getElementById('operation-status'), player = document.getElementById('preview-player');
  let busy = false, hls = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const mediaPath = value => value.split('/').map(encodeURIComponent).join('/');
  async function api(url, data, method = 'POST') {
    const response = await fetch(url, {method, headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
    const payload = await response.json().catch(() => ({message:`Zahteva ni uspela (${response.status}). Preveri terminal urejevalnika.`}));
    if (!response.ok || payload.status === 'error') throw Error(payload.message || 'Zahteva ni uspela.');
    return payload;
  }
  function render() {
    const term = search.value.trim().toLocaleLowerCase('sl');
    const visible = tracks.filter(track => Object.values({...track,...drafts.get(track.filename)}).join(' ').toLocaleLowerCase('sl').includes(term));
    rows.innerHTML = visible.length ? visible.map(track => {
      const data = {...track,...drafts.get(track.filename)}, id = esc(track.filename);
      return `<tr data-track="${id}" data-dirty="${drafts.has(track.filename)}"><td><button type="button" data-action="play" class="secondary">Poslušaj</button><small>${id}</small><small>${esc(track.duration)}</small></td>${[['title','Naslov'],['artist','Izvajalec'],['album','Album']].map(([field,label])=>`<td data-label="${label}"><input type="text" data-field="${field}" aria-label="${label}: ${esc(track.title)}" value="${esc(data[field])}" ${busy?'disabled':''}></td>`).join('')}<td><div class="actions"><button type="button" data-action="save" ${busy||!drafts.has(track.filename)?'disabled':''}>Shrani</button><button type="button" data-action="delete" class="danger" ${busy?'disabled':''}>Izbriši</button></div><p class="track-status" role="status">${esc(statuses.get(track.filename)||'')}</p></td></tr>`;
    }).join('') : '<tr><td colspan="5" class="empty">Ni skladb. Spremeni iskanje ali dodaj MP3 in osveži seznam.</td></tr>';
    document.getElementById('record-count').textContent = `${visible.length} od ${tracks.length} skladb · ${drafts.size} neshranjenih`;
    document.getElementById('save-all').disabled = busy || !drafts.size;
  }
  function setBusy(value) {
    busy = value;
    document.querySelectorAll('#prepare,#refresh,#download-form button').forEach(button => button.disabled = value);
    render();
  }
  async function operation(message, work) {
    if (busy) return;
    setBusy(true); status.className = 'status'; status.textContent = message;
    try { await work(); } catch (error) { status.className = 'status error'; status.textContent = error.message; }
    finally { setBusy(false); }
  }
  async function save(filename) {
    const snapshot = {...drafts.get(filename)};
    try {
      const result = await api('/api/music/update', {filename,...snapshot});
      const track = tracks.find(item=>item.filename===filename);
      Object.assign(track, result.metadata || snapshot); drafts.delete(filename); statuses.set(filename,'Shranjeno.');
    } catch (error) { statuses.set(filename,error.message); throw error; }
  }
  async function refresh() {
    const result = await api('/api/music/list', undefined, 'GET'); tracks = result.music;
  }
  rows.addEventListener('input', event => {
    if (!event.target.dataset.field) return;
    const row = event.target.closest('[data-track]'), id = row.dataset.track;
    const values = Object.fromEntries([...row.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value]));
    drafts.set(id, values); row.dataset.dirty = 'true'; row.querySelector('[data-action=save]').disabled = false;
    document.getElementById('save-all').disabled = false;
    document.getElementById('record-count').textContent = `${tracks.length} skladb · ${drafts.size} neshranjenih`;
  });
  rows.addEventListener('click', event => {
    const button = event.target.closest('[data-action]'); if (!button) return;
    const filename = button.closest('[data-track]').dataset.track, track = tracks.find(item=>item.filename===filename);
    if (button.dataset.action === 'save') operation('Shranjujem …', async()=>{await save(filename); status.textContent='Spremembe shranjene.';});
    if (button.dataset.action === 'delete' && confirm(`Izbrišem skladbo »${track.title}«, izvorni MP3 in pripadajočo HLS mapo? Tega ni mogoče razveljaviti.`)) {
      operation('Brišem …', async()=>{await api('/api/music/delete',{filename},'DELETE'); tracks=tracks.filter(item=>item.filename!==filename); drafts.delete(filename); player.pause(); status.textContent='Skladba izbrisana.';});
    }
    if (button.dataset.action === 'play') {
      player.pause(); if (hls) {hls.destroy();hls=null;}
      const path = track.play_path || `${filename}.mp3`, url = `/music/file/${mediaPath(path)}`;
      document.getElementById('player-panel').hidden=false; document.getElementById('now-playing').textContent=`${track.title} — ${track.artist || 'neznan izvajalec'}`;
      if (path.endsWith('.m3u8') && window.Hls?.isSupported()) {hls=new Hls({maxBufferLength:20});hls.loadSource(url);hls.attachMedia(player);hls.on(Hls.Events.MANIFEST_PARSED,()=>player.play().catch(()=>{}));}
      else {player.src=url;player.play().catch(()=>{status.textContent='Za predvajanje uporabi gumb na predvajalniku.';});}
    }
  });
  player.addEventListener('error',()=>{status.textContent='Posnetka ni mogoče predvajati. Preveri datoteko ali pripravi HLS.';});
  search.addEventListener('input',render);
  document.getElementById('save-all').addEventListener('click',()=>operation('Shranjujem spremembe …',async()=>{for(const id of [...drafts.keys()]) await save(id);status.textContent='Vse spremembe shranjene.';}));
  document.getElementById('refresh').addEventListener('click',()=>operation('Osvežujem …',async()=>{await refresh();status.textContent='Seznam osvežen. Neshranjene spremembe ostanejo v obrazcu.';}));
  document.getElementById('prepare').addEventListener('click',()=>operation('Pripravljam HLS, zaporedno po skladbah. Napredek spremljaj v terminalu; stran pusti odprto.',async()=>{const result=await api('/api/music/prepare',{});await refresh();status.textContent=result.message;}));
  document.getElementById('download-form').addEventListener('submit',event=>{event.preventDefault();operation('Prenašam in pripravljam skladbe. Napredek je v terminalu; stran pusti odprto.',async()=>{await api('/api/music/download-yt',{url:document.getElementById('yt-url').value.trim()});await refresh();status.textContent='Prenos in priprava zaključena. Preglej podatke spodaj.';});});
  window.addEventListener('beforeunload',event=>{if(drafts.size||busy){event.preventDefault();event.returnValue='';}});
  render();
})();
