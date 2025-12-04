import imdb  # IMDbPY
import os
import requests
import json
from google.cloud import translate_v2 as translate
import html
import subprocess
from PIL import Image

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials/gen-lang-client.json"

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

ia = imdb.IMDb()

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

    if os.path.exists(film_readme_file) and os.path.exists(film_cover_file):
        with open(film_readme_file, 'r', encoding="utf-8") as f:
            movie_metadata = json.loads(f.read()) 

        return movie_metadata, film_cover_file

    if "Collection" in folder:
        print("Missing data for collection: " + film)
        return {}, "popcorn.png"
    
    search = ia.search_movie(film)
    result = {"Film": film}

    if len(search) == 0:
        print("Missing data for: " + film)
        return {}, "popcorn.png"

    cover_url = None

    for i, mov in enumerate(search[:3]):
        movie = ia.get_movie(mov.movieID)
        
        result['Title'] = movie.get('title') if result.get('Title', None) == None else result['Title']
        result['Genres'] = movie.get('genres', "") if result.get('Genres', None) == None else result['Genres']
        result['Rating'] = movie.get('rating') if result.get('Rating', None) == None else result['Rating']
        result['Votes'] = movie.get('votes') if result.get('Votes', None) == None else result['Votes']
        result['Year'] = movie.get('year') if result.get('Year', None) == None else result['Year']
        result['Runtimes'] = int(movie.get('runtimes', ['0'])[0]) if result.get('Runtimes', None) == None else result['Runtimes']
        result['Players'] = namesInList(movie.get('cast')) if result.get('Players', None) == None else result['Players']
        result['Country'] = movie.get('countries', [''])[0] if result.get('Country', None) == None else result['Country']
        result['Language'] = movie.get('languages', [''])[0] if result.get('Language', None) == None else result['Language']
        result['Plot outline'] = movie.get('plot outline') if result.get('Plot outline', None) == None else result['Plot outline']
        result['Plot'] = movie.get('plot', [''])[0] if result.get('Plot', None) == None else result['Plot']
        result['Kind'] = movie.get('kind') if result.get('Kind', None) == None else result['Kind']
        cover_url = movie.get('cover url') if cover_url == None else cover_url

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
        self.plot_1 = html.unescape(metadata.get("Plot outline - translated", metadata.get("Plot outline", "")))
        self.plot_2 = html.unescape(metadata.get("Plot - translated", metadata.get("Plot", "")))

