const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
const grid = document.getElementById('movie-grid');
const movieStatus = document.getElementById('movies-status');
const moreMovies = document.getElementById('movies-more');
let currentPage = 1;
let loading = false;
let hasMore = false;
const escapeMovieText = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const moviePath = value => String(value || '').split('/').map(encodeURIComponent).join('/');
function movieFeedback(text) {
    let status = movieStatus || document.getElementById('movie-action-status');
    if (!status) {
        status = document.createElement('p');
        status.id = 'movie-action-status';
        status.setAttribute('role', 'status');
        document.querySelector('.movie-view-heading')?.append(status);
    }
    status.textContent = text;
}
async function odstraniMovieCard(event, form) {
    event.preventDefault();
    if (!confirm('Ali res želiš izbrisati vse datoteke tega filma?')) return false;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
        const response = await fetch(form.action, {method: 'POST', headers: {'X-CSRFToken': csrfToken}});
        const data = await response.json();
        if (!response.ok || data.status !== 'success') throw new Error();
        const card = form.closest('.movie-card');
        if (card) { card.remove(); movieFeedback('Film je odstranjen.'); }
        else window.location.href = '/movies';
    } catch { movieFeedback('Filma ni bilo mogoče odstraniti. Poskusi znova.'); }
    finally { button.disabled = false; }
    return false;
}
const movieHoverMedia = window.matchMedia('(min-width: 700px) and (hover: hover) and (pointer: fine)');
function attachMovieHover(card) {
    const details = card.querySelector('.movie-details');
    function show() {
        if (!movieHoverMedia.matches) return;
        details.open = true;
        const rect = card.getBoundingClientRect();
        const width = details.offsetWidth;
        const left = rect.right + width <= innerWidth - 12
            ? rect.width - 1
            : rect.left - width >= 12 ? 1 - width : 12 - rect.left;
        details.style.left = `${left}px`;
        const top = Math.max(12 - rect.top, Math.min(0, innerHeight - 12 - rect.top - details.offsetHeight));
        details.style.top = `${top}px`;
    }
    function hide() {
        if (movieHoverMedia.matches && !card.contains(document.activeElement) && !card.matches(':hover')) {
            details.open = false;
        }
    }
    card.addEventListener('mouseenter', show);
    card.addEventListener('mouseleave', hide);
    card.addEventListener('focusin', show);
    card.addEventListener('focusout', () => queueMicrotask(hide));
}
movieHoverMedia.addEventListener('change', () => {
    grid?.querySelectorAll('.movie-details').forEach(details => {
        details.open = false;
        details.style.removeProperty('left');
        details.style.removeProperty('top');
    });
});
function movieGenreClass(genre) {
    return String(genre).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-');
}
function renderMovieCard(movie) {
    const text = escapeMovieText;
    const wrapper = document.createElement('article');
    const recommendation = ['recommend', 'warm-recommend'].includes(movie.recommendation_level) ? movie.recommendation_level : '';
    const watched = Math.max(0, Math.min(100, Number(movie.watch_ratio) || 0));
    const id = String(movie.movie_id);
    wrapper.className = `movie-card ${recommendation}`;
    wrapper.dataset.movieId = id;
    wrapper.style.setProperty('--watch', `${watched}%`);
    const link = '/movies/play' + moviePath(movie.folder);
    wrapper.innerHTML = `
        <a class="movie-poster" href="${text(link)}" aria-label="Ogled: ${text(movie.title)}">
            <img src="/movies/file${text(moviePath(movie.thumbnail))}" alt="Plakat za ${text(movie.title)}" loading="lazy">
            ${recommendation ? `<span class="movie-recommendation">${recommendation === 'warm-recommend' ? '★ Toplo priporočamo' : '★ Priporočamo'}</span>` : ''}
        </a>
        <div class="movie-watch-progress" role="progressbar" aria-label="Napredek ogleda" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(watched)}"></div>
        <div class="movie-card-body"><div class="movie-meta"><span>${text(movie.year)}</span><span class="movie-runtime"><i class="bi bi-clock" aria-hidden="true"></i> ${text(movie.runtimes)} min</span></div>
        <h2><a href="${text(link)}">${text(movie.title)}</a></h2>
        <p class="original-title">${text(movie.original_title)}</p>
        ${movie.slosinh ? `<p class="slosinh"><i class="bi bi-volume-up-fill" aria-hidden="true"></i> ${text(movie.slosinh)}</p>` : ''}
        <div class="genres">${(movie.genres || []).map(g => `<span class="genre-badge ${movieGenreClass(g)}">${text(g)}</span>`).join('')}</div>
        <a class="movie-play" href="${text(link)}">${watched > 0 && watched < 100 ? 'Nadaljuj ogled' : 'Ogled filma'} <span aria-hidden="true">▶</span></a>
        <details class="movie-details"><summary>Opis in možnosti</summary>
            <p>${text(movie.description)}</p>${movie.players ? `<p><strong>Igrajo:</strong> ${text(movie.players)}</p>` : ''}
            <fieldset class="selectors izbira" movie-id="${text(id)}"><legend>Stanje ogleda</legend>
            ${[0,100].map(value => `<input type="radio" id="watch-${text(id)}-${value}" name="izbor-${text(id)}" value="${value}" ${watched === value ? 'checked' : ''}><label for="watch-${text(id)}-${value}">${value ? 'Pogledano' : 'Nepogledano'}</label>`).join('')}</fieldset>
            ${movie.is_admin ? `<fieldset class="selectors priporocilo" movie-folder="${text(movie.folder)}"><legend>Priporočilo</legend>${['','recommend','warm-recommend'].map((value,index) => `<input type="radio" id="recommend-${text(id)}-${index}" name="priporocaj-${text(id)}" value="${value}" ${recommendation === value ? 'checked' : ''}><label for="recommend-${text(id)}-${index}">${['Brez priporočila','Priporoči','Toplo priporoči'][index]}</label>`).join('')}</fieldset>
            <form action="/movies/remove${text(moviePath(movie.folder))}" method="post" onsubmit="odstraniMovieCard(event, this); return false;"><button class="movie-delete" type="submit">Odstrani film</button></form>` : ''}
        </details></div>`;
    wrapper.querySelectorAll('.selectors').forEach(group => group.dataset.savedValue = group.querySelector('input:checked')?.value);
    attachMovieHover(wrapper);
    return wrapper;
}
function appendMovies(movies, initial = false) {
    movies.forEach(movie => grid.append(renderMovieCard(initial ? {...movie, is_admin: grid.dataset.admin === 'true'} : movie)));
}
async function loadNextPage() {
    if (loading || !hasMore) return;
    loading = true;
    moreMovies.disabled = true;
    moreMovies.textContent = 'Nalagam …';
    grid.setAttribute('aria-busy', 'true');
    try {
        const response = await fetch(`/movies/page?page=${currentPage}`);
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (!Array.isArray(data.movies)) throw new Error();
        appendMovies(data.movies);
        hasMore = data.has_more;
        currentPage++;
        moreMovies.hidden = !hasMore;
        movieFeedback(`Prikazanih filmov: ${grid.children.length}${hasMore ? '' : ' · Vsi filmi so naloženi.'}`);
    } catch { movieFeedback('Nalaganje ni uspelo. Poskusi znova.'); }
    finally {
        loading = false;
        moreMovies.disabled = false;
        moreMovies.textContent = 'Naloži več filmov';
        grid.setAttribute('aria-busy', 'false');
    }
}
if (grid) {
    const initial = JSON.parse(document.getElementById('movies-initial').textContent);
    appendMovies(initial.movies, true);
    hasMore = initial.has_more;
    moreMovies.hidden = !hasMore;
    movieFeedback(initial.movies.length ? `Prikazanih filmov: ${grid.children.length}` : 'Ni filmov za izbrane pogoje. Poskusi drugačno iskanje ali ponastavi filtre.');
    moreMovies.addEventListener('click', loadNextPage);
}
document.addEventListener('change', async event => {
    const radio = event.target;
    const group = radio.closest('.selectors');
    if (!group || !radio.matches('input[type="radio"]')) return;
    const progress = group.classList.contains('izbira');
    if (!progress && !group.classList.contains('priporocilo')) return;
    const inputs = [...group.querySelectorAll('input')];
    const previous = group.dataset.savedValue;
    inputs.forEach(input => input.disabled = true);
    try {
        const response = await fetch(progress ? '/movies/progress-change' : '/movies/recommend', {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify(progress ? {izbor: radio.value, movieId: group.getAttribute('movie-id')} : {recommendation_level: radio.value, movieFolder: group.getAttribute('movie-folder')})
        });
        if (!response.ok || response.redirected) throw new Error();
        if (!progress && (await response.json()).status !== 'success') throw new Error();
        group.dataset.savedValue = radio.value;
        const card = group.closest('.movie-card');
        if (progress) {
            document.querySelectorAll('[data-movie-id]').forEach(element => {
                if (element.dataset.movieId !== group.getAttribute('movie-id')) return;
                element.style.setProperty('--watch', radio.value + '%');
                const bar = element.matches('.movie-watch-progress') ? element : element.querySelector('.movie-watch-progress');
                bar?.setAttribute('aria-valuenow', radio.value);
            });
        }
        if (progress && card) {
            card.querySelector('.movie-play').innerHTML = 'Ogled filma <span aria-hidden="true">▶</span>';
        }
        if (!progress && card) {
            card.classList.remove('recommend','warm-recommend');
            if (radio.value) card.classList.add(radio.value);
            card.querySelector('.movie-recommendation')?.remove();
            if (radio.value) {
                const badge = document.createElement('span');
                badge.className = 'movie-recommendation';
                badge.textContent = radio.value === 'warm-recommend' ? '★ Toplo priporočamo' : '★ Priporočamo';
                card.querySelector('.movie-poster').append(badge);
            }
        }
        movieFeedback('Sprememba shranjena.');
    } catch {
        inputs.forEach(input => input.checked = input.value === previous);
        movieFeedback('Spremembe ni bilo mogoče shraniti. Poskusi znova.');
    } finally { inputs.forEach(input => input.disabled = false); }
});
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.selectors').forEach(group => group.dataset.savedValue = group.querySelector('input:checked')?.value);
    document.getElementById('movieFilterForm')?.addEventListener('submit', function(event) {
        event.preventDefault();
        const params = new URLSearchParams(new FormData(this));
        this.querySelectorAll('input[type="checkbox"]').forEach(input => { if (!input.checked) params.set(input.name, 'off'); });
        window.location.href = '/movies?' + params;
    });
});
document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("videoPlayer") || document.getElementById("hlsVideoPlayer") || document.querySelector(".plyr-container video, .plyr video");
    if (!video) return;

    video.addEventListener("dblclick", () => {
        if (!document.fullscreenElement) {
            // Vklopi celozaslonski način
            if (video.requestFullscreen) {
                video.requestFullscreen();
            } else if (video.webkitRequestFullscreen) { // Safari
                video.webkitRequestFullscreen();
            } else if (video.msRequestFullscreen) { // IE11
                video.msRequestFullscreen();
            }
        } else {
            // Izhod iz celozaslonskega načina
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) { // Safari
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) { // IE11
                document.msExitFullscreen();
            }
        }
    });

    // Nastavi interval (v milisekundah)
    const intervalMillis = 20 * 1000;
    let csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    const refreshCsrfToken = async () => {
        try {
            const response = await fetch('/csrf-token');
            if (response.ok) {
                csrfToken = (await response.json()).csrf_token;
                document.querySelector('meta[name="csrf-token"]')
                    .setAttribute('content', csrfToken);
            }
        } catch (error) {
            console.error('[csrf] token refresh failed', error);
        }
    };
    setInterval(refreshCsrfToken, 25 * 60 * 1000);
    setInterval(() => {
        const currentVideo = document.getElementById("videoPlayer") || document.getElementById("hlsVideoPlayer") || document.querySelector(".plyr-container video, .plyr video");
        if (currentVideo && !currentVideo.paused && !currentVideo.ended) {
            let currentFilename = currentVideo.currentSrc;
            const isHlsPlayer = currentVideo.id === "hlsVideoPlayer" || currentFilename.endsWith('.ts') || currentFilename.includes('stream_');

            if (isHlsPlayer) {
                currentFilename = window.hlsVideoSrc || currentFilename;
            }

            if (!currentFilename) return;

            const progressData = {
                filename: currentFilename,
                currentTime: currentVideo.currentTime,
                duration: currentVideo.duration
            };

            const sendProgress = () => fetch("/movies/video-progress", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify(progressData)
            });
            sendProgress().then(async response => {
                if (response.status === 400) {
                    await refreshCsrfToken();
                    await sendProgress();
                }
            }).catch(error => {
                console.error("[movie-progress] request failed", error);
            });
            const selectedButton = document.querySelector('.video-btn.selected');
            if (selectedButton) {
                selectedButton.style.setProperty('--watch', Math.round(currentVideo.currentTime / currentVideo.duration * 100) + '%');
            }
        }
    }, intervalMillis);
});


async function submitComment(event, movieFolder) {
    event.preventDefault();
    const form = document.getElementById('commentForm');
    const button = form.querySelector('button[type="submit"]');
    if (button.disabled) return;
    const status = document.getElementById('commentStatus');
    button.disabled = true;
    status.textContent = 'Pošiljam …';
    try {
        const response = await fetch('/movies/add-comment', {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify({movieFolder, comment: document.getElementById('commentText').value, comment_type: 'komentar na film'})
        });
        const result = await response.json();
        if (!response.ok || result.status !== 'success') throw new Error(result.message || 'Komentarja ni bilo mogoče poslati. Poskusi znova.');
        status.className = 'status-message success';
        status.textContent = 'Hvala! Komentar je poslan skrbniku v pregled.';
        form.reset();
    } catch (error) {
        status.className = 'status-message error';
        status.textContent = error.message || 'Komentarja ni bilo mogoče poslati. Poskusi znova.';
    } finally { button.disabled = false; }
}

const ALERT_TYPES_PAGE = {
    "opozorilo": "bi-exclamation-diamond-fill",
    "ideja": "bi-lightbulb-fill",
};

function submitAlertOnPage(movieFolder) {
    const text = document.getElementById('alert_text').value.trim();
    const type = document.getElementById('alert_type').value;
    const icon = ALERT_TYPES_PAGE[type] || 'bi-lightbulb-fill';

    if (!text) {
        alert('Besedilo opozorila je obvezno');
        return;
    }

    const data = {
        movieFolder: movieFolder,
        text: text,
        type: type,
        icon: icon
    };

    fetch('/movies/add-warning', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            alert('Opozorilo je bilo dodano!');
            document.getElementById('alert_text').value = '';
            location.reload();
        } else {
            alert('Napaka: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Napaka pri dodajanju opozorila');
    });
}

let editingAlertData = {};

function editAlertOnPage(button, movieFolder, index) {
    const noteElement = button.closest('.user-note');
    const noteHeader = noteElement.querySelector('.note-header');
    const alertText = noteHeader.textContent.trim();
    const alertType = noteElement.className.match(/note-type-(\w+)/)?.[1] || 'opozorilo';

    editingAlertData = {
        movieFolder: movieFolder,
        index: index
    };

    document.getElementById('edit_alert_text').value = alertText;
    document.getElementById('edit_alert_type').value = alertType;
    document.getElementById('editAlertModal').style.display = 'block';
}

function closeEditAlertModal() {
    document.getElementById('editAlertModal').style.display = 'none';
    editingAlertData = {};
}

function saveEditedAlert() {
    const text = document.getElementById('edit_alert_text').value.trim();
    const type = document.getElementById('edit_alert_type').value;
    const ALERT_TYPES_PAGE = {
        "opozorilo": "bi-exclamation-diamond-fill",
        "ideja": "bi-lightbulb-fill"
    };
    const icon = ALERT_TYPES_PAGE[type] || 'bi-lightbulb-fill';

    if (!text) {
        alert('Besedilo opozorila je obvezno');
        return;
    }

    const data = {
        movieFolder: editingAlertData.movieFolder,
        warningIndex: editingAlertData.index,
        text: text,
        type: type,
        icon: icon
    };

    fetch('/movies/edit-warning', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            alert('Opozorilo je bilo shranjeno!');
            closeEditAlertModal();
            location.reload();
        } else {
            alert('Napaka: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Napaka pri shranjevanju opozorila');
    });
}

window.onclick = function(event) {
    const modal = document.getElementById('editAlertModal');
    if (event.target === modal) {
        closeEditAlertModal();
    }
}

function deleteAlertOnPage(button, movieFolder, index) {
    if (!confirm('Ali si prepričan, da želiš izbrisati to opozorilo?')) {
        return;
    }

    const data = {
        movieFolder: movieFolder,
        warningIndex: index
    };

    fetch('/movies/delete-warning', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            alert('Opozorilo je bilo izbrisano!');
            location.reload();
        } else {
            alert('Napaka: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Napaka pri brisanju opozorila');
    });
}

// ===== Rating prompt logic =====
(() => {
    let ratingNeeded = false;
    let ratingShown = false;
    let intendedNav = null;

    function createRatingModal() {
        if (document.getElementById('ratingModal')) return;
        const modal = document.createElement('div');
        modal.id = 'ratingModal';
        modal.style.display = 'none';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'rating-title');
        modal.innerHTML = `
            <div class="rating-modal-inner">
                <h3 id="rating-title">Oceni film</h3><p>Oceni le področja, ki jih želiš. Višja ocena pomeni večjo prisotnost ali boljšo kakovost.</p>
                <div class="rating-row"><label>Koliko bi priporočali ogled?</label> <span class="stars" data-name="would-watch">${[1,2,3,4,5].map(i=>`<button type="button" class="star" aria-label="${i} od 5" data-value="${i}"><i class="bi bi-star-fill"></i></button>`).join('')}</span></div>
                <div class="rating-row"><label>Prisotni prizori nasilja:</label> <span class="stars" data-name="violence">${[1,2,3,4,5].map(i=>`<button type="button" class="star" aria-label="${i} od 5" data-value="${i}"><i class="bi bi-exclamation-triangle-fill"></i></button>`).join('')}</span></div>
                <div class="rating-row"><label>Prisotni prizori spolnosti:</label> <span class="stars" data-name="sexual">${[1,2,3,4,5].map(i=>`<button type="button" class="star" aria-label="${i} od 5" data-value="${i}"><i class="bi bi-exclamation-triangle-fill"></i></button>`).join('')}</span></div>
                <div class="rating-row"><label>Primerno starostni skupini:</label> <span class="age-options" data-name="age_group">${[3,6,10,14,18].map(v=>`<button type="button" class="age-option" data-value="${v}">+${v}</button>`).join('')}</span></div>
                <div class="rating-row"><label>Kvaliteta videa:</label> <span class="stars" data-name="video_quality">${[1,2,3,4,5].map(i=>`<button type="button" class="star" aria-label="${i} od 5" data-value="${i}"><i class="bi bi-film"></i></button>`).join('')}</span></div>
                <div class="rating-row"><label>Kvaliteta podnapisov:</label> <span class="stars" data-name="subtitles_quality">${[1,2,3,4,5].map(i=>`<button type="button" class="star" aria-label="${i} od 5" data-value="${i}"><i class="bi bi-chat-dots-fill"></i></button>`).join('')}</span></div>
                <div class="rating-actions">
                    <button id="ratingSkip">Preskoči</button>
                    <button id="ratingSubmit">Pošlji oceno</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        modal.addEventListener('keydown', event => {
            if (event.key === 'Escape') { document.getElementById('ratingSkip').click(); return; }
            if (event.key !== 'Tab') return;
            const buttons = [...modal.querySelectorAll('button:not(:disabled)')];
            const first = buttons[0], last = buttons[buttons.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });

        document.getElementById('ratingSkip').addEventListener('click', () => {
            hideRatingModal();
            if (intendedNav) window.location = intendedNav;
        });

        document.getElementById('ratingSubmit').addEventListener('click', () => {
            submitRating().then(() => {
                hideRatingModal();
                if (intendedNav) window.location = intendedNav;
            }).catch(() => { alert('Napaka pri pošiljanju ocene'); });
        });

        // wire up stars
        modal.querySelectorAll('.stars').forEach(box => {
            box.querySelectorAll('.star').forEach(item => {
                item.addEventListener('click', () => {
                    const v = parseInt(item.getAttribute('data-value'));
                    box.querySelectorAll('.star').forEach(ei => {
                        const sv = parseInt(ei.getAttribute('data-value'));
                        if (sv <= v) ei.classList.add('selected'); else ei.classList.remove('selected');
                    });
                    box.setAttribute('data-selected', v);
                });
            });
        });

        // wire up age options (discrete choices)
        modal.querySelectorAll('.age-options').forEach(box => {
            box.querySelectorAll('.age-option').forEach(opt => {
                opt.addEventListener('click', () => {
                    box.querySelectorAll('.age-option').forEach(o => o.classList.remove('selected'));
                    opt.classList.add('selected');
                    box.setAttribute('data-selected', opt.getAttribute('data-value'));
                });
            });
        });
    }

    function showRatingModal() {
        createRatingModal();
        ratingShown = true;
        const m = document.getElementById('ratingModal');
        m.style.display = 'flex';
        m.querySelector('button').focus();
    }

    // Expose function to open modal from templates
    window.openRatingModal = function() {
        showRatingModal();
    };

    function hideRatingModal() {
        const m = document.getElementById('ratingModal');
        if (m) m.style.display = 'none';
        ratingNeeded = false;
        document.querySelector('[onclick="openRatingModal()"]')?.focus();
    }

    async function submitRating() {
        const movieFolder = document.getElementById('rating-summary')?.getAttribute('data-movie-folder');
        if (!movieFolder) throw 'no movie folder';
        const violence = parseInt(document.querySelector('.stars[data-name="violence"]')?.getAttribute('data-selected') || 0);
        const sexual = parseInt(document.querySelector('.stars[data-name="sexual"]')?.getAttribute('data-selected') || 0);
        const age_group = parseInt(document.querySelector('.age-options')?.getAttribute('data-selected') || 0);
        const would_watch_again = parseInt(document.querySelector('.stars[data-name="would-watch"]')?.getAttribute('data-selected') || 0);
        const video_quality = parseInt(document.querySelector('.stars[data-name="video_quality"]')?.getAttribute('data-selected') || 0);
        const subtitles_quality = parseInt(document.querySelector('.stars[data-name="subtitles_quality"]')?.getAttribute('data-selected') || 0);
        const token = document.querySelector('meta[name="csrf-token"]').content;

        const res = await fetch('/movies/rate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
            body: JSON.stringify({ movieFolder, violence, sexual, age_group, would_watch_again, video_quality, subtitles_quality })
        });
        const json = await res.json();
        if (!res.ok) throw new Error();
        if (json.status !== 'success') throw 'error';
        if (json.summary) {
            const metrics = {violence: 'violence', sexual: 'sexual', age_group: 'age', would_watch_again: 'would-watch-again', video_quality: 'video-quality', subtitles_quality: 'subtitles-quality'};
            Object.entries(metrics).forEach(([key, prefix]) => {
                const metric = json.summary[key];
                const count = document.getElementById(prefix + '-count');
                if (!metric || !count) return;
                count.textContent = metric.count;
                const icons = count.closest('div').querySelectorAll('.icons-base i');
                icons.forEach((icon, index) => {
                    const percent = Math.max(0, Math.min(1, Number(metric.avg) - index)) * 100;
                    icon.style.color = `color-mix(in srgb, var(--marinkino-orange) ${percent}%, #bfbfbf ${100 - percent}%)`;
                });
            });
            movieFeedback('Ocena je shranjena. Hvala!');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const video = document.getElementById("videoPlayer") || document.getElementById("hlsVideoPlayer");
        if (!video) return;

        // Check if this is a collection - if so, skip rating
        const ratingElement = document.getElementById('rating-summary');
        const isCollection = ratingElement && ratingElement.getAttribute('data-is-collection') === 'true';

        if (isCollection) return;

        video.addEventListener('timeupdate', () => {
            if (!video.duration) return;
            if (video.currentTime / video.duration > 0.8) {
                ratingNeeded = true;
            }
        });

        window.addEventListener('beforeunload', (e) => {
            if (ratingNeeded && !ratingShown) {
                // Try to show our modal, but as backup, browser will show default dialog
                // This prevents leaving without acknowledging
                e.preventDefault();
                e.returnValue = 'Želite oceniti film preden zapustite stran?';
                // Also try to show our modal
                setTimeout(() => {
                    if (!ratingShown) {
                        showRatingModal();
                    }
                }, 100);
            }
        });

        // Also handle page unload to catch direct URL navigation
        window.addEventListener('unload', () => {
            if (ratingNeeded && !ratingShown) {
                // Last attempt - this fires just before leaving
                navigator.sendBeacon('/api/user-left-without-rating', JSON.stringify({
                    movieFolder: document.getElementById('rating-summary')?.getAttribute('data-movie-folder')
                }));
            }
        });

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && ratingNeeded && !ratingShown) {
                showRatingModal();
            }
        });

        // intercept navigation links
        document.addEventListener('click', (e) => {
            const a = e.target.closest('a');
            if (a && ratingNeeded && !ratingShown) {
                e.preventDefault();
                intendedNav = a.href;
                showRatingModal();
            }
        });
    });
})();
