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
    Object.keys(albums).forEach(a => {
        const div = document.createElement("div");
        div.textContent = a;
        div.className = "album-item" + (a===currentAlbum?" active":"");
        div.onclick = () => loadAlbum(a);
        albumListEl.appendChild(div);
    });
}

// Load album
function loadAlbum(name) {
    currentAlbum = name;
    localStorage.setItem("album", name);
    currentSongs = albums[name];
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

    audio.src = "/music/file/" + currentTrack;
    audio.currentTime = 0;
    audio.play().catch(() => {});

    highlightTrack();
    scrollToActiveTrack();

    // === MEDIA SESSION (iPhone lock screen, Control Center) ===
    if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title: title,
            artist: artist,
            album: album,
            artwork: [
                { src: "/static/logo.png", sizes: "96x96", type: "image/png" },
                { src: "/static/logo.png", sizes: "192x192", type: "image/png" },
                { src: "/static/logo.png", sizes: "512x512", type: "image/png" }
            ]
        });

        navigator.mediaSession.setActionHandler("play", () => {
            audio.play();
            updatePlayBtn("true");
        });

        navigator.mediaSession.setActionHandler("pause", () => {
            audio.pause();
            updatePlayBtn("false");
        });

        navigator.mediaSession.setActionHandler("previoustrack", () => {
            prev();
        });

        navigator.mediaSession.setActionHandler("nexttrack", () => {
            next();
        });
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

// Initialize
loadAlbum(currentAlbum);
if(currentSongs.length>0) playTrack(currentIndex||0);
