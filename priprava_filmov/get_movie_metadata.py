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

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials/gen-lang-client.json"
TMDB_KEY = os.getenv("TMDB_KEY")
TMDB_URL = "https://api.themoviedb.org/3"

def tmdb_get(path, params=None):
    if params is None:
        params = {}
    params["api_key"] = TMDB_KEY
    params["language"] = "en-US"
    r = requests.get(f"{TMDB_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def tmdb_search_movie(title, year=None):
    params = {"query": title}
    if year:
        params["year"] = year

    data = tmdb_get("/search/movie", params)

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
    return tmdb_get(f"/movie/{tmdb_id}")

def tmdb_poster_url(poster_path, size="w500"):
    if not poster_path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{poster_path}"

def tmdb_cast(tmdb_id, limit=10):
    data = tmdb_get(f"/movie/{tmdb_id}/credits")
    cast = data.get("cast", [])[:limit]
    return [p["name"] for p in cast]

def get_imdb_id_from_tmdb(tmdb_id):
    return tmdb_get(f"/movie/{tmdb_id}/external_ids").get("imdb_id")



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
            print(f"{path} — napaka: {e}")
            runtimes.append(None)
    return runtimes


def get_movie_metadata(folder, film, video_files):
    film_readme_file = os.path.join(folder, 'readme.json')
    film_cover_file = os.path.join(folder, 'cover_image.jpg')
    result = {"Film": film}
    film_aux = re.sub(r'\b(19|20)\d{2}\b', '', film)
    film_aux = re.sub(r'\s+', ' ', film_aux).strip()
    match = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)', film)
    if match:
        year = int(match.group(1))
    else:
        year = None

    if os.path.exists(film_readme_file):
        with open(film_readme_file, 'r', encoding="utf-8") as f:
            movie_metadata = json.loads(f.read()) 

        if os.path.exists(film_cover_file) and [k for k in movie_metadata.keys() if k not in ["Film", "Title"]]:
            if "07-" in folder and sorted(list(movie_metadata["RuntimesByFiles"].keys())) != sorted(list(video_files)):
                print(film)
                runtimes = get_movie_runtimes(folder, video_files)
                movie_metadata["RuntimesByFiles"] = {file: runtime for file, runtime in zip(video_files, runtimes)}
                with open(film_readme_file, 'w', encoding="utf-8") as f:
                    json.dump(movie_metadata, f, ensure_ascii=False, indent=4)    
            return movie_metadata, film_cover_file
        else:
            result = movie_metadata
            film_aux = movie_metadata["Film"]

    if "Collection" in folder:
        print("Missing data for collection: " + film)
        return {}, "popcorn.png"
    
    search = tmdb_search_movie(film_aux, year=year)
    if len(search) == 0:
        print("Missing data for: " + film)
        return {}, "popcorn.png"
    movie, score = best_tmdb_match(film_aux, search)
    print(film, score)
    details = tmdb_movie_details(movie["id"])
    cover_url = tmdb_poster_url(details["poster_path"])

    result["Title"] = details.get("title")
    result["Year"] = details.get("release_date", "")[:4]
    result["Rating"] = details.get("vote_average")
    result["Votes"] = details.get("vote_count")
    result["Plot"] = details.get("overview")
    result["Kind"] = "movie"
    result["Genres"] = [g["name"] for g in details.get("genres", [])]
    result["Runtimes"] = details.get("runtime")
    result["Players"] = tmdb_cast(details["id"])
    result["imdb_id"] = get_imdb_id_from_tmdb(details["id"])

    # country
    countries = details.get("production_countries", [])
    if countries:
        result["Country"] = countries[0]["name"]

    # language
    langs = details.get("spoken_languages", [])
    if langs:
        result["Language"] = langs[0]["english_name"]

    result["Plot outline - translated"] = translate_text(result.get("Plot outline", ""))
    result["Plot - translated"] = translate_text(result.get("Plot", ""))

    if cover_url:
        img_data = requests.get(cover_url).content
        with open(film_cover_file, 'wb') as handler:
            handler.write(img_data)
    else:
        print("Missing cover image for: " + film)

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
        print(f"{folder} has no videos.")

    if runtime:
        result["Runtimes"] = runtime
    
    with open(film_readme_file, 'w', encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)           
            
    return result, film_cover_file

def translate_plots(folder):
    print(f"Prevajam opis filma {folder}")
    film_readme_file = folder + '/readme.json'
    with open(film_readme_file, 'r', encoding="utf-8") as f:
        movie_metadata = json.loads(f.read())

    if movie_metadata.get("Plot outline - translated") == None:
        movie_metadata["Plot outline - translated"] = translate_text(movie_metadata.get("Plot outline", ""))
    if movie_metadata.get("Plot - translated") == None:
        movie_metadata["Plot - translated"] = translate_text(movie_metadata.get("Plot", ""))
    
    with open(film_readme_file, 'w', encoding="utf-8") as f:
        json.dump(movie_metadata, f, ensure_ascii=False, indent=4) 

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
        self.genres = metadata.get("Genres", [])
        self.year = metadata.get("Year", "")
        self.runtimes = metadata.get("Runtimes", "")
        self.runtimes_by_files = metadata.get("RuntimesByFiles", {})
        self.players = metadata.get("Players", "")
        if isinstance(self.players, list):
            self.players = "; ".join(self.players)
        self.plot_1 = html.unescape(metadata.get("Plot outline - translated", metadata.get("Plot outline", "")))
        self.plot_2 = html.unescape(metadata.get("Plot - translated", metadata.get("Plot", "")))

