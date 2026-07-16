import html
import json
import logging
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

import requests
from google.cloud import translate_v2 as translate
from langdetect import detect
from PIL import Image

log = logging.getLogger(__name__)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    "credentials/gen-lang-client.json"
)
TMDB_KEY = os.getenv("TMDB_KEY")
TMDB_URL = "https://api.themoviedb.org/3"


def tmdb_get(path, params=None, lang="sl-SI"):
    if params is None:
        params = {}
    params["api_key"] = TMDB_KEY
    params["language"] = lang
    r = requests.get(f"{TMDB_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def tmdb_search_movie(title, year=None):
    params = {"query": title}
    if year:
        # Multi search sprejme 'year' za filme in 'first_air_date_year'
        # za serije
        params["year"] = year
        params["first_air_date_year"] = year

    # 1. Poskusimo iskanje v primarnem jeziku
    data = tmdb_get("/search/multi", params)
    results = data.get("results", [])

    # Filtriramo, da odstranimo morebitne osebe (people) in
    # obdržimo le filme in serije
    valid_results = [
        r for r in results if r.get("media_type") in ("movie", "tv")
    ]
    if valid_results:
        return valid_results

    # 2. Če ni rezultatov, poskusimo še v angleščini
    data = tmdb_get("/search/multi", params, lang="en-US")
    results = data.get("results", [])
    return [r for r in results if r.get("media_type") in ("movie", "tv")]


def best_tmdb_match(query, results):
    best, score = None, 0
    for r in results:
        title = r.get("title", r.get("name", ""))
        s = SequenceMatcher(None, query.lower(), title.lower()).ratio()
        if s > score:
            best, score = r, s
    return best, score


def tmdb_get_by_imdb_id(imdb_id, lang="sl-SI"):
    """
    Poišče podatke o filmu ali seriji na TMDB s pomočjo IMDb ID-ja.
    Vrne podatke in tip medija ('movie' ali 'tv').
    """
    # IMDb ID se mora začeti s "tt" (npr. tt0944947)
    if not imdb_id.startswith("tt"):
        log.error(f"❌ Neveljaven IMDb ID format: {imdb_id}")
        return None

    params = {"external_source": "imdb_id"}

    # 1. Poskusimo najprej v primarnem jeziku (npr. slovenščina)
    data = tmdb_get(f"/find/{imdb_id}", params, lang=lang)

    # TMDB razvrsti rezultate v ločene sezname glede na tip medija
    movie_results = data.get("movie_results", [])
    tv_results = data.get("tv_results", [])

    # Če v našem jeziku nismo našli ničesar, poskusimo še v angleščini
    if not movie_results and not tv_results and lang != "en-US":
        data = tmdb_get(f"/find/{imdb_id}", params, lang="en-US")
        movie_results = data.get("movie_results", [])
        tv_results = data.get("tv_results", [])

    # 2. Obdelamo in vrnemo rezultat ter določimo 'media_type'
    if movie_results:
        result = movie_results[0]
        result["media_type"] = "movie"
        return result

    elif tv_results:
        result = tv_results[0]
        result["media_type"] = "tv"
        return result

    log.warning(f"⚠️ Na TMDB ni bilo mogoče najti ničesar z IMDb ID: {imdb_id}")
    return None


def tmdb_poster_url(poster_path, size="w500"):
    if not poster_path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{poster_path}"


def tmdb_movie_details(tmdb_id, media_type="movie"):
    """Pridobi podatke o filmu ali seriji in
    združi slovenske ter angleške opise."""
    endpoint = f"/{media_type}/{tmdb_id}"

    # 1. Pridobi slovenske podatke
    try:
        data_sl = tmdb_get(endpoint, lang="sl-SI")
    except Exception:
        data_sl = {}

    # Preverimo, če imamo opis in poster
    has_overview = bool(data_sl.get("overview"))
    has_poster = bool(data_sl.get("poster_path"))

    # Če imamo oboje v slovenščini, takoj vrnemo slovenske podatke
    if has_overview and has_poster:
        return data_sl

    # 2. Če kaj manjka, pridobimo angleške podatke
    try:
        data_en = tmdb_get(endpoint, lang="en-US")
    except Exception:
        # Če angleški klic ne uspe, vrnemo to kar imamo (SL)
        return data_sl

    # 3. Združevanje (Merge):
    merged_data = data_sl.copy() if data_sl else data_en.copy()

    # Če manjka slovenski opis, vzemi angleškega
    if not has_overview:
        merged_data["overview"] = data_en.get("overview", "")

    # Razlika v poimenovanju naslovov med filmom in serijo:
    title_key = "title" if media_type == "movie" else "name"
    orig_title_key = (
        "original_title" if media_type == "movie" else "original_name"
    )

    if not merged_data.get(title_key):
        merged_data[title_key] = data_en.get(
            title_key, data_en.get(orig_title_key, "")
        )

    # Če manjka pot do slike v slovenščini, vzemi angleško
    if not has_poster:
        merged_data["poster_path"] = data_en.get("poster_path")

    # Če manjkajo žanri, vzemi angleške
    if not merged_data.get("genres"):
        merged_data["genres"] = data_en.get("genres", [])

    return merged_data


def tmdb_cast(tmdb_id, media_type="movie", limit=7):
    """Pridobi igralce za filme ali serije."""
    endpoint = f"/{media_type}/{tmdb_id}/credits"
    try:
        data = tmdb_get(endpoint)
        cast = data.get("cast", [])
    except Exception:
        cast = []

    if not cast:
        try:
            data = tmdb_get(endpoint, lang="en-US")
            cast = data.get("cast", [])
        except Exception:
            cast = []

    return [p["name"] for p in cast[:limit]]


def get_imdb_id_from_tmdb(tmdb_id, media_type="movie"):
    """Pridobi IMDb ID iz TMDB ID glede na tip medija."""
    endpoint = f"/{media_type}/{tmdb_id}/external_ids"
    try:
        external_ids = tmdb_get(endpoint)
        imdb_id = external_ids.get("imdb_id")
    except Exception:
        imdb_id = None

    if not imdb_id:
        try:
            external_ids = tmdb_get(endpoint, lang="en-US")
            imdb_id = external_ids.get("imdb_id")
        except Exception:
            imdb_id = None

    return imdb_id


translate_client = translate.Client()


def translate_text(text, target_language="sl"):
    if not text:
        return ""

    result = translate_client.translate(text, target_language=target_language)
    return result[
        "translatedText"
    ]  # TODO: previdno uporabi za opise, lahko je drago


def create_thumbnail(src, height=250, quality=85):
    if "popcorn.png" in src:
        return src
    dst = src.replace("cover_image.jpg", "cover_thumb.jpg")
    if os.path.exists(dst):
        return dst
    img = Image.open(src)
    w, h = img.size
    ratio = height / float(h)
    new_width = int(w * ratio)

    if new_width < w:
        img = img.resize((new_width, height), Image.LANCZOS)

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    img.save(dst, "JPEG", quality=quality)
    return dst


def get_movie_runtimes(folder, video_files):
    runtimes = []
    for video_file in video_files:
        path = os.path.join(folder, video_file)
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
            )
            duration = int(round(float(result.stdout.strip()) / 60))
            runtimes.append(duration)
        except Exception as e:
            log.error(f"{path} — napaka: {e}")
            runtimes.append(None)
    return runtimes


def get_movie_metadata(folder, film, video_files):
    film_readme_file = os.path.join(folder, "readme.json")
    film_cover_file = os.path.join(folder, "cover_image.jpg")

    # Če readme.json že obstaja, samo posodobimo runtimes in ga preberemo
    if os.path.exists(film_readme_file):
        with open(film_readme_file, "r", encoding="utf-8") as f:
            movie_metadata = json.loads(f.read())
        return movie_metadata, film_cover_file

    result = {"Film": film}

    # Izločimo letnico iz imena mape za boljše iskanje
    film_aux = re.sub(r"\b(19|20)\d{2}\b", "", film.replace("Collection", ""))
    film_aux = re.sub(r"\s+", " ", film_aux).strip()

    match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", film)
    year = int(match.group(1)) if match else None

    log.info(f"Iščem na TMDB: '{film_aux}' (Leto: {year})")

    # 1. Poiščemo film ali serijo preko Multi Search
    search = tmdb_search_movie(film_aux, year=year)
    if len(search) == 0:
        log.error(f"Ni podatkov za: {film} ({film_aux}, {year})")
        return {}, "static/logo.png"

    movie_match, score = best_tmdb_match(film_aux, search)
    if movie_match is None:
        return {}, "static/logo.png"

    log.info(
        f"Najboljši zadetek: {movie_match.get('title', movie_match.get('name'))} (Ujemanje: {score})"  # noqa E501
    )

    # Pridobimo TMDB ID in tip medija ('movie' ali 'tv')
    tmdb_id = movie_match["id"]
    media_type = movie_match.get("media_type", "movie")

    # 2. Pridobimo podrobne podatke glede na to ali je film ali serija
    details = tmdb_movie_details(tmdb_id, media_type=media_type)
    cover_url = tmdb_poster_url(details.get("poster_path"))

    # Shranimo metapodatke (ločimo med ključi za filme in serije)
    result["Title"] = (
        details.get("title") if media_type == "movie" else details.get("name")
    )
    result["OriginalTitle"] = (
        details.get("original_title")
        if media_type == "movie"
        else details.get("original_name")
    )
    result["Year"] = (
        details.get("release_date", "")[:4]
        if media_type == "movie"
        else details.get("first_air_date", "")[:4]
    )
    result["Plot"] = details.get("overview", "")
    result["Genres"] = [g["name"] for g in details.get("genres", [])]
    result["Runtimes"] = (
        details.get("runtime")
        if media_type == "movie"
        else (
            details.get("episode_run_time", [None])[0]
            if details.get("episode_run_time")
            else None
        )
    )
    result["Players"] = tmdb_cast(tmdb_id, media_type=media_type)
    result["imdb_id"] = get_imdb_id_from_tmdb(tmdb_id, media_type=media_type)
    result["media_type"] = (
        media_type  # Shranimo tip medija za prihodnjo uporabo
    )

    # Prevajanje opisa v slovenščino, če je zaznana angleščina
    if result["Plot"] and detect(result["Plot"]) != "sl":
        result["Plot - translated"] = translate_text(result.get("Plot", ""))

    # 3. Prenos slike platnice
    if cover_url:
        try:
            img_data = requests.get(cover_url, timeout=10).content
            with open(film_cover_file, "wb") as handler:
                handler.write(img_data)
        except Exception as e:
            log.error(f"Napaka pri prenosu slike za {film}: {e}")
            film_cover_file = "static/logo.png"
    else:
        log.error("Ni slike platnice za: " + film)
        film_cover_file = "static/logo.png"

    # Dodajanje dolžin datotek
    runtimes = get_movie_runtimes(folder, video_files)
    result["RuntimesByFiles"] = {
        file.replace(".mp4", "")
        .replace("_Slo", "")
        .replace("_Eng", ""): runtime
        for file, runtime in zip(video_files, runtimes)
    }

    runtime = None
    if len(runtimes) > 1:
        valid_r = [r for r in runtimes if r]
        if valid_r:
            runtime = f"{len(runtimes)} delov po {min(valid_r)}-{max(valid_r)}"
    elif len(runtimes) == 1:
        if runtimes[0]:
            runtime = runtimes[0]
    else:
        log.error(f"{folder} nima video datotek.")

    if runtime:
        result["Runtimes"] = runtime

    # Shranimo nov readme.json
    with open(film_readme_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    return result, film_cover_file


class MovieMetadata:
    SUPPORTED_VIDEO = {".avi", ".mp4", ".mkv", ".vob"}

    def __init__(self, folder):
        self.folder = folder
        self.path = Path(folder)
        self.folder_str = str(folder)

        # Logične zastavice
        self.slosinh = "sinh" in self.path.name.lower()
        self.is_collection = ".collection" in self.path.name.lower()
        self.is_chosen_series = "the-chosen-series/" in folder

        # Očistimo ime filma
        # replace(".", " ") bi lahko pokvaril kratice, zato čistimo le ločila
        raw_name = self.path.name.replace(".", " ").replace("-", " ")
        self.title = " ".join(raw_name.split()).title()

        # Vsebino mape preberemo samo enkrat za večjo hitrost
        folder_contents = (
            list(self.path.iterdir()) if self.path.exists() else []
        )

        # Filtriranje datotek z uporabo pathlib suffixov (ki vključujejo piko)
        self.video_files = sorted(
            [
                f.name
                for f in folder_contents
                if f.is_file() and f.suffix.lower() in self.SUPPORTED_VIDEO
            ]
        )
        self.video_files_m3u8 = sorted(
            [str(f.relative_to(self.path)) for f in self.path.rglob("*.m3u8")]
        )

        self.subtitles = [
            f.name
            for f in folder_contents
            if f.is_file() and f.suffix.lower() == ".vtt"
        ]

        metadata, cover = get_movie_metadata(
            folder, self.title, self.video_files
        )

        self.cover = cover
        self.thumbnail = create_thumbnail(cover)
        self.film_name = metadata.get("Film", self.title)
        self.title = metadata.get("Title", self.title)
        self.original_title = metadata.get("OriginalTitle", "")
        self.genres = metadata.get("Genres", [])
        self.year = metadata.get("Year", "")
        self.runtimes = metadata.get("Runtimes", "")
        self.runtimes_by_files = metadata.get("RuntimesByFiles", {})
        self.players = metadata.get("Players", "")
        if isinstance(self.players, list):
            self.players = "; ".join(self.players)
        self.plot = html.unescape(
            metadata.get("Plot - translated", metadata.get("Plot", ""))
        )
        self.imdb_id = metadata.get("imdb_id", "")
        self.recommendation_level = metadata.get("recommendation_level", "")
        self.user_notes = metadata.get("user_notes", {})

        self.ratings = metadata.get("ratings", {})
