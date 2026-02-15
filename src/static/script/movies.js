function odstraniMovieCard(event, form) {
    if (!confirm('Ali res želiš izbrisati vse datoteke v mapi?')) {
        return false;
    }
    event.preventDefault();
    // Najdi najbližji parent z class "movie-card"
    const card = form.closest('.movie-card');
    const token = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    fetch(form.action, { method: 'POST',
        headers: {
            'X-CSRFToken': token
        } })
        .then(resp => resp.json())
        .then(data => console.log('Film odstranjen', data))
        .catch(err => console.error(err));
    if (card) {
        card.remove(); // odstrani iz DOM
    }

    return false; 
}

let currentPage = 0;
let loading = false;

// CSRF token
const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

// Glavni container
const grid = document.getElementById("movie-grid");

function attachHover(card) {
    const desc = card.querySelector('.description');
    if (!desc) return;

    card.addEventListener('mouseenter', () => {
        if (window.innerWidth < 700) {
            return;
        }
        // Najprej ponastavi pozicijo
        desc.style.left = '100%';
        desc.style.right = 'auto';
        desc.style.top = '0';

        // Pokaži začasno, da lahko izmerimo velikost
        desc.style.opacity = '1';
        desc.style.pointerEvents = 'auto';

        const rect = desc.getBoundingClientRect();
        const overflowRight = rect.right > window.innerWidth;
        const overflowBottom = rect.bottom > window.innerHeight;

        // Če gre izven desnega roba, pokaži levo
        if (overflowRight) {
            desc.style.left = 'auto';
            desc.style.right = '100%';
        }

        // Če gre izven spodnjega roba, prestavi opis navzgor
        if (overflowBottom) {
            const shift = rect.bottom - window.innerHeight + 10; // nekaj dodatnega prostora
            desc.style.top = `-${shift}px`;
        }

        const rect_new = desc.getBoundingClientRect();
        const overflowLeft = rect_new.left < 0;

        // Če gre izven levega roba, zozaj
        if (overflowLeft) {
            desc.style.width = `${rect_new.right - 5}px`;
        }
    });

    card.addEventListener('mouseleave', () => {
        desc.style.opacity = '0';
        desc.style.pointerEvents = 'none';
        desc.style.top = '0';
    });
}


async function loadNextPage() {
    if (loading) return;
    loading = true;

    const response = await fetch(`/movies/page?page=${currentPage}`);
    const data = await response.json();

    data.movies.forEach(movie => {
        const card = renderMovieCard(movie);
        grid.appendChild(card);
        attachHover(card);
    });

    if (data.has_more) {
        currentPage += 1;
        loading = false;
    }
}

function renderMovieCard(movie) {
    const wrapper = document.createElement("div");
    wrapper.className = `movie-card ${movie.movie_id} ${movie.recommendation_level}`;
    wrapper.style = `--watch: ${movie.watch_ratio}%;`;

    wrapper.innerHTML = `
        <a href="/movies/play${movie.folder}">
            <img src="/movies/file${movie.thumbnail}" alt="Poster" loading="lazy">
        </a>

        <h3><b>${movie.title}</b>${movie.year}<br><i class="original-title">${movie.original_title}</i>
            <div class="slosinh">${movie.slosinh}</div>
        </h3>

        <div class="genres">
            ${movie.genres.map(g => `
                <span class="genre-badge ${g.toLowerCase().replace(/ /g, '-')}">${g}</span>
            `).join('')}
        </div>

        <div class="description">
            <b>${movie.players}</b><br>
            <hr>${movie.description}

            <br><hr>

            <div class="selectors izbira" movie-id="${movie.movie_id}">
                <input type="radio" id="opcija1-${movie.movie_id}" name="izbor-${movie.movie_id}" value="0">
                <label for="opcija1-${movie.movie_id}">Nepogledano</label>

                <input type="radio" id="opcija2-${movie.movie_id}" name="izbor-${movie.movie_id}" value="100">
                <label for="opcija2-${movie.movie_id}">Pogledano</label>
            </div>
            ${movie.is_admin ? `
            <hr><div class="selectors priporocilo" movie-folder="${movie.folder}">
                <input type="radio" id="priporocilo1-${movie.movie_id}" name="priporocaj-${movie.movie_id}" value="">
                <label for="priporocilo1-${movie.movie_id}">Odstrani priporočilo</label>
                <input type="radio" id="priporocilo2-${movie.movie_id}" name="priporocaj-${movie.movie_id}" value="recommend">
                <label for="priporocilo2-${movie.movie_id}">Priporoči</label>
                <input type="radio" id="priporocilo3-${movie.movie_id}" name="priporocaj-${movie.movie_id}" value="warm-recommend">
                <label for="priporocilo3-${movie.movie_id}">Toplo priporoči</label>
            </div>` : ""}
        </div>

        <div class="buttons">
            <button class="runtime">${movie.runtimes} min</button>${movie.is_admin ? `
            <form action="/movies/remove${movie.folder}" method="post" onsubmit="return odstraniMovieCard(event, this);">
                <input type="hidden" name="csrf_token" value="${csrfToken}">
                <button type="submit">Odstrani</button>
            </form>
            ` : ""}
        </div>
    `;

    return wrapper;
}

if (grid) {
    // Infinite scroll trigger
    window.addEventListener("scroll", () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 100) {
            loadNextPage();
        }
    });

    // Zaženi prvo nalaganje
    loadNextPage();
}

document.addEventListener("change", (e) => {
    if (e.target.matches('.selectors.izbira input[type="radio"]')) {

        const radio = e.target;
        const skupina = radio.closest(".selectors.izbira");
        const movieId = skupina.getAttribute("movie-id");
        const izbor = radio.value;

        const token = document.querySelector('meta[name="csrf-token"]').content;

        fetch("/movies/progress-change", {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': token
            },
            body: JSON.stringify({ izbor, movieId })
        });

        document.querySelectorAll('.' + movieId).forEach(el => {
            el.style.setProperty('--watch', izbor + '%');
        });
    } else if ((e.target.matches('.selectors.priporocilo input[type="radio"]'))) {

        const radio = e.target;
        const skupina = radio.closest(".selectors.priporocilo");
        const movieFolder = skupina.getAttribute("movie-folder");
        const recommendation_level = radio.value;

        const token = document.querySelector('meta[name="csrf-token"]').content;

        fetch("/movies/recommend", {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': token
            },
            body: JSON.stringify({ recommendation_level, movieFolder })
        });

    }
});

document.addEventListener("DOMContentLoaded", function () {
    const onlyunwatched_checkbox = document.getElementById("onlyunwatched");
    const onlyunwatched_label = document.getElementById("onlyunwatchedlabel");
    if (!onlyunwatched_checkbox) return;

    onlyunwatched_label.innerHTML = onlyunwatched_checkbox.checked ? "Prikaži pogledano" : "Skrij pogledano"

    onlyunwatched_checkbox.addEventListener("change", function () {
        onlyunwatched_label.innerHTML = onlyunwatched_checkbox.checked ? "Prikaži pogledano" : "Skrij pogledano"
    });

    const onlyrecommended_checkbox = document.getElementById("onlyrecommended");
    const onlyrecommended_label = document.getElementById("onlyrecommendedlabel");
    if (!onlyrecommended_checkbox) return;

    onlyrecommended_label.innerHTML = onlyrecommended_checkbox.checked ? "Tudi brez priporočil" : "Samo priporočeni"

    // ko uporabnik klikne, shrani
    onlyrecommended_checkbox.addEventListener("change", function () {
        onlyrecommended_label.innerHTML = onlyrecommended_checkbox.checked ? "Tudi brez priporočil" : "Samo priporočeni"
    });
});

document.addEventListener('DOMContentLoaded', function() {
  const filterForm = document.querySelector('form');
  if (!filterForm) return;

  filterForm.addEventListener('submit', function(e) {
    e.preventDefault();
    
    const formData = new FormData(this);
    const params = new URLSearchParams();
    
    // Handle all form fields
    formData.forEach((value, key) => {
      params.append(key, value);
    });
    
    // Handle checkboxes - ensure unchecked ones are included with "off" value
    const checkboxes = this.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
      if (!params.has(checkbox.name)) {
        params.append(checkbox.name, 'off');
      }
    });
    
    console.log('Filter params:', params.toString()); // Debug
    
    // Build new URL and navigate
    const baseUrl = this.getAttribute('action') || window.location.pathname;
    window.location.href = baseUrl + '?' + params.toString();
  });
});

document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("videoPlayer");
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
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    setInterval(() => {
            if (video && !video.paused && !video.ended) {
                fetch("/movies/video-progress", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        filename: video.currentSrc,
                        currentTime: video.currentTime,
                        duration: video.duration
                    })
                }).catch(() => {});
                const selectedButton = document.querySelector('.video-btn.selected');
                if (selectedButton) {
                    selectedButton.style.setProperty('--watch', Math.round(video.currentTime / video.duration * 100) + '%');
                }
            }
        }, intervalMillis);
});


function submitComment(event, movieFolder) {
    event.preventDefault();
    
    const commentText = document.getElementById('commentText').value;
    const statusDiv = document.getElementById('commentStatus');
    
    const data = {
        movieFolder: movieFolder,
        comment: commentText,
        comment_type: "komentar na film"
    };
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    fetch('/movies/add-comment', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            "X-CSRFToken": csrfToken
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.status === 'success') {
            statusDiv.className = 'status-message success';
            statusDiv.textContent = 'Hvala! Vaš komentar je bil poslan. Administrator bo kmalu odgovoril.';
            document.getElementById('commentForm').reset();
            
            // Počisti status po 5 sekundah
            setTimeout(() => {
                statusDiv.textContent = '';
                statusDiv.className = 'status-message';
            }, 5000);
        } else {
            statusDiv.className = 'status-message error';
            statusDiv.textContent = 'Napaka: ' + result.message;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        statusDiv.className = 'status-message error';
        statusDiv.textContent = 'Napaka pri pošiljanju komentarja. Poskusite ponovno.';
    });
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
        modal.innerHTML = `
            <div class="rating-modal-inner">
                <h3>Oceni film</h3>
                <div class="rating-row"><label>Koliko bi priporočali ogled?</label> <span class="stars" data-name="would-watch">${[1,2,3,4,5].map(i=>`<span class="star" data-value="${i}"><i class="bi bi-star-fill"></i></span>`).join('')}</span></div>
                <div class="rating-row"><label>Prisotni prizori nasilja:</label> <span class="stars" data-name="violence">${[1,2,3,4,5].map(i=>`<span class="star" data-value="${i}"><i class="bi bi-exclamation-triangle-fill"></i></span>`).join('')}</span></div>
                <div class="rating-row"><label>Prisotni prizori spolnosti:</label> <span class="stars" data-name="sexual">${[1,2,3,4,5].map(i=>`<span class="star" data-value="${i}"><i class="bi bi-exclamation-triangle-fill"></i></span>`).join('')}</span></div>
                <div class="rating-row"><label>Primerno starostni skupini:</label> <span class="age-options" data-name="age_group">${[3,6,10,14,18].map(v=>`<span class="age-option" data-value="${v}">+${v}</span>`).join('')}</span></div>
                <div class="rating-row"><label>Kvaliteta videa:</label> <span class="stars" data-name="video_quality">${[1,2,3,4,5].map(i=>`<span class="star" data-value="${i}"><i class="bi bi-film"></i></span>`).join('')}</span></div>
                <div class="rating-row"><label>Kvaliteta podnapisov:</label> <span class="stars" data-name="subtitles_quality">${[1,2,3,4,5].map(i=>`<span class="star" data-value="${i}"><i class="bi bi-chat-dots-fill"></i></span>`).join('')}</span></div>
                <div class="rating-actions">
                    <button id="ratingSkip">Preskoči</button>
                    <button id="ratingSubmit">Pošlji oceno</button>
                </div>
            </div>`;
        document.body.appendChild(modal);

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
    }

    // Expose function to open modal from templates
    window.openRatingModal = function() {
        showRatingModal();
    };

    function hideRatingModal() {
        const m = document.getElementById('ratingModal');
        if (m) m.style.display = 'none';
        ratingNeeded = false;
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
        if (json.status !== 'success') throw 'error';
        // update summary on page
        if (json.summary) {
            document.getElementById('violence-avg').textContent = json.summary.violence.avg;
            document.getElementById('violence-count').textContent = json.summary.violence.count;
            document.getElementById('sexual-avg').textContent = json.summary.sexual.avg;
            document.getElementById('sexual-count').textContent = json.summary.sexual.count;
            document.getElementById('age-avg').textContent = json.summary.age_group.avg;
            document.getElementById('age-count').textContent = json.summary.age_group.count;
            if (json.summary.would_watch_again) {
                document.getElementById('would-watch-avg').textContent = json.summary.would_watch_again.avg;
                document.getElementById('would-watch-again-count').textContent = json.summary.would_watch_again.count;
            }
            if (json.summary.video_quality) {
                document.getElementById('video-quality-count').textContent = json.summary.video_quality.count;
            }
            if (json.summary.subtitles_quality) {
                document.getElementById('subtitles-quality-count').textContent = json.summary.subtitles_quality.count;
            }
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const video = document.getElementById('videoPlayer');
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
