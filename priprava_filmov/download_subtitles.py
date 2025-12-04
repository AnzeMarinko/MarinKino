import requests
from bs4 import BeautifulSoup
import zipfile

def search_podnapisi(title, year):
    """Poišče film na podnapisi.net in vrne povezave do slovenskih podnapisov."""
    base_url = "https://www.podnapisi.net"
    search_url = f"{base_url}/sl/subtitles/search/advanced?keywords={title.replace(' ', '+')}&language=sl"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    subtitles = []
    
    # Poiščemo zadetke (tabela podnapisov)
    for row in soup.select("tbody tr"):
        language = row.select_one("abbr.language span")
        if language and "sl" in language.text:  # Filtriramo slovenske podnapise
            output = {}
            for a in row.select("td a"):
                href = a.get("href")
                if href:
                    if "sl/subtitles/search/" not in href and "/download" not in href[-9:] and "link" not in output.keys() and "title" not in output.keys():
                        link = base_url + a.get("href")
                        aux_title = a.text.strip()
                        if title in aux_title and f"({year})" in aux_title:
                            output["title"] = aux_title
                            output["link"] = link
                    elif "&contributors=" in href and "contributor" not in output.keys():
                        contributor = a.text.strip()
                        output["contributor"] = contributor
            if "link" in output.keys():
                subtitles.append(output)
    return subtitles[:5]

def download_podnapis(url, extract_path):
    """Prenese in shrani podnapise iz podnapisi.net."""
    headers = {"User-Agent": "Mozilla/5.0"}
    file_response = requests.get(url + "/download", headers=headers)

    zip_path = "subtitles.zip"
    with open(zip_path, "wb") as f:
        f.write(file_response.content)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)

    print(f"Podnapisi so shranjeni")
