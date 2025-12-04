import os
from .config import FILMS_ROOT

def shortened(s):
    return s.split('subtitles-')[-1].replace('.srt', '')

GENRES_MAPPING = {
    "Comedy": "Komedija",
    "Drama": "Drama",
    "Romance": "Romanca",
    "Adventure": "Pustolovski",
    "Family": "Druzinski",
    "Action": "Akcija",
    "Fantasy": "Domisljijski",
}
    

def prepare_html(films_metadata):
    filmi = {}
    counter = {}
    for film_metadata in films_metadata:
        genre_html = ""
        sinh =  'Sinhroniziran' if film_metadata.slosinh else ""

        for g in film_metadata.genres:
            g_repr = GENRES_MAPPING.get(g, g)
            aux_g = g_repr.lower().replace(" ", "-") if g_repr in GENRES_MAPPING.values() else "unknown"
            genre_html += f'<span class="genre-badge {aux_g}">{g_repr}</span>'

        slosubs_file = ""
        for subs in film_metadata.subtitles:
            if "slo" in subs.lower():
                slosubs_file = os.path.join(film_metadata.folder.replace(FILMS_ROOT, "movies"), subs)  

        movie_html = ""
        for video in film_metadata.video_files:
            video_f = os.path.join(film_metadata.folder.replace(FILMS_ROOT, "movies"), video)
            movie_html += f'<button data-src="{video_f}" data-sub="{slosubs_file}">{video}</button>'

        html_item = ('<div class="movie-card">'
                f'<img src="{film_metadata.cover}" alt="Poster" loading="lazy">'
                f'<h3>{film_metadata.title} ({film_metadata.year})<div class="slosinh">{sinh}</div></h3>'
                f'<div class="genres">{genre_html}</div>'
                f'<div class="description">'
                    f'<b>{film_metadata.players}</b></br>'
                    f'<hr>{film_metadata.plot_2}</br>'
                    f'<hr>{film_metadata.plot_1}</br>'
                    f'<hr>{film_metadata.runtimes} min</br>'
                    f'<hr><i>{film_metadata.folder.replace(FILMS_ROOT, "")}</i></br>'
                    f'<hr>{movie_html}'
                '</div>'
            '</div>')
        mapa = film_metadata.folder.replace(FILMS_ROOT, "").split(os.sep)[1]
        filmi[mapa] = filmi.get(mapa, "") + html_item
        counter[mapa] = counter.get(mapa, 0) + 1

    tabs = ""
    seznami = ""
    for k in sorted(filmi.keys()):
        name = k[3:].replace("-", " ").title() + f" ({counter[k]})"
        tabs += f"<li><a href='#{k}'>{name}</a></li>"
        seznami += f'<h2 id="{k}">{name}</h2><div class="movie-grid" id="{k}">{filmi[k]}</div>'

    with open("templates/user-interface-template.html", 'r', encoding="utf-8") as f:
        out_hml = f.read().format(tabs, seznami)
    with open("user-interface.html", 'w', encoding="utf-8") as f:
        f.write(out_hml)
