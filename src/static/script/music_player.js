let albums = [];
let publicAlbums = [];
let privateAlbums = [];
let musicMetadata = {};

const albumsRoot = document.getElementById("albums-root");
const metadataRoot = document.getElementById("metadata-root");
const configRoot = document.getElementById("music-config-root");
const albumListEl = document.getElementById("albumList");
const trackListEl = document.getElementById("trackList");
const audio = document.getElementById("audio");
const nowPlayingTitle = document.getElementById("nowPlayingTitle");
const nowPlayingArtist = document.getElementById("nowPlayingArtist");
const nowPlayingAlbum = document.getElementById("nowPlayingAlbum");
const progress = document.getElementById("seekBar");
const timeDisplay = document.getElementById("timeDisplay");
const albumCover = document.querySelector(".album-cover");
const searchInput = document.getElementById("searchInput");
const privateAlbumAddControls = document.getElementById("privateAlbumAddControls");
const privateAlbumRemoveControls = document.getElementById("privateAlbumRemoveControls");
const privateAlbumSelect = document.getElementById("privateAlbumSelect");
const addCurrentSongBtn = document.getElementById("addCurrentSongBtn");
const removeCurrentSongBtn = document.getElementById("removeCurrentSongBtn");
const privateAlbumsManagerList = document.getElementById("privateAlbumsManagerList");
const newPrivateAlbumForm = document.getElementById("newPrivateAlbumForm");
const newPrivateAlbumNameInput = document.getElementById("newPrivateAlbumName");
const shuffleBtn = document.getElementById("shuffleBtn");
const shuffleIcon = document.getElementById("shuffleIcon");
const playBtn = document.getElementById("playBtn");
const playIcon = document.getElementById("playIcon");

const isRadioStoriesPage = Boolean(
    window.IS_RADIO_STORIES_PAGE || window.RADIO_STORIES_FILES
);
const fileBase = window.MEDIA_FILE_BASE || "/music/file/";
const hlsBase = window.MEDIA_HLS_BASE || "/music/hls/";
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
const privateAlbumsEndpoint = configRoot?.dataset?.privateAlbumsEndpoint || "/music/private-albums";
const maxPrivateAlbums = parseInt(configRoot?.dataset?.privateAlbumsMax || "10", 10) || 10;

let currentAlbumKey = localStorage.getItem("musicAlbumKey") || null;
let currentTrack = localStorage.getItem("track") || null;
let currentTime = parseFloat(localStorage.getItem("time") || 0);
let currentSongs = [];
let currentIndex = -1;
let filteredSongs = [];
let selectedPrivateAlbumId = localStorage.getItem("musicPrivateAlbumTarget") || null;
let isLoadingTrack = false;
let pendingRestoreTime = currentTime;
let hlsInstance = null;
let randomMode = JSON.parse(localStorage.getItem("random") || "false");

function parseJsonDataset(element, key, fallback) {
    if (!element?.dataset?.[key]) {
        return fallback;
    }

    try {
        return JSON.parse(element.dataset[key]);
    } catch (_error) {
        return fallback;
    }
}

albums = parseJsonDataset(albumsRoot, "albums", []);
musicMetadata = parseJsonDataset(metadataRoot, "music", {});

if ((!albums || albums.length === 0) && window.RADIO_STORIES_FILES) {
    albums = [{ name: "Vse", songs: window.RADIO_STORIES_FILES }];
}
if (
    (!musicMetadata || Object.keys(musicMetadata).length === 0)
    && window.RADIO_STORIES_METADATA
) {
    musicMetadata = window.RADIO_STORIES_METADATA;
}

privateAlbums = parseJsonDataset(
    configRoot,
    "privateAlbums",
    albums.filter(album => album.is_private)
);
publicAlbums = albums.filter(album => !album.is_private);
albums = [...privateAlbums, ...publicAlbums];

function encodeMediaPath(path) {
    return String(path)
        .split("/")
        .map(segment => encodeURIComponent(segment))
        .join("/");
}

function getTrackMetadata(trackId) {
    return musicMetadata[trackId] || {};
}

function getAlbumDisplayInfo(albumName) {
    const rawAlbum = String(albumName || "");
    const separator = " - ";
    const separatorIndex = rawAlbum.indexOf(separator);

    if (separatorIndex === -1) {
        return {
            displayName: rawAlbum,
            hasSeparator: false,
        };
    }

    return {
        displayName: rawAlbum.slice(separatorIndex + separator.length).trim(),
        hasSeparator: true,
    };
}

function getAlbumKey(album) {
    if (!album) {
        return null;
    }
    return album.is_private ? `private:${album.id}` : `public:${album.name}`;
}

function findAlbumByKey(albumKey) {
    return albums.find(album => getAlbumKey(album) === albumKey) || null;
}

function getCurrentAlbum() {
    return findAlbumByKey(currentAlbumKey);
}

function persistSelectedPrivateAlbum() {
    if (selectedPrivateAlbumId) {
        localStorage.setItem("musicPrivateAlbumTarget", selectedPrivateAlbumId);
    } else {
        localStorage.removeItem("musicPrivateAlbumTarget");
    }
}

function ensureSelectedPrivateAlbum(options = {}) {
    const preferCurrentAlbum = Boolean(options.preferCurrentAlbum);
    const currentAlbum = getCurrentAlbum();

    if (
        preferCurrentAlbum
        && currentAlbum?.is_private
        && !privateAlbums.some(album => album.id === selectedPrivateAlbumId)
    ) {
        selectedPrivateAlbumId = currentAlbum.id;
    }

    if (!privateAlbums.some(album => album.id === selectedPrivateAlbumId)) {
        selectedPrivateAlbumId = privateAlbums[0]?.id || null;
    }

    persistSelectedPrivateAlbum();
}

function destroyHlsInstance() {
    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }
}

function resolveTrackSource(trackId) {
    const metadata = getTrackMetadata(trackId);
    const filePath = metadata.file_path || trackId;
    const hlsPath = metadata.hls_path || null;
    const encodedFilePath = filePath ? encodeMediaPath(filePath) : null;
    const encodedHlsPath = hlsPath ? encodeMediaPath(hlsPath) : null;

    return {
        fileUrl: encodedFilePath ? fileBase + encodedFilePath : null,
        hlsUrl: encodedHlsPath ? hlsBase + encodedHlsPath : null,
    };
}

function attachTrackSource(trackId) {
    const source = resolveTrackSource(trackId);

    destroyHlsInstance();
    audio.pause();
    audio.removeAttribute("src");
    audio.load();

    if (source.hlsUrl) {
        if (audio.canPlayType("application/vnd.apple.mpegurl")) {
            audio.src = source.hlsUrl;
            audio.load();
            return Promise.resolve();
        }

        if (window.Hls && window.Hls.isSupported()) {
            return new Promise((resolve, reject) => {
                hlsInstance = new window.Hls();
                hlsInstance.loadSource(source.hlsUrl);
                hlsInstance.attachMedia(audio);

                hlsInstance.on(window.Hls.Events.MANIFEST_PARSED, () => {
                    resolve();
                });

                hlsInstance.on(window.Hls.Events.ERROR, (_event, data) => {
                    if (!data || !data.fatal) {
                        return;
                    }

                    destroyHlsInstance();
                    if (source.fileUrl) {
                        audio.src = source.fileUrl;
                        audio.load();
                        resolve();
                        return;
                    }

                    reject(new Error(data.details || "HLS playback failed"));
                });
            });
        }
    }

    if (source.fileUrl) {
        audio.src = source.fileUrl;
        audio.load();
        return Promise.resolve();
    }

    return Promise.reject(new Error("No playable source found"));
}

function renderAlbums() {
    if (!albumListEl) {
        return;
    }

    albumListEl.innerHTML = "";
    albums.forEach(album => {
        const div = document.createElement("div");
        const albumNameInfo = getAlbumDisplayInfo(album.name);
        div.className = "album-item" + (getAlbumKey(album) === currentAlbumKey ? " active" : "");

        if (albumNameInfo.hasSeparator) {
            div.classList.add("album-item-after-separator");
        }

        if (album.is_private) {
            div.classList.add("album-item-private");
            div.innerHTML = `${albumNameInfo.displayName || album.name}<span class="album-item-private-badge">Moj album</span>`;
        } else {
            div.textContent = albumNameInfo.displayName || album.name;
        }

        div.onclick = () => {
            div.style.transform = "scale(0.95)";
            setTimeout(() => {
                div.style.transform = "scale(1)";
            }, 100);
            loadAlbum(album);
        };
        albumListEl.appendChild(div);
    });
}

function buildTrackHtml(songId) {
    const trackMetadata = getTrackMetadata(songId);
    const title = trackMetadata.title || songId.split("/").slice(-1)[0];
    const artist = trackMetadata.artist || "";
    const album = trackMetadata.album || "";
    const albumInfo = getAlbumDisplayInfo(album);

    if (isRadioStoriesPage) {
        const duration = trackMetadata.duration || 0;
        const artistPrefix = artist ? `${artist} : ` : "";
        return `<span class="track-main">${artistPrefix}<b>${title}</b></span><span class="track-duration">${formatTime(duration)}</span>`;
    }

    const albumClass = albumInfo.hasSeparator ? "album-after-separator" : "";
    return `<i class="${albumClass}">${albumInfo.displayName}</i> : ${artist} : <b>${title}</b>`;
}

function renderTrackCollection(songIds, useOriginalIndex) {
    if (!trackListEl) {
        return;
    }

    trackListEl.innerHTML = "";
    songIds.forEach((songId, idx) => {
        const div = document.createElement("div");
        div.innerHTML = buildTrackHtml(songId);
        div.className = "track-item" + (songId === currentTrack ? " active" : "");

        if (isRadioStoriesPage) {
            div.classList.add("radio-track-item");
        }

        const playIndex = useOriginalIndex ? currentSongs.indexOf(songId) : idx;
        div.onclick = () => {
            div.style.transform = "scale(0.98)";
            setTimeout(() => {
                div.style.transform = "scale(1)";
            }, 100);
            playTrack(playIndex);
        };
        trackListEl.appendChild(div);
    });
    scrollToActiveTrack();
}

function renderCurrentAlbumTracks() {
    if (!currentSongs.length) {
        trackListEl.innerHTML = "<i style='color: #999; padding: 20px; text-align: center;'>Ni pesmi v tej zbirki.</i>";
        return;
    }
    if (searchInput?.value) {
        filterSongs();
        return;
    }
    renderTrackCollection(currentSongs, false);
}

function resetNowPlayingState() {
    nowPlayingTitle.textContent = isRadioStoriesPage ? "Ni izbrane zgodbe" : "Ni izbrane pesmi";
    nowPlayingArtist.textContent = "";
    nowPlayingAlbum.textContent = "";
    audio.removeAttribute("src");
    audio.load();
    albumCover.style.opacity = "0.5";
}

function loadAlbum(album, options = {}) {
    if (!album) {
        return;
    }

    currentAlbumKey = getAlbumKey(album);
    localStorage.setItem("musicAlbumKey", currentAlbumKey);
    localStorage.setItem("album", album.name);
    currentSongs = [...(album.songs || [])];

    if (!currentSongs.length) {
        currentIndex = -1;
        renderAlbums();
        renderCurrentAlbumTracks();
        updatePrivateAlbumControls({ preferCurrentAlbum: true });
        resetNowPlayingState();
        return;
    }

    if (!currentSongs.includes(currentTrack)) {
        if (options.preserveCurrentTrackIfMissing) {
            currentIndex = -1;
        } else {
            currentTrack = currentSongs[0];
            currentIndex = 0;
        }
    } else {
        currentIndex = currentSongs.indexOf(currentTrack);
    }

    renderAlbums();
    renderCurrentAlbumTracks();
    updatePrivateAlbumControls({ preferCurrentAlbum: true });
    albumCover.style.opacity = "1";
}

async function playTrack(index) {
    if (isLoadingTrack || index < 0 || index >= currentSongs.length) {
        return;
    }
    isLoadingTrack = true;

    currentIndex = index;
    currentTrack = currentSongs[index];
    const trackMetadata = getTrackMetadata(currentTrack);
    const storedTrack = localStorage.getItem("track");
    const storedTime = parseFloat(localStorage.getItem("time") || 0);
    pendingRestoreTime = currentTrack === storedTrack ? storedTime : 0;

    localStorage.setItem("track", currentTrack);
    if (!pendingRestoreTime) {
        localStorage.setItem("time", 0);
    }

    const title = trackMetadata.title || currentTrack;
    const artist = trackMetadata.artist || "";
    const album = trackMetadata.album || "";
    const albumInfo = getAlbumDisplayInfo(album);

    nowPlayingTitle.style.opacity = "0.7";
    nowPlayingArtist.style.opacity = "0.7";
    nowPlayingAlbum.style.opacity = "0.7";

    setTimeout(() => {
        nowPlayingTitle.textContent = title;
        nowPlayingArtist.textContent = artist;
        nowPlayingAlbum.textContent = albumInfo.displayName;
        nowPlayingAlbum.classList.toggle("has-separator", albumInfo.hasSeparator);
        nowPlayingTitle.style.transition = "opacity 0.3s ease";
        nowPlayingArtist.style.transition = "opacity 0.3s ease";
        nowPlayingAlbum.style.transition = "opacity 0.3s ease";
        nowPlayingTitle.style.opacity = "1";
        nowPlayingArtist.style.opacity = "1";
        nowPlayingAlbum.style.opacity = "1";
    }, 150);

    albumCover.style.transform = "scale(1)";
    albumCover.style.transition = "transform 0.3s ease";
    updateMediaSession(title, artist, albumInfo.displayName);

    try {
        await attachTrackSource(currentTrack);
    } catch (error) {
        console.error("Napaka pri pripravi vira:", error);
        updatePlayBtn("false");
        isLoadingTrack = false;
        return;
    }

    const playPromise = audio.play();
    if (playPromise !== undefined) {
        playPromise
            .then(() => {
                updatePlayBtn("true");
                isLoadingTrack = false;
            })
            .catch(error => {
                if (error.name !== "AbortError") {
                    console.error("Napaka pri predvajanju:", error);
                    updatePlayBtn("false");
                }
                isLoadingTrack = false;
            });
    }

    highlightTrack();
    scrollToActiveTrack();
    updatePrivateAlbumControls();
}

function updateMediaSession(title, artist, album) {
    if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({
            title,
            artist: artist || "Neznan izvajalec",
            album: album || "",
            artwork: [
                { src: "/static/logo.png", sizes: "96x96", type: "image/png" },
                { src: "/static/logo.png", sizes: "128x128", type: "image/png" },
                { src: "/static/logo.png", sizes: "512x512", type: "image/png" },
            ],
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
        navigator.mediaSession.setActionHandler("seekto", details => {
            if (details.fastSeek && "fastSeek" in audio) {
                audio.fastSeek(details.seekTime);
                return;
            }
            audio.currentTime = details.seekTime;
            updatePositionState();
        });
    }
}

function updatePositionState() {
    if ("mediaSession" in navigator && !Number.isNaN(audio.duration)) {
        try {
            navigator.mediaSession.setPositionState({
                duration: audio.duration,
                playbackRate: audio.playbackRate,
                position: audio.currentTime,
            });
        } catch (_error) {
        }
    }
}

function highlightTrack() {
    const activeSongs = searchInput?.value ? filteredSongs : currentSongs;
    document.querySelectorAll(".track-item").forEach((trackEl, index) => {
        const songId = activeSongs[index];
        const wasActive = trackEl.classList.contains("active");
        const isActive = songId === currentTrack;

        if (isActive && !wasActive) {
            trackEl.style.transition = "all 0.3s ease";
        }
        trackEl.classList.toggle("active", isActive);
    });
}

function scrollToActiveTrack() {
    const active = document.querySelector(".track-item.active");
    if (active) {
        active.scrollIntoView({ behavior: "smooth", block: "center" });
    }
}

function togglePlay() {
    if (!audio.getAttribute("src") && currentSongs.length) {
        playTrack(currentIndex >= 0 ? currentIndex : 0);
        return;
    }

    if (audio.paused) {
        const playPromise = audio.play();
        if (playPromise !== undefined) {
            playPromise.then(() => {
                updatePlayBtn("true");
                playBtn.style.transform = "scale(0.95)";
                setTimeout(() => {
                    playBtn.style.transform = "scale(1)";
                }, 150);
            });
        }
    } else {
        audio.pause();
        updatePlayBtn("false");
        playBtn.style.transform = "scale(0.95)";
        setTimeout(() => {
            playBtn.style.transform = "scale(1)";
        }, 150);
    }
}

function next() {
    if (!currentSongs.length) {
        return;
    }
    if (randomMode) {
        playTrack(Math.floor(Math.random() * currentSongs.length));
        return;
    }
    if (currentIndex === -1) {
        playTrack(0);
        return;
    }
    if (currentIndex < currentSongs.length - 1) {
        playTrack(currentIndex + 1);
    }
}

function prev() {
    if (audio.currentTime > 3) {
        audio.currentTime = 0;
    } else if (currentIndex > 0) {
        playTrack(currentIndex - 1);
    }
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
    if (playMode === "true") {
        playBtn.classList.add("active");
        playIcon.className = "bi bi-pause-fill";
    } else {
        playBtn.classList.remove("active");
        playIcon.className = "bi bi-play-fill";
    }
    playBtn.style.transition = "all 0.3s ease";
}

function toggleRandom() {
    randomMode = !randomMode;
    localStorage.setItem("random", randomMode);
    updateShuffleBtn();

    shuffleBtn.style.transform = "rotate(360deg) scale(1.15)";
    setTimeout(() => {
        shuffleBtn.style.transition = "transform 0.4s ease";
        shuffleBtn.style.transform = "rotate(0deg) scale(1)";
    }, 50);
}

function updateSeekBarBackground() {
    try {
        const max = parseFloat(progress.max) || 1;
        const value = parseFloat(progress.value) || 0;
        const pct = Math.max(0, Math.min(100, (value / max) * 100));
        progress.style.background = `linear-gradient(90deg, var(--vijolicna) ${pct}%, lightgray ${pct}% )`;
    } catch (_error) {
    }
}

audio.ontimeupdate = () => {
    if (audio.duration) {
        progress.value = audio.currentTime;
        localStorage.setItem("time", audio.currentTime);
        timeDisplay.textContent = `${formatTime(audio.currentTime)} / ${formatTime(audio.duration)}`;
        updatePositionState();
        updateSeekBarBackground();
    }
};

progress.addEventListener("input", () => {
    audio.currentTime = progress.value;
    updatePositionState();
    updateSeekBarBackground();
});

audio.onloadedmetadata = () => {
    progress.max = Number.isFinite(audio.duration) ? audio.duration : 0;
    try {
        if (pendingRestoreTime > 0) {
            audio.currentTime = pendingRestoreTime;
        }
    } catch (_error) {
    }
    pendingRestoreTime = 0;
    updateSeekBarBackground();
};

audio.onended = () => next();

audio.addEventListener("play", () => {
    albumCover.style.animation = "spin 3s linear infinite";
});

audio.addEventListener("pause", () => {
    albumCover.style.animation = "none";
});

audio.addEventListener("waiting", () => {
    albumCover.style.opacity = "0.6";
});

audio.addEventListener("playing", () => {
    albumCover.style.opacity = "1";
});

audio.addEventListener("emptied", () => {
    updatePlayBtn("false");
});

function formatTime(seconds) {
    const totalSeconds = Math.floor(seconds);
    const minutes = Math.floor(totalSeconds / 60);
    const remainingSeconds = totalSeconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function izbrisiPesem() {
    if (confirm("Res želiš izbrisati to pesem?")) {
        const deleteBase = window.MEDIA_DELETE_BASE || "/music/delete/";
        const trackMetadata = getTrackMetadata(currentTrack);
        const deletePath = trackMetadata.delete_path || currentTrack;
        fetch(deleteBase + encodeMediaPath(deletePath), {
            method: "DELETE",
            headers: {
                "X-CSRFToken": csrfToken,
            },
        }).then(response => {
            if (response.ok) {
                next();
            } else {
                alert("Napaka pri brisanju pesmi!");
            }
        });
    }
}

function syncPrivateAlbums(nextPrivateAlbums, options = {}) {
    privateAlbums = (nextPrivateAlbums || []).map(album => ({ ...album, is_private: true }));
    albums = [...privateAlbums, ...publicAlbums];
    ensureSelectedPrivateAlbum({ preferCurrentAlbum: options.preferCurrentAlbum });
    renderAlbums();
    renderPrivateAlbumManager();
    updatePrivateAlbumControls();

    if (options.reloadCurrentAlbum === false) {
        return;
    }

    const activeAlbum = findAlbumByKey(currentAlbumKey) || albums[0] || null;
    if (activeAlbum) {
        loadAlbum(activeAlbum, {
            preserveCurrentTrackIfMissing: Boolean(options.preserveCurrentTrackIfMissing),
        });
    } else {
        resetNowPlayingState();
    }
}

async function requestPrivateAlbums(url, options = {}) {
    const fetchOptions = {
        method: options.method || "GET",
        headers: {
            Accept: "application/json",
        },
    };

    if (fetchOptions.method !== "GET" && csrfToken) {
        fetchOptions.headers["X-CSRFToken"] = csrfToken;
    }
    if (options.body !== undefined) {
        fetchOptions.headers["Content-Type"] = "application/json";
        fetchOptions.body = JSON.stringify(options.body);
    }

    const response = await fetch(url, fetchOptions);
    let payload = {};
    try {
        payload = await response.json();
    } catch (_error) {
        payload = {};
    }

    if (!response.ok) {
        throw new Error(payload.message || "Napaka pri posodobitvi privat albumov.");
    }
    return payload;
}

function renderPrivateAlbumManager() {
    if (!privateAlbumsManagerList) {
        return;
    }

    privateAlbumsManagerList.innerHTML = "";
    if (!privateAlbums.length) {
        privateAlbumsManagerList.innerHTML = "<div class='private-manager-empty'>Še nimaš privat albumov.</div>";
        return;
    }

    privateAlbums.forEach(album => {
        const row = document.createElement("div");
        row.className = "private-manager-row";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "form-control";
        input.maxLength = 80;
        input.value = album.name;

        const count = document.createElement("span");
        count.className = "private-manager-count";
        count.textContent = `${album.songs.length} pesmi`;

        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.className = "btn btn-outline-secondary btn-sm";
        saveBtn.textContent = "Preimenuj";
        saveBtn.onclick = async () => {
            const nextAlbumName = String(input.value || "").trim();

            if (nextAlbumName === album.name) {
                return;
            }
            if (
                !confirm(
                    `Res želiš preimenovati album \"${album.name}\" v \"${nextAlbumName}\"?`
                )
            ) {
                return;
            }

            try {
                const payload = await requestPrivateAlbums(`${privateAlbumsEndpoint}/${album.id}`, {
                    method: "PATCH",
                    body: { name: nextAlbumName },
                });
                syncPrivateAlbums(payload.albums, { reloadCurrentAlbum: false });
            } catch (error) {
                alert(error.message);
            }
        };

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "btn btn-outline-danger btn-sm";
        deleteBtn.textContent = "Odstrani";
        deleteBtn.onclick = async () => {
            if (!confirm(`Res želiš odstraniti album \"${album.name}\"?`)) {
                return;
            }
            try {
                const payload = await requestPrivateAlbums(`${privateAlbumsEndpoint}/${album.id}`, {
                    method: "DELETE",
                });
                syncPrivateAlbums(payload.albums, {
                    preserveCurrentTrackIfMissing: true,
                });
            } catch (error) {
                alert(error.message);
            }
        };

        row.appendChild(input);
        row.appendChild(count);
        row.appendChild(saveBtn);
        row.appendChild(deleteBtn);
        privateAlbumsManagerList.appendChild(row);
    });
}

function updatePrivateAlbumControls(options = {}) {
    ensureSelectedPrivateAlbum(options);

    if (
        !privateAlbumAddControls
        || !privateAlbumRemoveControls
        || !privateAlbumSelect
        || !addCurrentSongBtn
        || !removeCurrentSongBtn
    ) {
        return;
    }

    privateAlbumSelect.innerHTML = "";
    privateAlbums.forEach(album => {
        const option = document.createElement("option");
        option.value = album.id;
        option.textContent = album.name;
        privateAlbumSelect.appendChild(option);
    });

    privateAlbumSelect.disabled = privateAlbums.length === 0;
    if (selectedPrivateAlbumId) {
        privateAlbumSelect.value = selectedPrivateAlbumId;
    }

    const currentAlbum = getCurrentAlbum();
    const isInsidePrivateAlbum = Boolean(currentAlbum?.is_private);
    const canAddSong = Boolean(currentTrack && selectedPrivateAlbumId && !isInsidePrivateAlbum);
    const canRemoveSong = Boolean(currentAlbum?.is_private && currentTrack);
    const removeAlbumName = currentAlbum?.name || "tega albuma";

    privateAlbumAddControls.hidden = isInsidePrivateAlbum;
    privateAlbumRemoveControls.hidden = !currentAlbum?.is_private;
    addCurrentSongBtn.disabled = !canAddSong;
    removeCurrentSongBtn.disabled = !canRemoveSong;
    removeCurrentSongBtn.textContent = `Odstrani pesem iz albuma: ${removeAlbumName}`;
}

async function addSongsToSelectedPrivateAlbum(songIds) {
    if (!selectedPrivateAlbumId) {
        alert("Najprej ustvari ali izberi privat album.");
        return;
    }

    try {
        const payload = await requestPrivateAlbums(`${privateAlbumsEndpoint}/${selectedPrivateAlbumId}/songs`, {
            method: "POST",
            body: { song_ids: songIds },
        });
        const currentAlbum = getCurrentAlbum();
        const shouldReloadCurrentAlbum = currentAlbum?.is_private && currentAlbum.id === selectedPrivateAlbumId;
        syncPrivateAlbums(payload.albums, {
            reloadCurrentAlbum: shouldReloadCurrentAlbum,
            preferCurrentAlbum: shouldReloadCurrentAlbum,
        });
    } catch (error) {
        alert(error.message);
    }
}

async function removeCurrentSongFromPrivateAlbum() {
    const currentAlbum = getCurrentAlbum();
    if (!currentAlbum?.is_private || !currentTrack) {
        return;
    }

    const removedTrackIndex = currentIndex;

    if (
        !confirm(
            `Res želiš odstraniti trenutno pesem iz albuma \"${currentAlbum.name}\"?`
        )
    ) {
        return;
    }

    try {
        const payload = await requestPrivateAlbums(`${privateAlbumsEndpoint}/${currentAlbum.id}/songs`, {
            method: "DELETE",
            body: { song_ids: [currentTrack] },
        });
        syncPrivateAlbums(payload.albums, {
            preserveCurrentTrackIfMissing: true,
            preferCurrentAlbum: true,
        });

        if (currentSongs.length > 0) {
            const nextTrackIndex = Math.min(
                Math.max(removedTrackIndex, 0),
                currentSongs.length - 1
            );
            playTrack(nextTrackIndex);
        }
    } catch (error) {
        alert(error.message);
    }
}

function filterSongs() {
    const searchTerm = (searchInput?.value || "").toLowerCase();

    if (!searchTerm) {
        filteredSongs = [...currentSongs];
        renderTrackCollection(filteredSongs, true);
        return;
    }

    filteredSongs = currentSongs.filter(songId => {
        const metadata = musicMetadata[songId] || {};
        const title = (metadata.title || "").toLowerCase();
        const artist = (metadata.artist || "").toLowerCase();
        const album = (metadata.album || "").toLowerCase();

        return title.includes(searchTerm)
            || artist.includes(searchTerm)
            || album.includes(searchTerm);
    });

    if (!filteredSongs.length) {
        trackListEl.innerHTML = "<i style='color: #999; padding: 20px; text-align: center;'>Ni rezultatov iskanja.</i>";
        return;
    }

    renderTrackCollection(filteredSongs, true);
}

if (privateAlbumSelect) {
    privateAlbumSelect.addEventListener("change", () => {
        selectedPrivateAlbumId = privateAlbumSelect.value || null;
        persistSelectedPrivateAlbum();
        updatePrivateAlbumControls();
    });
}

if (addCurrentSongBtn) {
    addCurrentSongBtn.addEventListener("click", () => {
        if (currentTrack) {
            addSongsToSelectedPrivateAlbum([currentTrack]);
        }
    });
}

if (removeCurrentSongBtn) {
    removeCurrentSongBtn.addEventListener("click", removeCurrentSongFromPrivateAlbum);
}

if (newPrivateAlbumForm) {
    newPrivateAlbumForm.addEventListener("submit", async event => {
        event.preventDefault();
        try {
            const payload = await requestPrivateAlbums(privateAlbumsEndpoint, {
                method: "POST",
                body: { name: newPrivateAlbumNameInput?.value || "" },
            });
            selectedPrivateAlbumId = payload.album?.id || selectedPrivateAlbumId;
            persistSelectedPrivateAlbum();
            syncPrivateAlbums(payload.albums, { reloadCurrentAlbum: false });
            if (newPrivateAlbumNameInput) {
                newPrivateAlbumNameInput.value = "";
            }
            updatePrivateAlbumControls();
        } catch (error) {
            alert(error.message);
        }
    });
}

function initializeBrowserToggle() {
    const albumsSection = document.getElementById("albums");
    const tracksSection = document.getElementById("tracks");
    const toggleButtons = document.querySelectorAll(".toggle-btn");

    if (!albumsSection || !tracksSection) {
        return;
    }

    function switchView(target) {
        const nextTarget = isRadioStoriesPage && target === "albums" ? "tracks" : target;

        toggleButtons.forEach(btn => {
            btn.classList.toggle("active", btn.dataset.target === nextTarget);
        });

        if (nextTarget === "albums") {
            albumsSection.classList.add("active");
            tracksSection.classList.remove("active");
        } else {
            tracksSection.classList.add("active");
            albumsSection.classList.remove("active");
        }

        localStorage.setItem("musicBrowserTab", nextTarget);
    }

    toggleButtons.forEach(btn => {
        btn.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            switchView(btn.dataset.target);
        });
    });

    const defaultTab = isRadioStoriesPage ? "tracks" : "albums";
    const savedTabRaw = localStorage.getItem("musicBrowserTab");
    const savedTab =
        savedTabRaw === "albums" || savedTabRaw === "tracks"
            ? savedTabRaw
            : defaultTab;
    switchView(isRadioStoriesPage ? "tracks" : savedTab);

    window.addEventListener("orientationchange", () => {
        const savedTab = localStorage.getItem("musicBrowserTab");
        const nextTab =
            isRadioStoriesPage
                ? "tracks"
                : savedTab === "albums" || savedTab === "tracks"
                    ? savedTab
                    : defaultTab;
        setTimeout(() => {
            switchView(nextTab);
        }, 200);
    });
}

updateShuffleBtn();
updatePlayBtn("false");
ensureSelectedPrivateAlbum();
renderPrivateAlbumManager();

let initialAlbum = albums[0] || null;
const legacyAlbumName = localStorage.getItem("album") || "Vse";
if (!currentAlbumKey && legacyAlbumName) {
    initialAlbum = albums.find(album => album.name === legacyAlbumName) || initialAlbum;
    currentAlbumKey = getAlbumKey(initialAlbum);
}
if (currentAlbumKey) {
    initialAlbum = findAlbumByKey(currentAlbumKey) || initialAlbum;
}

if (initialAlbum) {
    loadAlbum(initialAlbum, { preserveCurrentTrackIfMissing: true });
    if (currentSongs.length > 0) {
        const initialIndex = currentSongs.includes(currentTrack)
            ? currentSongs.indexOf(currentTrack)
            : currentIndex >= 0
                ? currentIndex
                : 0;
        playTrack(initialIndex);
    }
} else {
    resetNowPlayingState();
}

if (searchInput) {
    searchInput.addEventListener("input", filterSongs);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeBrowserToggle);
} else {
    initializeBrowserToggle();
}

window.addEventListener("load", () => {
    setTimeout(() => {
        initializeBrowserToggle();
    }, 100);
});
