from imdb import Cinemagoer
import os
import requests
import json
from google.cloud import translate_v2 as translate
import html
import subprocess
from PIL import Image
import re
from difflib import SequenceMatcher
import logging
from langdetect import detect

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials/gen-lang-client.json"
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
        params["year"] = year

    data = tmdb_get("/search/movie", params)
    results = data.get("results", [])
    if results:
        return results
    data = tmdb_get("/search/movie", params, lang="en-US")
    return data.get("results", [])

def best_tmdb_match(query, results):
    best, score = None, 0
    for r in results:
        title = r.get("title", "")
        s = SequenceMatcher(None, query.lower(), title.lower()).ratio()
        if s > score:
            best, score = r, s
    return best, score

def tmdb_movie_details(tmdb_id):
    # 1. Pridobi slovenske podatke
    data_sl = tmdb_get(f"/movie/{tmdb_id}", lang="sl-SI")
    
    # Preverimo, če imamo opis in poster
    has_overview = bool(data_sl.get("overview"))
    has_poster = bool(data_sl.get("poster_path"))
    
    # Če imamo vse, vrnemo slovenske podatke
    if has_overview and has_poster:
        return data_sl

    # 2. Če kaj manjka, pridobimo angleške podatke
    try:
        data_en = tmdb_get(f"/movie/{tmdb_id}", lang="en-US")
    except Exception:
        # Če angleški klic ne uspe, vrnemo kar imamo (SL)
        return data_sl

    # 3. Združevanje (Merge):
    # Osnova je slovenski objekt (da ohranimo slovenski naslov, če obstaja)
    merged_data = data_sl.copy()

    # Če manjka slovenski opis, vzemi angleškega
    if not has_overview:
        merged_data["overview"] = data_en.get("overview", "")
    
    # Če manjka slovenski naslov (redko, a mogoče), vzemi angleškega ali originalnega
    if not merged_data.get("title"):
        merged_data["title"] = data_en.get("title", data_en.get("original_title"))

    # Če manjka pot do slike v slovenščini, vzemi angleško
    if not has_poster:
        merged_data["poster_path"] = data_en.get("poster_path")
        
    # Če manjkajo žanri v slovenščini (včasih se zgodi), vzemi angleške
    if not merged_data.get("genres"):
        merged_data["genres"] = data_en.get("genres", [])

    return merged_data

def tmdb_poster_url(poster_path, size="w500"):
    if not poster_path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{poster_path}"

def tmdb_cast(tmdb_id, limit=7):
    # Igralci se redko razlikujejo glede na jezik, a vseeno:
    data = tmdb_get(f"/movie/{tmdb_id}/credits")
    cast = data.get("cast", [])
    
    # Če je seznam prazen, poskusi EN (čeprav TMDB običajno vrne igralce ne glede na jezik)
    if not cast:
        data = tmdb_get(f"/movie/{tmdb_id}/credits", lang="en-US")
        cast = data.get("cast", [])
        
    return [p["name"] for p in cast[:limit]]

def get_imdb_id_from_tmdb(tmdb_id):
    imdb_id = tmdb_get(f"/movie/{tmdb_id}/external_ids").get("imdb_id")
    if imdb_id is None:
        imdb_id = tmdb_get(f"/movie/{tmdb_id}/external_ids", lang="en-US").get("imdb_id")
    return imdb_id


translate_client = translate.Client()

def translate_text(text, target_language="sl"):
    if not text:
        return ""

    result = translate_client.translate(text, target_language=target_language)
    return result["translatedText"]  # TODO: previdno uporabi za opise, lahko je drago

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


ia = Cinemagoer()

def namesInList(nameList):
    names = ''
    if nameList is None:
        return ''
    for i in nameList[:3]:
        names = names + '; ' + str(i.get('name'))
    return names[2:]

def get_movie_runtimes(folder, video_files):
    runtimes = []
    for video_file in video_files:
        path = os.path.join(folder, video_file)
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True
            )
            duration = int(round(float(result.stdout.strip()) / 60))
            runtimes.append(duration)
        except Exception as e:
            logging.error(f"{path} — napaka: {e}")
            runtimes.append(None)
    return runtimes


def get_movie_metadata(folder, film, video_files):
    film_readme_file = os.path.join(folder, 'readme.json')
    film_cover_file = os.path.join(folder, 'cover_image.jpg')

    if os.path.exists(film_readme_file):
        with open(film_readme_file, 'r', encoding="utf-8") as f:
            movie_metadata = json.loads(f.read()) 
        return movie_metadata, film_cover_file

    if "Collection" in folder:
        logging.error("Missing data for collection: " + film)
        return {}, "static/logo.png"

    result = {"Film": film}
    film_aux = re.sub(r'\b(19|20)\d{2}\b', '', film.replace("Collection", ""))
    film_aux = re.sub(r'\s+', ' ', film_aux).strip()
    match = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', film)
    if match:
        year = int(match.group(1))
    else:
        year = None
    
    search = tmdb_search_movie(film_aux, year=year)
    if len(search) == 0:
        logging.error(f"Missing data for: {film} ({film_aux}, {year})")
        return {}, "static/logo.png"
    movie, score = best_tmdb_match(film_aux, search)
    if movie is None:
        return {}, "static/logo.png"
    logging.info(f"{film}, {score}")
    details = tmdb_movie_details(movie["id"])
    cover_url = tmdb_poster_url(details["poster_path"])

    result["Title"] = details.get("title")
    result["OriginalTitle"] = details.get("original_title")
    result["Year"] = details.get("release_date", "")[:4]
    result["Plot"] = details.get("overview", "")
    result["Genres"] = [g["name"] for g in details.get("genres", [])]
    result["Runtimes"] = details.get("runtime")
    result["Players"] = tmdb_cast(details["id"])
    result["imdb_id"] = get_imdb_id_from_tmdb(details["id"])

    if result["Plot"] and detect(result["Plot"]) != "sl":
        result["Plot - translated"] = translate_text(result.get("Plot", ""))

    if cover_url:
        img_data = requests.get(cover_url).content
        with open(film_cover_file, 'wb') as handler:
            handler.write(img_data)
    else:
        logging.error("Missing cover image for: " + film)
        film_cover_file = "static/logo.png"


    runtimes = get_movie_runtimes(folder, video_files)
    result["RuntimesByFiles"] = {file: runtime for file, runtime in zip(video_files, runtimes)}
    runtime = None
    if len(runtimes) > 1:
        valid_r = [r for r in runtimes if r]
        if valid_r:
            runtime = f"{len(runtimes)} delov po {min(valid_r)}-{max(valid_r)}"
    elif len(runtimes) == 1:
        if runtimes[0]:
            runtime = runtimes[0]
    else:
        logging.error(f"{folder} has no videos.")

    if runtime:
        result["Runtimes"] = runtime
    
    with open(film_readme_file, 'w', encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)           
            
    return result, film_cover_file

class MovieMetadata:
    def __init__(self, folder):
        film_name = os.path.basename(folder)
    
        self.folder = folder
        film_name = (
            film_name.split(".SLOS")[0].split(".SLOs")[0].split(".SLoS")[0]
            .split(".SloS")[0].split(".EngS")[0].split(".ENGS")[0].split(".CROS")[0]
            .replace(".", " ").replace("-", " "))
        self.video_files = sorted([
            os.path.basename(f) 
            for f in os.listdir(folder) if f.split(".")[-1] in {"avi", "mp4", "mkv", "vob"}])
        self.subtitles = [
            os.path.basename(f) 
            for f in os.listdir(folder) if f.split(".")[-1] == "vtt"]
        self.slosinh = "sinh" in os.path.basename(folder).lower()

        metadata, cover = get_movie_metadata(folder, film_name, self.video_files)

        self.cover = cover
        self.thumbnail = create_thumbnail(cover)
        self.film_name = metadata.get("Film", film_name)
        self.title = metadata.get("Title", film_name)
        self.original_title = metadata.get("OriginalTitle", "")
        self.genres = metadata.get("Genres", [])
        self.year = metadata.get("Year", "")
        self.runtimes = metadata.get("Runtimes", "")
        self.runtimes_by_files = metadata.get("RuntimesByFiles", {})
        self.players = metadata.get("Players", "")
        if isinstance(self.players, list):
            self.players = "; ".join(self.players)
        self.plot = html.unescape(metadata.get("Plot - translated", metadata.get("Plot", "")))
        self.imdb_id = metadata.get("imdb_id", "")
