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
        if (((localStorage.getItem("onlyunwatched") !== "true") | (movie.watch_ratio < 100)) & ((localStorage.getItem("onlyrecommended") !== "true") | (movie.recommendation_level != ""))) {
            const card = renderMovieCard(movie);
            grid.appendChild(card);
            attachHover(card);
        }
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

        <h3><b>${movie.title}</b>${movie.year}<br><i style="opacity: 0.5;">${movie.original_title}</i>
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

    // preberi shranjeno vrednost
    const onlyunwatched_saved = localStorage.getItem("onlyunwatched");

    if (onlyunwatched_saved !== null) {
        onlyunwatched_checkbox.checked = onlyunwatched_saved === "true";
    }
    onlyunwatched_label.innerHTML = onlyunwatched_checkbox.checked ? "Prikaži pogledano" : "Skrij pogledano"

    // ko uporabnik klikne, shrani
    onlyunwatched_checkbox.addEventListener("change", function () {
        onlyunwatched_label.innerHTML = onlyunwatched_checkbox.checked ? "Prikaži pogledano" : "Skrij pogledano"
        localStorage.setItem("onlyunwatched", onlyunwatched_checkbox.checked);
    });

    const onlyrecommended_checkbox = document.getElementById("onlyrecommended");
    const onlyrecommended_label = document.getElementById("onlyrecommendedlabel");
    if (!onlyrecommended_checkbox) return;

    // preberi shranjeno vrednost
    const onlyrecommended_saved = localStorage.getItem("onlyrecommended");

    if (onlyrecommended_saved !== null) {
        onlyrecommended_checkbox.checked = onlyrecommended_saved === "true";
    }
    onlyrecommended_label.innerHTML = onlyrecommended_checkbox.checked ? "Tudi brez priporočil" : "Samo priporočeni"

    // ko uporabnik klikne, shrani
    onlyrecommended_checkbox.addEventListener("change", function () {
        onlyrecommended_label.innerHTML = onlyrecommended_checkbox.checked ? "Tudi brez priporočil" : "Samo priporočeni"
        localStorage.setItem("onlyrecommended", onlyrecommended_checkbox.checked);
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
