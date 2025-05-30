import imdb  # IMDbPY
import os
import requests
import json
from google.cloud import translate_v2 as translate
import html

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials/gen-lang-client.json"

translate_client = translate.Client()

def translate_text(text, target_language="sl"):
    if not text:
        return ""

    result = translate_client.translate(text, target_language=target_language)
    return result["translatedText"]  # TODO: previdno uporabi za opise, lahko je drago

ia = imdb.IMDb()

def namesInList(nameList):
    names = ''
    if nameList is None:
        return ''
    for i in nameList[:3]:
        names = names + '; ' + str(i.get('name'))
    return names[2:]


def get_movie_metadata(folder, film):
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
    
        film_name = (
            film_name.split(".SLOS")[0].split(".SLOs")[0].split(".SLoS")[0]
            .split(".SloS")[0].split(".EngS")[0].split(".ENGS")[0].split(".CROS")[0]
            .replace(".", " ").replace("-", " "))

        metadata, cover = get_movie_metadata(folder, film_name)

        self.folder = folder
        self.cover = cover
        self.film_name = metadata.get("Film", film_name)
        self.title = metadata.get("Title", film_name)
        self.genres = metadata.get("Genres", [])
        self.year = metadata.get("Year", "")
        self.runtimes = metadata.get("Runtimes", "")
        self.players = metadata.get("Players", "")
        self.plot_1 = html.unescape(metadata.get("Plot outline - translated", metadata.get("Plot outline", "")))
        self.plot_2 = html.unescape(metadata.get("Plot - translated", metadata.get("Plot", "")))
        self.video_files = sorted([
            os.path.basename(f) 
            for f in os.listdir(folder) if f.split(".")[-1] in {"avi", "mp4", "mkv", "vob"}])
        self.subtitles = [
            os.path.basename(f) 
            for f in os.listdir(folder) if f.split(".")[-1] == "vtt"]
        self.slosinh = "sinh" in os.path.basename(folder).lower()

