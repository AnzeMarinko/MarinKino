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
    removeAttribute(name) { delete this[name]; }
    getAttribute(name) { return this[name] ?? null; }
}

function createPlayer({ radio = true, mode = "random", nativeHls = false, apple = false } = {}) {
    class Audio extends Element {
        paused = true;
        currentTime = 0;
        duration = 120;
        volume = 1;
        playCount = 0;

        get currentSrc() { return this.src || ""; }
        canPlayType() { return nativeHls ? "probably" : ""; }
        load() { this.currentTime = 0; }
        pause() { this.paused = true; this.dispatch("pause"); }
        play() {
            this.paused = false;
            this.playCount += 1;
            this.dispatch("play");
            return Promise.resolve();
        }
    }

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
        tracks.map(id => [id, { file_path: id, hls_path: `${id}/index.m3u8` }]),
    ));
    const storage = new Map([["musicPlaybackMode", mode]]);
    const requests = [];
    const cover = new Element();
    let frameTime = 0;
    const context = vm.createContext({
        console,
        Audio,
        document: {
            readyState: "loading",
            hidden: false,
            getElementById: id => elements.get(id) || null,
            querySelector: selector => selector === ".album-cover" ? cover : null,
            querySelectorAll: () => [],
            createElement: () => new Element(),
            addEventListener() {},
        },
        window: {
            IS_RADIO_STORIES_PAGE: radio,
            MEDIA_FILE_BASE: radio ? "/radio-stories/file/" : "/music/file/",
            MEDIA_HLS_BASE: radio ? "/radio-stories/hls/" : "/music/hls/",
            addEventListener() {},
        },
        navigator: { userAgent: apple ? "iPhone" : "test", platform: "", maxTouchPoints: 0 },
        localStorage: {
            getItem: key => storage.get(key) ?? null,
            setItem: (key, value) => storage.set(key, String(value)),
            removeItem: key => storage.delete(key),
        },
        fetch: async (url, options) => {
            requests.push({ url, options });
            return { ok: false, json: async () => ({}) };
        },
        // Cosmetic delays and music's early-transition interval stay inactive.
        setTimeout: () => 1,
        clearTimeout() {},
        setInterval: () => 1,
        clearInterval() {},
        performance: { now: () => frameTime },
        requestAnimationFrame: callback => queueMicrotask(() => {
            frameTime += 500;
            callback(frameTime);
        }),
    });
    vm.runInContext(playerSource, context, { filename: "music_player.js" });
    return {
        audio, storage, requests,
        run: expression => vm.runInContext(expression, context),
        flush: () => new Promise(resolve => setImmediate(resolve)),
        end() {
            audio.paused = true;
            audio.currentTime = audio.duration;
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
