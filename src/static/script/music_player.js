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
const albumCover = document.querySelector(".album-cover");

let currentAlbum = localStorage.getItem("album") || "Vse";
let currentTrack = localStorage.getItem("track") || null;
let currentTime = parseFloat(localStorage.getItem("time") || 0);
let currentSongs = [];
let currentIndex = -1;
let isLoadingTrack = false;

// Render albumi
function renderAlbums() {
    albumListEl.innerHTML = "";
    albums.forEach(a => {
        const div = document.createElement("div");
        div.textContent = a["name"];
        div.className = "album-item" + (a["name"]===currentAlbum?" active":"");
        div.onclick = () => {
            div.style.transform = "scale(0.95)";
            setTimeout(() => div.style.transform = "scale(1)", 100);
            loadAlbum(a);
        };
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
        trackListEl.innerHTML = "<i style='color: #999; padding: 20px; text-align: center;'>Ni pesmi v tej zbirki.</i>";
        nowPlayingTitle.textContent = "Ni izbrane pesmi";
        nowPlayingArtist.textContent = "";
        nowPlayingAlbum.textContent = "";
        audio.src = "";
        albumCover.style.opacity = "0.5";
        return;
    } else if (!currentSongs.includes(currentTrack)) {
        currentTrack = currentSongs[Math.floor(Math.random() * currentSongs.length)];
    }
    currentIndex = currentSongs.indexOf(currentTrack);

    trackListEl.innerHTML = "";
    currentSongs.forEach((s, i) => {
        const div = document.createElement("div");
        const trackMetadata = music_metadata[s];
        const title = trackMetadata["title"];
        const artist = trackMetadata["artist"];
        const album = trackMetadata["album"];
        div.innerHTML = `<i>${album}</i> : ${artist} : <b>${title}</b>`;

        div.className = "track-item" + (s===currentTrack?" active":"");
        
        div.onclick = () => {
            div.style.transform = "scale(0.98)";
            setTimeout(() => div.style.transform = "scale(1)", 100);
            playTrack(i);
        };
        trackListEl.appendChild(div);
    });
    scrollToActiveTrack();
    albumCover.style.opacity = "1";
}

function playTrack(i) {
    if (isLoadingTrack) return; // Prepreči hkratne klice
    isLoadingTrack = true;
    
    currentIndex = i;
    currentTrack = currentSongs[i];
    const trackMetadata = music_metadata[currentTrack];

    localStorage.setItem("track", currentTrack);

    const title = trackMetadata["title"];
    const artist = trackMetadata["artist"];
    const album = trackMetadata["album"];

    // Animiraj spremembo teksta
    nowPlayingTitle.style.opacity = "0.7";
    nowPlayingArtist.style.opacity = "0.7";
    nowPlayingAlbum.style.opacity = "0.7";
    
    setTimeout(() => {
        nowPlayingTitle.textContent = title;
        nowPlayingArtist.textContent = artist;
        nowPlayingAlbum.textContent = album;
        
        nowPlayingTitle.style.transition = "opacity 0.3s ease";
        nowPlayingArtist.style.transition = "opacity 0.3s ease";
        nowPlayingAlbum.style.transition = "opacity 0.3s ease";
        
        nowPlayingTitle.style.opacity = "1";
        nowPlayingArtist.style.opacity = "1";
        nowPlayingAlbum.style.opacity = "1";
    }, 150);

    // Animiraj album cover
    albumCover.style.transform = "scale(1)";
    albumCover.style.transition = "transform 0.3s ease";
    
    // Posodobimo Media Session
    updateMediaSession(title, artist, album);

    // 1. Nastavi vir
    audio.src = "/music/file/" + currentTrack;
    
    // 2. Samo enkrat naloži
    audio.load(); 

    // 3. Play
    const playPromise = audio.play();

    if (playPromise !== undefined) {
        playPromise
        .then(_ => {
            updatePlayBtn("true");
            isLoadingTrack = false;
        })
        .catch(error => {
            // AbortError je normalen, če uporabnik hitro klika "Next"
            if (error.name !== "AbortError") {
                console.error("Napaka pri predvajanju:", error);
                updatePlayBtn("false");
            }
            isLoadingTrack = false;
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
            artist: artist || "Neznan izvajalec",
            album: album || "",
            artwork: [
                { src: "/static/logo.png", sizes: "96x96", type: "image/png" },
                { src: "/static/logo.png", sizes: "128x128", type: "image/png" },
                { src: "/static/logo.png", sizes: "512x512", type: "image/png" },
            ]
        });

        // Kontrole
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
        
        navigator.mediaSession.setActionHandler("seekto", (details) => {
            if (details.fastSeek && 'fastSeek' in audio) {
              audio.fastSeek(details.seekTime);
              return;
            }
            audio.currentTime = details.seekTime;
            updatePositionState(); 
        });
    }
}

// Helper funkcija za posodobitev position state
function updatePositionState() {
    if ("mediaSession" in navigator && !isNaN(audio.duration)) {
        try {
            navigator.mediaSession.setPositionState({
                duration: audio.duration,
                playbackRate: audio.playbackRate,
                position: audio.currentTime
            });
        } catch(e) {
            // Ignoriraj napake, če metadata še ni naložen
        }
    }
}


function highlightTrack() {
    document.querySelectorAll(".track-item").forEach((t, idx) => {
        const wasActive = t.classList.contains("active");
        const isActive = idx === currentIndex;
        
        if (isActive && !wasActive) {
            // Prehod iz ne-aktivnega v aktivnega
            t.style.transition = "all 0.3s ease";
        }
        t.classList.toggle("active", isActive);
    });
}

function scrollToActiveTrack() {
    const active = document.querySelector(".track-item.active");
    if(active) active.scrollIntoView({behavior:"smooth", block:"center"});
}

// Controls
function togglePlay() { 
    if (audio.paused) {
        const playPromise = audio.play();
        if (playPromise !== undefined) {
            playPromise.then(() => {
                updatePlayBtn("true");
                playBtn.style.transform = "scale(0.95)";
                setTimeout(() => playBtn.style.transform = "scale(1)", 150);
            });
        }
    } else {
        audio.pause();
        updatePlayBtn("false");
        playBtn.style.transform = "scale(0.95)";
        setTimeout(() => playBtn.style.transform = "scale(1)", 150);
    }
}

function next() {
    if (randomMode) playTrack(Math.floor(Math.random() * currentSongs.length));
    else if (currentIndex < currentSongs.length - 1) playTrack(currentIndex + 1);
}

function prev() {
    // Če pesem igra že več kot 3 sekunde, jo samo resetiraj na začetek
    if (audio.currentTime > 3) {
        audio.currentTime = 0;
    } 
    // Sicer pojdi na prejšnjo
    else if (currentIndex > 0) {
        playTrack(currentIndex - 1);
    }
}

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
    
    // Animiraj gumb
    shuffleBtn.style.transform = "rotate(360deg) scale(1.15)";
    setTimeout(() => {
        shuffleBtn.style.transition = "transform 0.4s ease";
        shuffleBtn.style.transform = "rotate(0deg) scale(1)";
    }, 50);
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
        playBtn.style.transition = "all 0.3s ease";
    } else {
        playBtn.classList.remove("active");
        playIcon.className = "bi bi-play-fill";
        playBtn.style.transition = "all 0.3s ease";
    }
}

// Audio update
audio.ontimeupdate = () => {
    if (audio.duration) {
        progress.value = audio.currentTime;
        localStorage.setItem("time", audio.currentTime);
        timeDisplay.textContent = formatTime(audio.currentTime) + " / " + formatTime(audio.duration);
        updatePositionState();
    }
};

// Update visual background of the range to show played portion
function updateSeekBarBackground() {
    try {
        const max = parseFloat(progress.max) || 1;
        const val = parseFloat(progress.value) || 0;
        const pct = Math.max(0, Math.min(100, (val / max) * 100));
        // left colored, right grey
        progress.style.background = `linear-gradient(90deg, var(--vijolicna) ${pct}%, var(--light-gray) ${pct}% )`;
    } catch (e) {
        // ignore
    }
}

// ensure background updates during playback and when user drags
audio.ontimeupdate = () => {
    if (audio.duration) {
        progress.value = audio.currentTime;
        localStorage.setItem("time", audio.currentTime);
        timeDisplay.textContent = formatTime(audio.currentTime) + " / " + formatTime(audio.duration);
        updatePositionState();
        updateSeekBarBackground();
    }
};



progress.addEventListener("input", () => {
    audio.currentTime = progress.value;
    updatePositionState();
    updateSeekBarBackground();
});

// update on metadata load (set max) and immediately refresh background
audio.onloadedmetadata = () => {
    progress.max = audio.duration;
    if (currentTime && currentTrack === audio.src.replace("/music/", "")) audio.currentTime = currentTime;
    updateSeekBarBackground();
};

audio.onended = () => next();

audio.addEventListener("play", () => {
    albumCover.style.animation = "spin 3s linear infinite";
});

audio.addEventListener("pause", () => {
    albumCover.style.animation = "none";
});

function formatTime(s) {
    s = Math.floor(s);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m + ":" + sec.toString().padStart(2, "0");
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
    albumCover.style.opacity = "0.6";
});

audio.addEventListener('playing', () => {
    console.log("Audio igra.");
    albumCover.style.opacity = "1";
});

let initialAlbum = albums[0];
albums.forEach(a => {
    if (a["name"] === currentAlbum) {
        initialAlbum = a;
    }
});

// Initialize
loadAlbum(initialAlbum);
if (currentSongs.length > 0) playTrack(currentIndex || 0);

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
        trackListEl.innerHTML = "<i style='color: #999; padding: 20px; text-align: center;'>Ni rezultatov iskanja.</i>";
        return;
    }
    
    filteredSongs.forEach((s, idx) => {
        const div = document.createElement("div");
        const trackMetadata = music_metadata[s];
        const title = trackMetadata["title"];
        const artist = trackMetadata["artist"];
        const album = trackMetadata["album"];
        div.innerHTML = `<i>${album}</i> : ${artist} : <b>${title}</b>`;

        div.className = "track-item" + (s === currentTrack ? " active" : "");
        div.style.opacity = "0";
        div.style.animation = "fadeInSlide 0.3s ease forwards";
        div.style.animationDelay = (idx * 0.03) + "s";
        
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

// ===== MOBILE TOGGLE FUNCTIONALITY =====
function initializeBrowserToggle() {
    console.log("initializeBrowserToggle called");
    
    const albumsSection = document.getElementById("albums");
    const tracksSection = document.getElementById("tracks");
    const toggleButtons = document.querySelectorAll(".toggle-btn");
    
    console.log("Elements found:", {
        albumsSection: !!albumsSection,
        tracksSection: !!tracksSection,
        toggleButtonsCount: toggleButtons.length
    });
    
    // Preverka je browser v mobilnem modu
    const isMobile = window.innerWidth <= 768;
    
    if (!albumsSection || !tracksSection) {
        console.error("Album or tracks section not found");
        return;
    }
    
    function switchView(target) {
        console.log("switchView called with target:", target, "Mobile:", isMobile);
        
        toggleButtons.forEach(btn => {
            console.log("Processing button with data-target:", btn.dataset.target);
            btn.classList.remove("active");
            if (btn.dataset.target === target) {
                btn.classList.add("active");
            }
        });
        
        if (target === "albums") {
            albumsSection.classList.add("active");
            tracksSection.classList.remove("active");
            console.log("Showing albums");
        } else {
            tracksSection.classList.add("active");
            albumsSection.classList.remove("active");
            console.log("Showing tracks");
        }
        
        // Spremi preference v localStorage
        localStorage.setItem("musicBrowserTab", target);
    }
    
    // Postavi event listenerjee na toggle gumbe
    console.log("Setting up click handlers for", toggleButtons.length, "buttons");
    toggleButtons.forEach((btn, index) => {
        console.log("Setting click handler on button", index, "with data-target:", btn.dataset.target);
        btn.addEventListener("click", (e) => {
            console.log("Toggle button clicked:", btn.dataset.target);
            e.preventDefault();
            e.stopPropagation();
            switchView(btn.dataset.target);
        });
    });
    
    // Napolni prejšnjo izbiro ali privzeto Album
    const savedTab = localStorage.getItem("musicBrowserTab") || "albums";
    console.log("Initializing with saved tab:", savedTab, "or default: albums");
    switchView(savedTab);
    
    // Dodaj event listener za orientationchange
    window.addEventListener("orientationchange", () => {
        console.log("Orientation changed");
        setTimeout(() => {
            switchView(localStorage.getItem("musicBrowserTab") || "albums");
        }, 200);
    });
}

// Kliči funkcijo ko je DOM pripravljen - z agresivnim timouttom
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        console.log("DOMContentLoaded fired");
        initializeBrowserToggle();
    });
} else {
    console.log("Document already loaded");
    initializeBrowserToggle();
}

// Tudi pri load
window.addEventListener("load", () => {
    console.log("Window load fired");
    setTimeout(() => {
        initializeBrowserToggle();
    }, 100);
});
