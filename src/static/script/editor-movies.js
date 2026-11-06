(() => {
  'use strict';
  const list = document.getElementById('movie-list'), workspace = document.getElementById('workspace');
  let movies = [], current = null, step = 0, metadata = {}, selected = [], mode = 'merge', busy = false, dirty = false;
  const labels = ['Pregled','Način','Podatki','Podnapisi','Potrditev'];
  const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const path = value => value.split('/').map(encodeURIComponent).join('/');
  async function api(url,data) {
    const response = await fetch(url,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name=csrf-token]').content},...(data?{body:JSON.stringify(data)}:{})});
    const result = await response.json().catch(()=>({message:`Zahteva ni uspela (${response.status}). Preveri terminal urejevalnika.`}));
    if(!response.ok||result.status==='error') throw Error(result.message||'Zahteva ni uspela.');
    return result;
  }
  function drawList() {
    const term=document.getElementById('movie-search').value.toLocaleLowerCase('sl');
    const visible=movies.filter(movie=>movie.name.toLocaleLowerCase('sl').includes(term));
    list.innerHTML=visible.length?visible.map(movie=>`<button type="button" class="movie" data-folder="${esc(movie.folder)}" aria-current="${movie.folder===current?.folder}" ${busy?'disabled':''}><strong>${esc(movie.name)}</strong><small>${movie.videos.length} videov · ${movie.subtitles.length} podnapisov</small></button>`).join(''):'<p class="hint">Ni neurejenih filmov za ta izbor. Dodaj mapo z videom in osveži seznam.</p>';
  }
  async function loadMovies() {try{movies=(await api('/api/movies/incoming')).movies;drawList();}catch(error){list.textContent=error.message;}}
  function remember() {
    workspace.querySelectorAll('[data-field]').forEach(input=>metadata[input.dataset.field]=input.value);
    const chosen=workspace.querySelector('input[name=mode]:checked');if(chosen)mode=chosen.value;
    if(step===3)selected=[...workspace.querySelectorAll('[data-sub]:checked')].map(input=>input.dataset.sub);
  }
  function select(folder) {
    if(dirty&&!confirm('Zamenjam film in zavržem neshranjene spremembe obrazca?'))return;
    current=movies.find(movie=>movie.folder===folder);step=0;dirty=false;mode=current.is_collection?'collection':'merge';selected=[...current.subtitles];metadata={title:current.name.replace(/[._-]/g,' '),original_title:'',year:'',imdb_id:'',plot:'',players:'',genres:[],...current.metadata};drawList();render();
  }
  function render() {
    workspace.innerHTML=`<ol class="steps" aria-label="Napredek">${labels.map((label,index)=>`<li ${step===index?'aria-current="step"':''}>${index+1}. ${label}</li>`).join('')}</ol><div class="step-card"><div id="step-body"></div><p id="status" class="status" role="status" aria-live="polite"></p><div class="actions"><button type="button" class="secondary" data-action="previous" ${step===0?'disabled':''}>Nazaj</button><button type="button" class="primary" data-action="${step===4?'finish':'next'}">${step===4?'Potrdi in pripravi HLS':'Naprej'}</button></div></div>`;
    const body=document.getElementById('step-body');
    if(step===0)body.innerHTML=`<h2 tabindex="-1">${esc(current.name)}</h2><p class="hint">Preveri sliko, zvok in vrstni red datotek. MKV/AVI/VOB brskalnik morda ne predvaja; preveri jih lokalno.</p><div class="preview"><video controls preload="metadata" src="/movie/file/${path(current.folder+'/'+current.videos[0])}"></video><div class="files">${current.videos.map((file,index)=>`<div>${index+1}. ${esc(file)}</div>`).join('')}</div></div>`;
    if(step===1)body.innerHTML=`<h2 tabindex="-1">Kako obdelam datoteke?</h2><p class="hint">Pri zbirki deli ostanejo ločeni. Združitev sledi vrstnemu redu na prejšnjem koraku.</p><div class="choices">${[['merge','En film','Več delov združi v en posnetek.'],['collection','Zbirka','Vsak video ostane samostojen del.']].map(([value,title,hint])=>`<label class="choice"><input type="radio" name="mode" value="${value}" ${mode===value?'checked':''}><span><b>${title}</b><span>${hint}</span></span></label>`).join('')}</div>`;
    if(step===2)body.innerHTML=`<h2 tabindex="-1">Podatki o filmu</h2><p class="hint">Vnesi podatke ali IMDb ID, nato pridobi predlog. Pred nadaljevanjem ga lahko popraviš.</p><div class="form-grid">${[['title','Naslov *'],['original_title','Izvirni naslov'],['year','Leto'],['imdb_id','IMDb ID (npr. tt0118799)'],['players','Igralci']].map(([id,label])=>`<div class="field"><label for="${id}">${label}</label><input id="${id}" data-field="${id}" type="text" ${id==='title'?'required':''} value="${esc(Array.isArray(metadata[id])?metadata[id].join('; '):metadata[id])}"></div>`).join('')}<div class="field wide"><label for="plot">Opis</label><textarea id="plot" data-field="plot">${esc(metadata.plot)}</textarea></div></div><div class="controls"><button type="button" data-action="metadata" class="secondary">Pridobi po IMDb ID</button></div>`;
    if(step===3)body.innerHTML=`<h2 tabindex="-1">Podnapisi</h2><p class="hint">Izberi podnapise za objavo. Neizbrani se ohranijo v mapi .originals. Prevod potrebuje nastavljene storitve in lahko traja več minut.</p><div class="controls"><button type="button" data-action="download" class="secondary">Prenesi slovenske in angleške</button><button type="button" data-action="translate" class="secondary">Prevedi izbrane SRT</button></div><div>${current.subtitles.length?current.subtitles.map(file=>`<label class="subtitle"><input type="checkbox" data-sub="${esc(file)}" ${selected.includes(file)?'checked':''}><span>${esc(file)}</span></label>`).join(''):'<p class="hint">Ni podnapisov. Film lahko pripraviš tudi brez njih.</p>'}</div>`;
    if(step===4)body.innerHTML=`<h2 tabindex="-1">Preveri pred pretvorbo</h2><div class="files"><div><b>Naslov:</b> ${esc(metadata.title)}</div><div><b>Način:</b> ${mode==='collection'?'Ločeni deli zbirke':'En film'}</div><div><b>Podnapisi:</b> ${selected.length?selected.map(esc).join(', '):'Brez'}</div></div><p class="hint">Obdelava poteka zaporedno. Izvorni videi ostanejo v .originals; nov HLS se objavi po končani pretvorbi. Napredek spremljaj v terminalu.</p>`;
    body.querySelector('h2')?.focus();
  }
  async function operation(message,work) {
    if(busy)return;remember();busy=true;document.getElementById('status').textContent=message;
    document.querySelectorAll('button,input,textarea').forEach(element=>element.disabled=true);
    try{await work();}catch(error){document.getElementById('status').className='status error';document.getElementById('status').textContent=error.message;}
    finally{busy=false;document.querySelectorAll('button,input,textarea').forEach(element=>element.disabled=false);const previous=workspace.querySelector('[data-action=previous]');if(previous)previous.disabled=step===0;drawList();}
  }
  workspace.addEventListener('input',()=>dirty=true);
  workspace.addEventListener('change',()=>{remember();dirty=true;});
  workspace.addEventListener('click',event=>{
    const action=event.target.closest('[data-action]')?.dataset.action;if(!action||busy)return;
    remember();
    if(action==='previous'){step--;render();}
    if(action==='next'){if(step===2&&!metadata.title.trim()){document.getElementById('title').reportValidity();return;}step++;render();}
    if(action==='metadata')operation('Pridobivam podatke …',async()=>{metadata={...metadata,...(await api('/api/movies/metadata',{folder:current.folder,imdb_id:metadata.imdb_id})).metadata};dirty=true;render();document.getElementById('status').textContent='Predlog pridobljen. Preglej podatke.';});
    if(action==='download'||action==='translate')operation(action==='download'?'Prenašam podnapise …':'Prevajam izbrane podnapise. Napredek je v terminalu …',async()=>{
      if(action==='translate'&&!selected.some(file=>file.endsWith('.srt')))throw Error('Izberi vsaj eno datoteko SRT.');
      const result=await api(`/api/movies/subtitles/${action}`,{folder:current.folder,metadata,languages:['sl','en'],files:selected.filter(file=>file.endsWith('.srt'))});
      if((action==='download'&&!result.downloaded)||(action==='translate'&&!result.translated?.length)){document.getElementById('status').textContent=action==='download'?'Ni novih podnapisov. Preveri IMDb ID in storitev ali jih dodaj ročno.':'Prevod ni bil ustvarjen. Preveri nastavitve storitve in izpis v terminalu.';return;}
      const fresh=(await api('/api/movies/incoming')).movies.find(movie=>movie.folder===current.folder);if(fresh){current=fresh;selected=[...current.subtitles];}render();document.getElementById('status').textContent='Končano. Preglej izbor podnapisov.';
    });
    if(action==='finish')operation('Pripravljam HLS … Stran pusti odprto, napredek spremljaj v terminalu.',async()=>{
      const result=await api('/api/movies/process',{folder:current.folder,mode,metadata,subtitles:selected});dirty=false;
      workspace.innerHTML=`<div class="panel"><h2>Film pripravljen</h2><p>${esc(metadata.title)} · ${result.hls.length} HLS posnetkov</p><p>Preveri predvajanje, nato mapo <code>${esc(result.folder)}</code> premakni iz neurejenih filmov v želeno kategorijo. Knjižnico osveži z <code>docker compose restart app</code>.</p><p id="status" role="status">Izvorne datoteke ostanejo v .originals.</p></div>`;current=null;await loadMovies();
    });
  });
  list.addEventListener('click',event=>{const button=event.target.closest('[data-folder]');if(button&&!busy)select(button.dataset.folder);});
  document.getElementById('movie-search').addEventListener('input',drawList);
  document.getElementById('refresh').addEventListener('click',loadMovies);
  window.addEventListener('beforeunload',event=>{if(dirty||busy){event.preventDefault();event.returnValue='';}});
  loadMovies();
})();
