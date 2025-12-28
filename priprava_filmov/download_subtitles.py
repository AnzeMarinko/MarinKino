import requests
from bs4 import BeautifulSoup
import zipfile
import re
from opensubtitlescom import OpenSubtitles
import os
import time
import io
import logging

OPENSUBTITLESCOM_TOKEN = os.getenv("OPENSUBTITLESCOM_TOKEN")
OPENSUBTITLESCOM_PASSWORD = os.getenv("OPENSUBTITLESCOM_PASSWORD")
osub = OpenSubtitles("MarinKino", OPENSUBTITLESCOM_TOKEN)

def search_opensubtitles(imdb_id, languages=("sl", "en")):
    osub.login("anzem", OPENSUBTITLESCOM_PASSWORD)
    results = []
    for lang in languages:
        try:
            subs = osub.search(
                imdb_id=imdb_id.replace("tt", ""),
                languages=lang,
                order_by="download_count",
                order_direction="desc",
            )
            for s in subs.data[:5]:
                if len(s.files) == 1:
                    results.append({
                        "lang": lang,
                        "downloads": s.download_count,
                        "url": s.files[0].get("file_id"),
                        "release": s.release,
                    })
        except Exception as e:
            logging.error(f"OpenSubtitles error: {e}")
            msg = str(e).lower()
            if "429" in msg or "too many" in msg:
                return results, "RateLimitError"
    return results, None

def download_opensubtitles(sub, i, path):
    data = osub.download(sub["url"])
    filename = f"{path}/subtitle{i}.{sub['lang']}.srt"
    with open(filename, "wb") as f:
        f.write(data)
    return filename


session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
})

def fetch_html(url, tries=5):
    for i in range(tries):
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200 and "<html" in r.text.lower():
                return r.text
        except:
            pass
        time.sleep(1.5 * (i + 1))
    return None

def search_podnapisi_safe(title, year):
    title = re.sub(r'[^\w]+', ' ', title.lower().replace(".slosinh", ""), flags=re.UNICODE)
    title = re.sub(r'\b(19|20)\d{2}\b', '', title).strip()

    base = "https://www.podnapisi.net"
    url = f"{base}/sl/subtitles/search/advanced?keywords={title.replace(' ', '+')}"
    
    html = fetch_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    for row in soup.select("tbody tr"):
        lang = row.select_one("abbr.language span")
        if not lang or lang.text.strip() not in ("sl", "en"):
            continue

        title_link = row.select_one("td a[href^='/sl/subtitles/']")
        if not title_link:
            continue

        aux_title = title_link.text
        if year and str(year) not in aux_title:
            continue

        results.append({
            "lang": lang.text.strip(),
            "title": aux_title,
            "link": base + title_link["href"]
        })

    return results[:5]

def download_podnapisi_safe(url, extract_path):
    r = session.get(url + "/download", timeout=10)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(extract_path)
    logging.info("Podnapisi so shranjeni")



def get_subtitles(title, year, imdb_id, path):
    # 1. OpenSubtitles
    subs, err = search_opensubtitles(imdb_id)
    if subs:
        for i, sub in enumerate(subs):
            download_opensubtitles(sub, i, path)
        return 
    elif err == "RateLimitError":
        return err

    # 2. podnapisi.net fallback
    subs = search_podnapisi_safe(title, year)
    if subs:
        for sub in subs:
            download_podnapisi_safe(sub["link"], path)
        return True

    logging.error(f"❌ No subtitles found: {title}")
    return False

