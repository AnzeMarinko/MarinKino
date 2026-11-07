/* A collection keeps one media element; HLS instances belong to one episode. */
(() => {
    const container = document.getElementById('collectionPlayerContainer');
    if (!container) return;
    const video = container.querySelector('video');
    const notice = document.getElementById('chooseVideoNotice');
    const status = document.getElementById('collectionPlaybackStatus');
    const audio = document.getElementById('collectionAudio');
    const audioSelect = document.getElementById('collectionAudioSelect');
    let player;
    let hls;
    let episode;

    function showStatus(message) {
        status.textContent = message;
        status.hidden = !message;
    }

    function rememberPosition() {
        if (!episode || !Number.isFinite(video.duration) || video.duration <= 0) return;
        const complete = video.currentTime / video.duration > .9 || video.duration - video.currentTime < 30;
        const resume = complete ? 0 : video.currentTime;
        episode.button.dataset.resume = String(resume);
        episode.button.dataset.resumeSeconds = String(resume);
        episode.button.style.setProperty('--watch', `${complete ? 100 : Math.round(video.currentTime / video.duration * 100)}%`);
    }

    function destroyHls() {
        if (hls) hls.destroy();
        hls = null;
    }

    function updateAudioTracks() {
        const tracks = hls ? hls.audioTracks : Array.from(video.audioTracks || []);
        audioSelect.replaceChildren();
        audio.hidden = tracks.length < 2;
        tracks.forEach((track, index) => {
            const option = document.createElement('option');
            option.value = String(index);
            const language = (track.lang || track.language || '').toLowerCase();
            option.textContent = ['sl', 'slv', 'slo'].includes(language) ? 'Slovenščina' :
                ['en', 'eng'].includes(language) ? 'Angleščina' : track.name || track.label || language || `Zvok ${index + 1}`;
            option.selected = hls ? hls.audioTrack === index : track.enabled;
            audioSelect.appendChild(option);
        });
    }

    audioSelect.addEventListener('change', () => {
        const index = Number(audioSelect.value);
        if (hls) hls.audioTrack = index;
        else Array.from(video.audioTracks || []).forEach((track, number) => { track.enabled = number === index; });
    });
    video.audioTracks?.addEventListener('addtrack', updateAudioTracks);

    video.addEventListener('loadedmetadata', () => {
        if (!episode || episode.restored || !Number.isFinite(video.duration) || video.duration <= 0) return;
        episode.restored = true;
        if (episode.resume > 0 && episode.resume < video.duration) video.currentTime = episode.resume;
        showStatus('');
        updateAudioTracks();
        const current = episode;
        video.play()?.catch(error => {
            if (episode !== current || error.name === 'AbortError') return;
            showStatus(error.name === 'NotAllowedError' ? 'Za začetek pritisni Predvajaj.' : 'Predvajanje ni uspelo. Ponovno izberi epizodo.');
        });
    });
    video.addEventListener('error', () => {
        if (episode) showStatus('Videa ni mogoče predvajati. Ponovno izberi epizodo ali uporabi prenos.');
    });

    window.playVideo = (src, startTime = 0, button) => {
        rememberPosition();
        video.pause();
        destroyHls();
        video.removeAttribute('src');
        video.load();
        if (!player && window.Plyr) {
            player = new Plyr(video, {
                iconUrl: container.dataset.plyrIcons,
                blankVideo: container.dataset.blankVideo,
                ratio: '16:9',
                controls: ['play-large', 'rewind', 'play', 'fast-forward', 'progress', 'current-time', 'duration', 'volume', 'settings', 'fullscreen', 'download'],
                urls: {download: container.dataset.downloadUrl},
                keyboard: {focused: true, global: false},
            });
        }
        const resume = Number(button.dataset.resume);
        const current = {button, resume: Number.isFinite(resume) ? resume : startTime, restored: false};
        episode = current;
        document.querySelectorAll('.video-btn').forEach(item => {
            item.classList.toggle('selected', item === button);
            item.setAttribute('aria-pressed', String(item === button));
        });
        notice.hidden = true;
        container.style.display = 'block';
        audio.hidden = true;
        showStatus('Nalagam izbrano epizodo …');
        // MediaSource uses blob URLs, which cannot identify stored progress.
        video.dataset.progressSource = button.dataset.progressSource || src;
        if (button.dataset.hls === 'true' && window.Hls?.isSupported()) {
            const instance = new Hls({debug: false});
            hls = instance;
            instance.on(Hls.Events.AUDIO_TRACKS_UPDATED, updateAudioTracks);
            instance.on(Hls.Events.ERROR, (_event, data) => {
                if (data.fatal && episode === current) {
                    destroyHls();
                    showStatus('Epizode ni mogoče naložiti. Ponovno jo izberi ali uporabi prenos.');
                }
            });
            instance.loadSource(src);
            instance.attachMedia(video);
        } else if (button.dataset.hls !== 'true' || video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = src;
            video.load();
        } else {
            showStatus('Ta brskalnik ne podpira HLS. Poskusi drug brskalnik ali uporabi prenos.');
        }
    };
})();
