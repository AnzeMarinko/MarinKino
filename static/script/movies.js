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

function getGreeting() {
    const hour = new Date().getHours();

    if (hour < 5)      return "lahko noč";
    if (hour < 10)     return "dobro jutro";
    if (hour < 18)     return "dober dan";
    return "dober večer";
}

document.getElementById("greeting").textContent = getGreeting();

let currentPage = 0;
let loading = false;

// CSRF token
const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

// Glavni container
const grid = document.getElementById("movie-grid");

async function loadNextPage() {
    if (loading) return;
    loading = true;

    const response = await fetch(`/movies_page?page=${currentPage}`);
    const data = await response.json();

    data.movies.forEach(movie => {
        const card = renderMovieCard(movie);
        grid.appendChild(card);
    });

    if (data.has_more) {
        currentPage += 1;
        loading = false;
    }
}

// Render funkcija, ki ustvari DOM strukturo enako tvojemu Jinja templatu
function renderMovieCard(movie) {
    const wrapper = document.createElement("div");
    wrapper.className = `movie-card ${movie.movie_id}`;
    wrapper.style = `--watch: ${movie.watch_ratio}%;`;

    wrapper.innerHTML = `
        <a href="/play${movie.folder}">
            <img src="/movies${movie.thumbnail}" alt="Poster" loading="lazy">
        </a>

        <h3>${movie.title}${movie.year}
            <div class="slosinh">${movie.slosinh}</div>
        </h3>

        <div class="genres">
            ${movie.genres.map(g => `
                <span class="genre-badge ${g.toLowerCase().replace(/ /g, '-')}">${g}</span>
            `).join('')}
        </div>

        <div class="description">
            <b>${movie.players}</b><br>
            <hr>${movie.description}<br>
            <hr>${movie.description_2 || ""}

            ${movie.subtitle_buttons?.length ? `
                <br><hr>Podnapisi:
                ${movie.subtitle_buttons.map(s => `<button class="subtitles">${s}</button>`).join("")}
            ` : ""}

            <br><hr>

            <div class="izbira" movie-id="${movie.movie_id}">
                <input type="radio" id="opcija1-${movie.movie_id}" name="izbor-${movie.movie_id}" value="0">
                <label for="opcija1-${movie.movie_id}">Nepogledano</label>

                <input type="radio" id="opcija2-${movie.movie_id}" name="izbor-${movie.movie_id}" value="100">
                <label for="opcija2-${movie.movie_id}">Pogledano</label>
            </div>
        </div>

        <div class="buttons">
            <button class="runtime">${movie.runtimes} min</button>${movie.is_admin ? `
            <form action="/remove${movie.folder}" method="post" onsubmit="return odstraniMovieCard(event, this);">
                <input type="hidden" name="csrf_token" value="${csrfToken}">
                <button type="submit">Odstrani</button>
            </form>
            ` : ""}
        </div>
    `;

    return wrapper;
}

// Infinite scroll trigger
window.addEventListener("scroll", () => {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 100) {
        loadNextPage();
    }
});

// Zaženi prvo nalaganje
loadNextPage();

document.addEventListener("change", (e) => {
    if (e.target.matches('.izbira input[type="radio"]')) {

        const radio = e.target;
        const skupina = radio.closest(".izbira");
        const movieId = skupina.getAttribute("movie-id");
        const izbor = radio.value;

        const token = document.querySelector('meta[name="csrf-token"]').content;

        fetch("/progress-change", {
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
    }
});

document.querySelectorAll('.movie-card').forEach(card => {
    const desc = card.querySelector('.description');

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
    });

    card.addEventListener('mouseleave', () => {
        desc.style.opacity = '0';
        desc.style.pointerEvents = 'none';
        desc.style.top = '0';
    });
});
