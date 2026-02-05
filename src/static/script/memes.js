
function izbrisiMeme(meme_file_name) {
    const token = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    if (confirm("Res želiš izbrisati ta meme?")) {
        fetch(`/memes/delete/` + meme_file_name, {
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
    window.location.reload();
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
