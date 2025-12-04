
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

// Poišči vse gumbe
document.querySelectorAll('#filmList button').forEach(btn => {
btn.addEventListener('click', () => {
    const videoSrc = btn.getAttribute('data-src');
    const subSrc = btn.getAttribute('data-sub');
    history.pushState("", document.title, window.location.pathname + window.location.search);

    document.getElementById('videoSource').src = videoSrc;
    document.getElementById('subtitleTrack').src = subSrc;

    const player = document.getElementById('player');
    player.load();
    player.play();

    // Prikaži video pogled, skrij seznam
    document.getElementById('filmList').style.display = 'none';
    document.getElementById('playerView').style.display = 'block';
});
});


function closePlayer() {
    const player = document.getElementById('player');
    player.pause();
    player.currentTime = 0;

    document.getElementById('playerView').style.display = 'none';
    document.getElementById('filmList').style.display = 'block';
}

let lastScroll = 0;
const header = document.querySelector("header");
const headerHeight = header.offsetHeight - 50;

function onScroll() {
    const currentScroll = window.pageYOffset || document.documentElement.scrollTop;

    if (currentScroll > lastScroll) {
        // scroll down
        header.style.top = `-${headerHeight}px`;
    } else {
        // scroll up
        header.style.top = "0";
    }
    
    lastScroll = currentScroll <= 0 ? 0 : currentScroll;
}

window.addEventListener("scroll", onScroll, { passive: true });
window.addEventListener("touchmove", onScroll, { passive: true }); // za mobilne naprave

document.querySelectorAll('.izbira').forEach((skupina) => {
    const movieId = skupina.getAttribute('movie-id');
    const radios = skupina.querySelectorAll('input[type="radio"]');

    radios.forEach(radio => {
      radio.addEventListener('change', () => {
        // Pripravi podatke za pošiljanje
        const izbor = radio.value;

        fetch("/progress-change", {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ izbor: izbor, movieId: movieId })
        })
        document.querySelectorAll('.' + movieId).forEach(el => {
            el.style.setProperty('--watch', izbor + '%');
            });
      });
    });
  });
