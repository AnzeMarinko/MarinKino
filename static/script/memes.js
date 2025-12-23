
let refreshing = true;
const refreshInterval = setInterval(() => {
    if (refreshing) {
        location.reload();
    }
}, 30 * 1000);

// Ustavi osvežitev ob interakciji
const container = document.getElementById('mediaContainer');
container.addEventListener('mousedown', () => refreshing = false);
container.addEventListener('touchstart', () => refreshing = false);

const video = document.getElementById('videoPlayer');
if (video) {
    video.addEventListener('playing', () => refreshing = false);
    video.addEventListener('pause', () => refreshing = true);
    video.addEventListener('ended', () => refreshing = true);
}

function izbrisiMeme(meme_file_name) {
    const token = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    if (confirm("Res želiš izbrisati ta meme?")) {
        fetch(`/meme/delete/` + meme_file_name, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': token
            }
        })
        .then(response => {
            if (response.ok) {
                pojdiNaNaslednjega();
            } else {
                alert("Napaka pri brisanju mema!");
            }
        });
    }
}

function pojdiNaNaslednjega() {
    window.location.href = "/meme";
}

function preklopiFullscreen() {
    const elem = document.documentElement;

    if (!document.fullscreenElement &&
        !document.webkitFullscreenElement &&
        !document.msFullscreenElement) {
        if (elem.requestFullscreen) {
            elem.requestFullscreen();
        } else if (elem.webkitRequestFullscreen) {
            elem.webkitRequestFullscreen();
        } else if (elem.msRequestFullscreen) {
            elem.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}

const nextBtn = document.getElementById('nextButton');
const mediaContainer = document.getElementById('mediaContainer');

// Prikaz gumbka samo, ko je miška/blizu sredine
function checkPosition(event) {
    const rect = mediaContainer.getBoundingClientRect();
    const x = event.clientX || (event.touches ? event.touches[0].clientX : 0);
    const y = event.clientY || (event.touches ? event.touches[0].clientY : 0);

    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    const distanceX = Math.abs(x - centerX);
    const distanceY = Math.abs(y - centerY);

    const toleranceX = rect.width * 0.25;  // 25% širine
    const toleranceY = rect.height * 0.25; // 25% višine

    if (distanceX < toleranceX && distanceY < toleranceY) {
        nextBtn.style.opacity = 1;
    } else {
        nextBtn.style.opacity = 0;
    }
}

// Za miško
mediaContainer.addEventListener('mousemove', checkPosition);
// Za mobilne naprave
mediaContainer.addEventListener('touchmove', checkPosition);

// Ob izhodu iz območja skrij gumb
mediaContainer.addEventListener('mouseleave', () => nextBtn.style.opacity = 0);
