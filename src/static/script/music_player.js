const root = document.getElementById("albums-root");
const albums = JSON.parse(root.dataset.albums);
const metadata_root = document.getElementById("metadata-root");
const music_metadata = JSON.parse(metadata_root.dataset.music);

const albumListEl = document.getElementById("albumList");
const trackListEl = document.getElementById("trackList");
const audio = document.getElementById("audio");
const nowPlayingTitle = document.getElementById("nowPlayingTitle");
const nowPlayingArtist = document.getElementById("nowPlayingArtist");
const nowPlayingAlbum = document.getElementById("nowPlayingAlbum");
const progress = document.getElementById("seekBar");
const timeDisplay = document.getElementById("timeDisplay");

let currentAlbum = localStorage.getItem("album") || "Vse";
let currentTrack = localStorage.getItem("track") || null;
let currentTime = parseFloat(localStorage.getItem("time") || 0);
let currentSongs = [];
let currentIndex = -1;

// Render albumi
function renderAlbums() {
    albumListEl.innerHTML = "";
    albums.forEach(a => {
        const div = document.createElement("div");
        div.textContent = a["name"];
        div.className = "album-item" + (a["name"]===currentAlbum?" active":"");
        div.onclick = () => loadAlbum(a);
        albumListEl.appendChild(div);
    });
}

// Load album
function loadAlbum(album) {
    currentAlbum = album["name"];
    localStorage.setItem("album", currentAlbum);
    currentSongs = album["songs"];
    renderAlbums();

    if (currentSongs.length === 0) {
        trackListEl.innerHTML = "<i>Ni pesmi v tej zbirki.</i>";
        nowPlayingTitle.textContent = "-";
        nowPlayingArtist.textContent = "-";
        nowPlayingAlbum.textContent = "-";
        audio.src = "";
        return;
    } else if (!currentSongs.includes(currentTrack)) {
        currentTrack = currentSongs[Math.floor(Math.random() * currentSongs.length)];
    }
    currentIndex = currentSongs.indexOf(currentTrack);

    trackListEl.innerHTML = "";
    currentSongs.forEach((s,i)=>{
        const div = document.createElement("div");
        const trackMetadata = music_metadata[s];
        const title = trackMetadata["title"];
        const artist = trackMetadata["artist"];
        const album = trackMetadata["album"];
        div.innerHTML = `<i>${album}</i> : ${artist} : <b>${title}</b>`;

        div.className = "track-item" + (s===currentTrack?" active":"");
        div.onclick = ()=>playTrack(i);
        trackListEl.appendChild(div);
    });
    scrollToActiveTrack();
}

function playTrack(i) {
    currentIndex = i;
    currentTrack = currentSongs[i];
    const trackMetadata = music_metadata[currentTrack];

    localStorage.setItem("track", currentTrack);

    const title = trackMetadata["title"];
    const artist = trackMetadata["artist"];
    const album = trackMetadata["album"];

    nowPlayingTitle.textContent = title;
    nowPlayingArtist.textContent = artist;
    nowPlayingAlbum.textContent = album;

    // 1. Nastavi vir
    audio.src = "/music/file/" + currentTrack;
    
    // 2. Eksplicitno naloži (pomaga na iOS)
    audio.load(); 

    // 3. Obravnavaj Play Promise
    const playPromise = audio.play();

    if (playPromise !== undefined) {
        playPromise.then(_ => {
            // Predvajanje se je uspešno začelo
            updatePlayBtn("true");
            
            // Nastavi Media Session šele ko se dejansko začne predvajati
            updateMediaSession(title, artist, album);
        })
        .catch(error => {
            console.error("Napaka pri predvajanju:", error);
            // Če je napaka, posodobi gumb na "pause", da uporabnik vidi, da ne igra
            updatePlayBtn("false");
        });
    }

    highlightTrack();
    scrollToActiveTrack();
}

// Ločena funkcija za Media Session (da je koda bolj čista)
function updateMediaSession(title, artist, album) {
    if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: title,
            artwork: [
                { src: "/static/logo.png", sizes: "512x512", type: "image/png" }
            ],
            ...(artist && { artist: artist }),
            ...(album && { album: album })
        });

        navigator.mediaSession.setActionHandler("play", () => {
            audio.play();
            updatePlayBtn("true");
        });
        navigator.mediaSession.setActionHandler("pause", () => {
            audio.pause();
            updatePlayBtn("false");
        });
        navigator.mediaSession.setActionHandler("previoustrack", prev);
        navigator.mediaSession.setActionHandler("nexttrack", next);
    }
}


function highlightTrack() {
    document.querySelectorAll(".track-item").forEach((t, idx)=>{
        t.classList.toggle("active", idx===currentIndex);
    });
}

function scrollToActiveTrack() {
    const active = document.querySelector(".track-item.active");
    if(active) active.scrollIntoView({behavior:"smooth", block:"center"});
}

// Controls
function togglePlay() { 
    if(audio.paused) {
        audio.play();
        updatePlayBtn("true")}
    else {
        audio.pause(); updatePlayBtn("false"); }}

function next() {
    if(randomMode) playTrack(Math.floor(Math.random()*currentSongs.length));
    else if(currentIndex<currentSongs.length-1) playTrack(currentIndex+1);
}
function prev() { if(currentIndex>0) playTrack(currentIndex-1); }

const shuffleBtn = document.getElementById("shuffleBtn");
let randomMode = JSON.parse(localStorage.getItem("random") || "false");
const shuffleIcon = document.getElementById("shuffleIcon");

const playBtn = document.getElementById("playBtn");
const playIcon = document.getElementById("playIcon");

// Posodobimo gumb ob zagonu
updateShuffleBtn();
updatePlayBtn("false");

// Toggle random
function toggleRandom() {
    randomMode = !randomMode;
    localStorage.setItem("random", randomMode);
    updateShuffleBtn();
}

function updateShuffleBtn() {

    if (randomMode) {
        shuffleBtn.classList.add("active");
        shuffleIcon.className = "bi bi-shuffle";
    } else {
        shuffleBtn.classList.remove("active");
        shuffleIcon.className = "bi bi-arrow-right";
    }
}

function updatePlayBtn(playMode) {
    if (playMode == "true") {
        playBtn.classList.add("active");
        playIcon.className = "bi bi-pause-fill";
    } else {
        playBtn.classList.remove("active");
        playIcon.className = "bi bi-play-fill";
    }
}

// Audio update
audio.ontimeupdate = ()=>{
    if(audio.duration){
        progress.value = audio.currentTime;
        localStorage.setItem("time", audio.currentTime);
        timeDisplay.textContent = formatTime(audio.currentTime)+" / "+formatTime(audio.duration);
    }
};
audio.onloadedmetadata = ()=>{
    progress.max = audio.duration;
    if(currentTime && currentTrack===audio.src.replace("/music/","")) audio.currentTime=currentTime;
};
progress.oninput = ()=>{ audio.currentTime = progress.value; }
audio.onended = ()=>next();

function formatTime(s){
    s=Math.floor(s);
    const m=Math.floor(s/60);
    const sec=s%60;
    return m+":"+sec.toString().padStart(2,"0");
}

function izbrisiPesem() {
    const token = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    if (confirm("Res želiš izbrisati to pesem?")) {
        fetch(`/music/delete/` + currentTrack, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': token
            }
        })
        .then(response => {
            if (response.ok) {
                next();
            } else {
                alert("Napaka pri brisanju pesmi!");
            }
        });
    }
}

audio.addEventListener('waiting', () => {
    console.log("Audio se nalaga...");
    // Tukaj lahko dodaš kakšen "loading spinner" na UI
});

audio.addEventListener('playing', () => {
    console.log("Audio igra.");
});

// Zelo pomembno: Poskusi ponovno predvajati, če se zatakne
audio.addEventListener('stalled', () => {
   console.log("Povezava je prekinjena, poskušam ponovno naložiti.");
   audio.load();
   audio.play().catch(e => console.error(e));
});

let initialAlbum = albums[0]
albums.forEach(a => {
    if (a["name"]===currentAlbum) {
        initialAlbum = a;
    }
});

// Initialize
loadAlbum(initialAlbum);
if(currentSongs.length>0) playTrack(currentIndex||0);

// ======== ISKANJE ========
const searchInput = document.getElementById("searchInput");
let filteredSongs = [];

function filterSongs() {
    const searchTerm = searchInput.value.toLowerCase();
    
    if (!searchTerm) {
        filteredSongs = currentSongs;
    } else {
        filteredSongs = currentSongs.filter(song => {
            const metadata = music_metadata[song];
            const title = (metadata["title"] || "").toLowerCase();
            const artist = (metadata["artist"] || "").toLowerCase();
            const album = (metadata["album"] || "").toLowerCase();
            
            return title.includes(searchTerm) || 
                   artist.includes(searchTerm) || 
                   album.includes(searchTerm);
        });
    }
    
    renderFilteredTracks();
}

function renderFilteredTracks() {
    trackListEl.innerHTML = "";
    if (filteredSongs.length === 0) {
        trackListEl.innerHTML = "<i>Ni rezultatov iskanja.</i>";
        return;
    }
    
    filteredSongs.forEach((s, idx) => {
        const div = document.createElement("div");
        const trackMetadata = music_metadata[s];
        const title = trackMetadata["title"];
        const artist = trackMetadata["artist"];
        const album = trackMetadata["album"];
        div.innerHTML = `<i>${album}</i> : ${artist} : <b>${title}</b>`;

        div.className = "track-item" + (s===currentTrack?" active":"");
        div.onclick = () => {
            // Najdi indeks v originalnem currentSongs polju
            const originalIndex = currentSongs.indexOf(s);
            playTrack(originalIndex);
        };
        trackListEl.appendChild(div);
    });
    scrollToActiveTrack();
}

searchInput.addEventListener("input", filterSongs);
