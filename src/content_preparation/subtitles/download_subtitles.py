import io
import logging
import os
import re
import time
import zipfile

import requests
from bs4 import BeautifulSoup
from opensubtitlescom import OpenSubtitles

log = logging.getLogger(__name__)

OPENSUBTITLESCOM_TOKEN = os.getenv("OPENSUBTITLESCOM_TOKEN")
OPENSUBTITLESCOM_PASSWORD = os.getenv("OPENSUBTITLESCOM_PASSWORD")
osub = OpenSubtitles("MarinKino", OPENSUBTITLESCOM_TOKEN)

# Marker appended to filenames of subtitles fetched by us, so alignment
# (rescale) only ever touches subtitles we downloaded, never ones already
# present in the video container or placed manually.
DOWNLOADED_MARKER = "-Downloaded"


def search_opensubtitles(imdb_id, languages=("sl", "en"), num=1):
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
            for s in subs.data[:num]:
                if len(s.files) == 1:
                    results.append(
                        {
                            "lang": lang,
                            "downloads": s.download_count,
                            "url": s.files[0].get("file_id"),
                            "release": s.release,
                        }
                    )
        except Exception as e:
            log.error(f"OpenSubtitles error: {e}")
            msg = str(e).lower()
            if "429" in msg or "too many" in msg:
                return results, "RateLimitError"
    return results, None


def download_opensubtitles(sub, i, path):
    data = osub.download(sub["url"])
    lang_short = "Slo" if sub["lang"] == "sl" else sub["lang"]
    filename = f"{path}/subtitles{i}-{lang_short}Subs{DOWNLOADED_MARKER}.srt"
    with open(filename, "wb") as f:
        f.write(data)
    return filename


session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
    }
)


def fetch_html(url, tries=5):
    for i in range(tries):
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200 and "<html" in r.text.lower():
                return r.text
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def search_podnapisi_safe(title, year, languages):
    title = re.sub(
        r"[^\w]+", " ", title.lower().replace(".slosinh", ""), flags=re.UNICODE
    )
    title = re.sub(r"\b(19|20)\d{2}\b", "", title).strip()

    base = "https://www.podnapisi.net"
    url = (
        f"{base}/sl/subtitles/search/advanced"
        f"?keywords={title.replace(' ', '+')}"
    )

    html = fetch_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = {}
    final_list = []

    for row in soup.find_all("a"):
        if row:
            href = str(row.attrs.get("href"))
            for lang in languages:
                if (
                    "/subtitles/" in href
                    and f"/{lang}" in href
                    and href.endswith("/download")
                    and year in href
                ):
                    urls_for_lang = [r["url"] for r in results.get(lang, [])]
                    is_new = base + href not in urls_for_lang
                    if len(urls_for_lang) < 5 and is_new:
                        entry = {"lang": lang, "url": base + href}
                        results.setdefault(lang, []).append(entry)
                        final_list.append(entry)

    return final_list


def download_podnapisi_safe(sub, index, extract_path):
    r = session.get(sub["url"] + "/download", timeout=10)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        srt_names = [n for n in z.namelist() if n.lower().endswith(".srt")]
        z.extractall(extract_path)

    lang_short = "Slo" if sub["lang"] == "sl" else sub["lang"]
    downloaded = []
    for i, name in enumerate(srt_names):
        src = os.path.join(extract_path, name)
        suffix = f"-{i}" if i else ""
        dst = os.path.join(
            extract_path,
            f"subtitles{index}{suffix}-{lang_short}Subs{DOWNLOADED_MARKER}.srt",  # noqa: E501
        )
        os.replace(src, dst)
        downloaded.append(dst)
    log.info("Podnapisi so shranjeni")
    return downloaded


def get_subtitles(title, year, imdb_id, path, languages=["sl", "en"]):
    # 1. OpenSubtitles
    subs, err = search_opensubtitles(imdb_id, languages)
    time.sleep(1)
    if subs:
        for i, sub in enumerate(subs):
            download_opensubtitles(sub, "" if i == 0 else i, path)
            time.sleep(10)
        return True
    elif err == "RateLimitError":
        print("RateLimitError")
        return False

    # 2. podnapisi.net fallback
    subs = search_podnapisi_safe(title, str(year), languages)
    if subs:
        for i, sub in enumerate(subs):
            download_podnapisi_safe(sub, i, path)
        return True

    log.error(f"❌ No subtitles found: {title}")
    return False
