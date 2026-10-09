import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const playerSource = readFileSync(
    new URL("../src/static/script/music_player.js", import.meta.url),
    "utf8",
);
const tracks = ["third.mp3", "first.mp3", "second.mp3"];

class Element {
    constructor() {
        this.dataset = {};
        this.style = { setProperty() {} };
        this.children = [];
        this.listeners = new Map();
        this.classes = new Set();
        this.classList = {
            add: name => this.classes.add(name),
            remove: name => this.classes.delete(name),
            contains: name => this.classes.has(name),
            toggle: (name, enabled) => enabled
                ? this.classes.add(name)
                : this.classes.delete(name),
        };
    }

    addEventListener(name, listener) {
        const listeners = this.listeners.get(name) || [];
        this.listeners.set(name, [...listeners, listener]);
    }

    dispatch(name) {
        this[`on${name}`]?.();
        for (const listener of this.listeners.get(name) || []) listener();
    }

    appendChild(child) { this.children.push(child); }
    set innerHTML(value) { this.html = value; this.children = []; }
    get innerHTML() { return this.html; }
    set className(value) { this.classes = new Set(value.split(" ")); }
    get className() { return [...this.classes].join(" "); }
    scrollIntoView() { this.scrollCount = (this.scrollCount || 0) + 1; }
    removeAttribute(name) { delete this[name]; }
    getAttribute(name) { return this[name] ?? null; }
}

function createPlayer({
    radio = true, mode = "random", nativeHls = false, apple = false,
    hidden = false, session = false, unsupportedAction = null,
    fetchSession = null, fetchRecommendation = null,
} = {}) {
    class Audio extends Element {
        paused = true;
        time = 0;
        duration = 120;
        volume = 1;
        playCount = 0;
        loadCount = 0;
        pauseCount = 0;
        ended = false;

        get currentTime() { return this.time; }
        set currentTime(value) { this.time = value; this.ended = false; }
        get currentSrc() { return this.src || ""; }
        canPlayType() { return nativeHls ? "probably" : ""; }
        load() {
            this.loadCount += 1;
            this.currentTime = 0;
            this.duration = sessionDurations.get(this.src) || 120;
        }
        pause() { this.paused = true; this.pauseCount += 1; this.dispatch("pause"); }
        fastSeek(value) { this.lastFastSeek = value; this.currentTime = value; }
        play() {
            this.paused = false;
            this.playCount += 1;
            this.dispatch("play");
            return Promise.resolve();
        }
    }

    const sessionDurations = new Map();
    const audio = new Audio();
    const elements = new Map([
        "albums-root", "metadata-root", "trackList", "nowPlayingTitle",
        "nowPlayingArtist", "nowPlayingAlbum", "seekBar", "timeDisplay",
        "playbackModeBtn", "playbackModeIcon", "playBtn", "playIcon",
    ].map(id => [id, new Element()]));
    elements.set("audio", audio);
    elements.get("albums-root").dataset.albums = JSON.stringify([
        { name: "Vse", songs: tracks },
    ]);
    elements.get("metadata-root").dataset.music = JSON.stringify(Object.fromEntries(
        tracks.map(id => [id, {
            title: `Title ${id}`, artist: `Artist ${id}`, album: "Artist - Album",
            file_path: id, hls_path: `${id}/index.m3u8`,
        }]),
    ));
    const storage = new Map([["musicPlaybackMode", mode]]);
    const requests = [];
    const cover = new Element();
    let frameTime = 0;
    const document = Object.assign(new Element(), {
        readyState: "loading",
        hidden,
        getElementById: id => elements.get(id) || null,
        querySelector: selector => selector === ".album-cover"
            ? cover
            : selector === ".track-item.active"
                ? elements.get("trackList").children.find(child => child.classes.has("active")) || null
                : null,
        querySelectorAll: selector => selector === ".track-item"
            ? elements.get("trackList").children
            : [],
        createElement: () => new Element(),
    });
    const mediaSession = {
        actions: new Map(),
        setActionHandler(action, handler) {
            if (action === unsupportedAction) throw new Error("Unsupported action");
            this.actions.set(action, handler);
        },
        setPositionState(state) { this.position = state; },
    };
    const context = vm.createContext({
        console,
        Audio,
        document,
        window: {
            IS_RADIO_STORIES_PAGE: radio,
            MEDIA_FILE_BASE: radio ? "/radio-stories/file/" : "/music/file/",
            MEDIA_HLS_BASE: radio ? "/radio-stories/hls/" : "/music/hls/",
            addEventListener() {},
        },
        navigator: {
            userAgent: apple ? "iPhone" : "test", platform: "", maxTouchPoints: 0,
            mediaSession,
        },
        MediaMetadata: class { constructor(value) { Object.assign(this, value); } },
        localStorage: {
            getItem: key => storage.get(key) ?? null,
            setItem: (key, value) => storage.set(key, String(value)),
            removeItem: key => storage.delete(key),
        },
        fetch: async (url, options) => {
            requests.push({ url, options });
            if (fetchRecommendation && url === "/music/recommendation/next") {
                const payload = await fetchRecommendation(JSON.parse(options.body));
                return { ok: true, json: async () => payload };
            }
            if (session && url === "/music/session-playlist") {
                const body = JSON.parse(options.body);
                const response = fetchSession
                    ? await fetchSession(body)
                    : {
                        url: `/music/session-hls/test-${requests.length}.m3u8`,
                        tracks: body.track_ids.map(id => ({ id, duration: 120 })),
                    };
                sessionDurations.set(response.url, response.tracks.reduce((sum, track) => sum + track.duration, 0));
                return { ok: true, json: async () => response };
            }
            return { ok: false, json: async () => ({}) };
        },
        // Cosmetic delays and music's early-transition interval stay inactive.
        setTimeout: () => 1,
        clearTimeout() {},
        setInterval: () => 1,
        clearInterval() {},
        performance: { now: () => frameTime },
        requestAnimationFrame: callback => {
            if (!document.hidden) queueMicrotask(() => {
                frameTime += 500;
                callback(frameTime);
            });
        },
    });
    vm.runInContext(playerSource, context, { filename: "music_player.js" });
    return {
        audio, storage, requests, document, elements, mediaSession,
        run: expression => vm.runInContext(expression, context),
        flush: () => new Promise(resolve => setImmediate(resolve)),
        end() {
            audio.paused = true;
            audio.currentTime = audio.duration;
            audio.ended = true;
            audio.dispatch("ended");
        },
    };
}

for (const mode of ["random", "similar", "repeat"]) {
    test(`radio ignores stored ${mode}; next and ended follow list without wrapping`, async () => {
        const player = createPlayer({ mode });
        assert.equal(player.run("playbackMode"), "sequential");
        player.run(`setPlaybackMode(${JSON.stringify(mode)})`);
        assert.equal(player.run("playbackMode"), "sequential");
        assert.equal(player.storage.get("musicPlaybackMode"), mode);

        player.run("next()");
        await player.flush();
        assert.equal(player.run("currentTrack"), tracks[1]);
        player.end();
        await player.flush();
        assert.equal(player.run("currentTrack"), tracks[2]);
        const playCount = player.audio.playCount;
        player.end();
        player.run("next()");
        assert.equal(player.run("playbackIntent"), false);
        await player.run("resumePlaybackIfNeeded()");
        await player.flush();
        assert.equal(player.run("currentTrack"), tracks[2]);
        assert.equal(player.audio.playCount, playCount);
        assert.equal(player.audio.paused, true);
        assert.deepEqual(player.requests, []);
    });
}

test("duplicate ended events during source loading do not skip a radio programme", async () => {
    const player = createPlayer();
    player.end();
    player.audio.dispatch("ended");
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[1]);
    assert.equal(player.audio.playCount, 1);
    player.end();
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[2]);
});

test("replaying the final radio programme still stops when it ends again", async () => {
    const player = createPlayer();
    await player.run("playTrack(2)");
    await player.flush();
    player.end();
    assert.equal(player.run("playbackIntent"), false);

    player.run("togglePlay()");
    await player.flush();
    assert.equal(player.audio.playCount, 2);
    assert.equal(player.run("playbackIntent"), true);
    player.end();
    assert.equal(player.run("playbackIntent"), false);
    await player.run("resumePlaybackIfNeeded()");
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[2]);
    assert.equal(player.audio.playCount, 2);
    assert.equal(player.audio.paused, true);
});

for (const mode of ["sequential", "random", "similar", "repeat"]) {
    test(`music still restores and changes stored ${mode} mode`, () => {
        const player = createPlayer({ radio: false, mode });
        assert.equal(player.run("playbackMode"), mode);
        const nextMode = mode === "random" ? "repeat" : "random";
        player.run(`setPlaybackMode(${JSON.stringify(nextMode)})`);
        assert.equal(player.run("playbackMode"), nextMode);
        assert.equal(player.storage.get("musicPlaybackMode"), nextMode);
    });
}

for (const capabilities of [{ nativeHls: true }, { apple: true }]) {
    test(`radio manual play avoids music session endpoint with ${JSON.stringify(capabilities)}`, async () => {
        const player = createPlayer(capabilities);
        await player.run("playTrack(1)");
        await player.flush();
        assert.equal(player.run("currentTrack"), tracks[1]);
        assert.equal(player.audio.playCount, 1);
        assert.equal(player.audio.src, capabilities.nativeHls
            ? "/radio-stories/hls/first.mp3/index.m3u8"
            : "/radio-stories/file/first.mp3");
        assert.equal(player.run("isHlsSessionPlayback"), false);
        assert.deepEqual(player.requests, []);
    });
}

const iphone = { radio: false, mode: "sequential", nativeHls: true, apple: true, session: true };

test("lock-screen next keeps native session playing and updates title and highlight synchronously", async () => {
    const player = createPlayer(iphone);
    await player.run("playTrack(0)");
    await player.flush();
    const { src, loadCount, pauseCount, playCount } = player.audio;
    player.document.hidden = true;
    player.mediaSession.actions.get("nexttrack")();
    await player.flush();

    assert.equal(player.run("currentTrack"), tracks[1]);
    assert.equal(player.audio.currentTime, 120);
    assert.equal(player.audio.src, src);
    assert.equal(player.audio.loadCount, loadCount);
    assert.equal(player.audio.pauseCount, pauseCount);
    assert.equal(player.audio.playCount, playCount);
    assert.equal(player.audio.paused, false);
    assert.equal(player.requests.length, 1);
    assert.equal(player.mediaSession.metadata.title, `Title ${tracks[1]}`);
    assert.equal(player.elements.get("nowPlayingTitle").textContent, `Title ${tracks[1]}`);
    assert.equal(player.elements.get("trackList").children.find(child => child.classes.has("active")).dataset.trackId, tracks[1]);
});

test("background native track boundaries update metadata and track-relative lock-screen position", async () => {
    const player = createPlayer({ ...iphone, hidden: true });
    await player.run("playTrack(0)");
    await player.flush();
    player.audio.currentTime = 252;
    player.audio.dispatch("timeupdate");
    assert.equal(player.run("currentTrack"), tracks[2]);
    assert.equal(player.storage.get("time"), "12");
    assert.equal(player.mediaSession.position.duration, 120);
    assert.equal(player.mediaSession.position.position, 12);
    assert.equal(player.elements.get("nowPlayingAlbum").textContent, "Album");
    assert.equal(player.elements.get("nowPlayingTitle").textContent, `Title ${tracks[2]}`);

    player.audio.currentTime = 360;
    player.audio.dispatch("timeupdate");
    assert.equal(player.run("hlsSessionTrackStart"), 240);
    assert.equal(player.storage.get("time"), "120");
    assert.equal(player.elements.get("timeDisplay").textContent, "2:00 / 2:00");
});

test("lock-screen seek, fast seek and previous use current track offsets", async () => {
    const player = createPlayer(iphone);
    await player.run("playTrack(0)");
    await player.flush();
    player.audio.currentTime = 140;
    player.audio.dispatch("timeupdate");
    const seek = player.mediaSession.actions.get("seekto");
    seek({ seekTime: 45 });
    assert.equal(player.audio.currentTime, 165);
    assert.equal(player.mediaSession.position.position, 45);
    seek({ seekTime: 2, fastSeek: true });
    assert.equal(player.audio.lastFastSeek, 122);
    player.run("prev()");
    assert.equal(player.audio.currentTime, 0);

    player.audio.currentTime = 260;
    player.audio.dispatch("timeupdate");
    player.run("prev()");
    assert.equal(player.audio.currentTime, 240);
    assert.equal(player.run("currentTrack"), tracks[2]);
});

test("sequential session starts at selected track without wrapping to earlier songs", async () => {
    const player = createPlayer(iphone);
    await player.run("playTrack(1)");
    await player.flush();
    assert.deepEqual(JSON.parse(player.requests[0].options.body).track_ids, tracks.slice(1));
    player.end();
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[2]);
    assert.equal(player.run("playbackIntent"), false);
    const playCount = player.audio.playCount;
    player.run("resumePlaybackIfNeeded()");
    await player.flush();
    assert.equal(player.audio.playCount, playCount);
});

test("short sequential session continues into next chunk and duplicate ended does not skip", async () => {
    const player = createPlayer({
        ...iphone,
        fetchSession: async body => ({
            url: `/music/session-hls/${body.track_ids[0]}.m3u8`,
            tracks: body.track_ids.slice(0, 1).map(id => ({ id, duration: 120 })),
        }),
    });
    await player.run("playTrack(0)");
    await player.flush();
    player.document.hidden = true;
    player.end();
    player.audio.dispatch("ended");
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[1]);
    assert.equal(player.run("isHlsSessionPlayback"), true);
    assert.equal(player.requests.length, 2);
    assert.equal(player.audio.paused, false);
});

for (const mode of ["random", "similar"]) {
    test(`${mode} next follows prepared order and session end resumes within native stream`, async () => {
        const player = createPlayer({
            ...iphone, mode,
            fetchSession: async body => ({
                url: `/music/session-hls/${body.track_ids[0]}.m3u8`,
                tracks: [body.track_ids[0], ...tracks.filter(id => id !== body.track_ids[0]).reverse()]
                    .map(id => ({ id, duration: 120 })),
            }),
        });
        await player.run("playTrack(0)");
        await player.flush();
        player.run("next()");
        await player.flush();
        assert.equal(player.run("currentTrack"), tracks[2]);
        assert.equal(player.requests.length, 1);
        const src = player.audio.src;
        player.end();
        await player.flush();
        assert.equal(player.requests.length, 1);
        assert.equal(player.audio.src, src);
        assert.equal(player.audio.paused, false);
        assert.equal(player.run("isHlsSessionPlayback"), true);
    });
}

test("mode changes preserve track position and explicit pause; repeat uses native loop", async () => {
    const player = createPlayer(iphone);
    await player.run("playTrack(0)");
    await player.flush();
    player.audio.currentTime = 147;
    player.audio.dispatch("timeupdate");
    player.run("togglePlay(); setPlaybackMode('repeat')");
    await player.flush();
    player.audio.dispatch("loadedmetadata");
    assert.equal(player.audio.currentTime, 27);
    assert.equal(player.run("currentTrack"), tracks[1]);
    assert.equal(player.audio.loop, true);
    assert.equal(player.audio.paused, true);
    assert.equal(player.run("isHlsSessionPlayback"), false);

    player.run("setPlaybackMode('random')");
    await player.flush();
    assert.equal(player.audio.loop, false);
    player.run("togglePlay()");
    await player.flush();
    player.audio.dispatch("loadedmetadata");
    assert.equal(player.audio.currentTime, 27);
    assert.equal(player.run("isHlsSessionPlayback"), true);
    assert.equal(player.audio.paused, false);
});

test("background source changes complete with animation frames suspended", async () => {
    const player = createPlayer({ radio: false, mode: "sequential", hidden: true });
    await player.run("playTrack(0)");
    await player.flush();
    await player.run("playTrack(1)");
    await player.flush();
    assert.equal(player.run("isLoadingTrack"), false);
    assert.equal(player.audio.playCount, 2);
    assert.equal(player.audio.volume, 1);
    assert.equal(player.elements.get("nowPlayingTitle").textContent, `Title ${tracks[1]}`);
});

test("unsupported Media Session action does not prevent playback or metadata updates", async () => {
    const player = createPlayer({ ...iphone, unsupportedAction: "seekto" });
    await player.run("playTrack(0)");
    await player.flush();
    assert.equal(player.audio.paused, false);
    assert.equal(player.mediaSession.metadata.title, `Title ${tracks[0]}`);
});

test("normal track list keeps playing song visible even when already in target private album", () => {
    const player = createPlayer({ radio: false });
    player.run(`privateAlbums = [{ id: 'target', songs: [currentTrack] }]; selectedPrivateAlbumId = 'target'`);
    assert.equal(player.run("getTrackIdsToDisplay(currentSongs).includes(currentTrack)"), true);
    player.run("isTrackSelectionMode = true");
    assert.equal(player.run("getTrackIdsToDisplay(currentSongs).includes(currentTrack)"), false);
});

test("browsing another or empty album preserves actual playing track and source", async () => {
    const player = createPlayer(iphone);
    await player.run("playTrack(0)");
    await player.flush();
    const src = player.audio.src;
    player.run("loadAlbum({ name: 'Other', songs: ['other.mp3'] })");
    assert.equal(player.run("currentTrack"), tracks[0]);
    assert.equal(player.run("currentIndex"), -1);
    player.run("loadAlbum({ name: 'Empty', songs: [] })");
    assert.equal(player.audio.src, src);
    assert.equal(player.audio.paused, false);
    assert.equal(player.elements.get("nowPlayingTitle").textContent, `Title ${tracks[0]}`);
});

test("late old session response cannot replace a newer track selection", async () => {
    let resolveFirst;
    let calls = 0;
    const player = createPlayer({
        ...iphone,
        fetchSession: body => {
            const response = {
                url: `/music/session-hls/${body.track_ids[0]}.m3u8`,
                tracks: body.track_ids.map(id => ({ id, duration: 120 })),
            };
            calls += 1;
            return calls === 1
                ? new Promise(resolve => { resolveFirst = () => resolve(response); })
                : Promise.resolve(response);
        },
    });
    const firstLoad = player.run("playTrack(0)");
    await player.run("playTrack(1, { automatic: true })");
    await player.flush();
    const src = player.audio.src;
    resolveFirst();
    await firstLoad;
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[1]);
    assert.equal(player.audio.src, src);
    assert.equal(player.mediaSession.metadata.title, `Title ${tracks[1]}`);
    assert.equal(player.run("isLoadingTrack"), false);
});

test("similar fallback uses sound and style when recommendation unavailable", async () => {
    const player = createPlayer({ radio: false, mode: "similar" });
    player.run(`
        musicMetadata[currentSongs[0]].audio_features = { tempo: .2, energy: .2, mood: .2, instruments: .2 };
        musicMetadata[currentSongs[1]].audio_features = { tempo: .21, energy: .21, mood: .21, instruments: .21 };
        musicMetadata[currentSongs[2]].audio_features = { tempo: .2, energy: .2, mood: .2, instruments: .2 };
        musicMetadata[currentSongs[0]].semantic_analysis = { tags: ['folk'] };
        musicMetadata[currentSongs[1]].semantic_analysis = { tags: ['Folk'] };
        musicMetadata[currentSongs[2]].semantic_analysis = { tags: ['metal'] };
        musicMetadata[currentSongs[0]].genre = 'Acoustic';
        musicMetadata[currentSongs[1]].genre = 'acoustic';
        musicMetadata[currentSongs[2]].genre = 'Metal';
        next();
    `);
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[1]);
    assert.equal(player.audio.paused, false);
});

test("similar session searches whole album without randomly dropping later candidates", async () => {
    const player = createPlayer({ ...iphone, mode: "similar" });
    await player.run(`
        currentSongs = Array.from({ length: 301 }, (_, index) => 'song-' + index);
        requestHlsSessionPlaylist(0);
    `);
    const request = JSON.parse(player.requests[0].options.body);
    assert.equal(request.track_ids.length, 301);
    assert.equal(request.track_ids[300], "song-300");
});

test("similar native loop and last-track next stay within prepared neighborhood", async () => {
    const player = createPlayer({ ...iphone, mode: "similar" });
    await player.run("playTrack(0)");
    await player.flush();
    assert.equal(player.audio.loop, true);
    const loadCount = player.audio.loadCount;
    const playCount = player.audio.playCount;
    player.document.hidden = true;
    player.audio.currentTime = 242;
    player.audio.dispatch("timeupdate");
    player.run("next()");
    await player.flush();
    assert.equal(player.run("currentTrack"), tracks[0]);
    assert.equal(player.audio.currentTime, 0);
    assert.equal(player.audio.loadCount, loadCount);
    assert.equal(player.audio.playCount, playCount);
    assert.equal(player.requests.length, 1);
    player.audio.currentTime = 3;
    player.audio.dispatch("timeupdate");
    assert.equal(player.mediaSession.position.position, 3);
});

for (const rejected of [false, true]) {
    test(`stale recommendation ${rejected ? 'failure' : 'response'} cannot replace newer similar choice`, async () => {
        let finishFirst;
        let calls = 0;
        const player = createPlayer({
            radio: false, mode: "similar",
            fetchRecommendation: () => {
                calls += 1;
                return calls === 1
                    ? new Promise((resolve, reject) => {
                        finishFirst = rejected
                            ? () => reject(new Error("Old request failed"))
                            : () => resolve({ song: { id: tracks[1] } });
                    })
                    : Promise.resolve({ song: { id: tracks[2] } });
            },
        });
        await player.run("playTrack(0)");
        await player.flush();
        await player.run("playTrack(1)");
        await player.flush();
        finishFirst();
        await player.flush();
        assert.equal(player.run("preloadedRecommendation.currentTrack"), tracks[1]);
        assert.equal(player.run("preloadedRecommendation.payload.song.id"), tracks[2]);
        player.run("next()");
        await player.flush();
        assert.equal(player.run("currentTrack"), tracks[2]);
    });
}
