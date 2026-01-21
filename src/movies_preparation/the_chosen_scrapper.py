import asyncio
import json
import logging
import os
import subprocess
import time
from urllib.parse import urljoin

import m3u8
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

log = logging.getLogger(__name__)

user_name = os.getenv("CHOSEN_USERNAME")
password = os.getenv("CHOSEN_PASSWORD")
chosen_token = os.getenv("CHOSEN_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

videos = {}
for season in [1, 2, 3, 4, 5]:
    # preberemo iz lokalno shranjenega html, ki se odpre kot seznam epizod v izbrani sezoni
    with open(
        f"data/movies/06-the-chosen/seasons-metadata/{season}.html", "r"
    ) as f:
        soup = BeautifulSoup(f.read(), "lxml")

    episodes = soup.find_all("img")
    i = 0
    for e in episodes:
        src, alt = e.get("src"), e.get("alt")
        if "VIDEO" in src:
            channel_id = int(src.split("/channels/")[-1].split("/")[0])
            video_id = int(src.split("/VIDEO_THUMBNAIL/")[-1].split("/")[0])
            i += 1
            videos[f"{season}-{i}"] = {
                "season": season,
                "episode": i,
                "description": alt,
                "channel_id": channel_id,
                "video_id": video_id,
                "cover_url": src,
            }

    episodes = soup.find_all("span")
    i = 0
    for e in episodes:
        if "contentCardTitle" in "".join(e.attrs.get("class", [])):
            i += 1
            videos[f"{season}-{i}"]["title"] = e.contents[0]

    episodes = soup.find_all("span")
    i = 0
    for e in episodes:
        if (
            e.contents
            and ":" in e.contents[0]
            and len(e.contents[0]) in [5, 7]
        ):
            i += 1
            times = e.contents[0].split(":")
            minutes = 0
            if len(times) == 3:
                minutes += int(times[0]) * 60
            minutes += int(times[-2])
            minutes += int(times[-1]) / 60
            videos[f"{season}-{i}"]["runtime"] = round(minutes)
    if i == 0:
        raise Exception

headers = {
    "accept": "*/*",
    "accept-language": "sl-SI,sl;q=0.9",
    "cache-control": "max-age=0",
    "if-modified-since": "Wed, 22 Oct 2025 16:59:14 GMT",
    "origin": "https://watch.thechosen.tv",
    "referer": "https://watch.thechosen.tv/",
    "if-none-match": '"c7fafa5326546ce8d0104fb215489120"',
    "priority": "u=0, i",
    "sec-ch-ua": '"Brave";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "sec-fetch-user": "?1",
    "sec-gpc": "1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
}
token = f"viewerToken={chosen_token}"


def combine_to_mp4(
    video_path: str,
    audio_tracks: list[tuple[str, str, str]],  # (path, language, title)
    subtitle_tracks: list[
        tuple[str, str, str]
    ] = None,  # (path, language, title)
    output_path: str = "output.mp4",
    default_audio: int = 0,
    default_subtitle: int = 0,
):
    """
    Združi video + več zvokov + več podnapisov v eno MP4 datoteko.

    Args:
        video_path: pot do video datoteke (.ts, .mp4 ...)
        audio_tracks: seznam (path, language_code, title)
        subtitle_tracks: seznam (path, language_code, title)
        output_path: izhodni mp4
        default_audio: index privzetega zvoka
        default_subtitle: index privzetih podnapisov
    """
    if subtitle_tracks is None:
        subtitle_tracks = []

    cmd = ["ffmpeg", "-y", "-i", video_path]

    # Dodaj vse zvoke
    for audio_path, _, _ in audio_tracks:
        cmd += ["-i", audio_path]

    # Dodaj vse podnapise
    for sub_path, _, _ in subtitle_tracks:
        cmd += ["-i", sub_path]

    # MAPPING
    # video = prvi input (0)
    maps = ["-map", "0:v"]
    for i in range(len(audio_tracks)):
        maps += ["-map", f"{i+1}:a"]  # zvoki
    for i in range(len(subtitle_tracks)):
        maps += ["-map", f"{i+1+len(audio_tracks)}:s"]  # podnapisi

    cmd += maps

    # CODECS
    cmd += [
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-c:s",
        "mov_text",
    ]

    # METADATA
    for i, (_, lang, title) in enumerate(audio_tracks):
        cmd += [
            f"-metadata:s:a:{i}",
            f"language={lang}",
            f"-metadata:s:a:{i}",
            f"title={title}",
        ]

    for i, (_, lang, title) in enumerate(subtitle_tracks):
        cmd += [
            f"-metadata:s:s:{i}",
            f"language={lang}",
            f"-metadata:s:s:{i}",
            f"title={title}",
        ]

    # DEFAULT flags
    for i in range(len(audio_tracks)):
        disposition = "default" if i == default_audio else "0"
        cmd += [f"-disposition:a:{i}", disposition]

    for i in range(len(subtitle_tracks)):
        disposition = "default" if i == default_subtitle else "0"
        cmd += [f"-disposition:s:{i}", disposition]

    cmd += [output_path]

    if os.path.exists(output_path):
        return None
    for file, _, _ in subtitle_tracks + audio_tracks:
        if not os.path.exists(file):
            raise
    if not os.path.exists(video_path):
        raise

    logging.info("Running ffmpeg:\n " + " ".join(cmd))
    subprocess.run(cmd, check=True)


async def get_master_url(video_id):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                # executable_path="/snap/bin/brave"  # ali prava pot do Brave
            )
            page = await browser.new_page()
            await page.goto(
                f"https://watch.thechosen.tv/video/{video_id}",
                wait_until="networkidle",
            )

            # počakamo, da se prikaže obrazec (če je asinhrono naložen)
            await page.wait_for_selector('button[aria-label="Prijavite se"]')

            # klikni gumb "Sign in" ali podobno (preveri selector na strani)
            await page.click('button[aria-label="Prijavite se"]')

            # počakamo, da se prikaže obrazec (če je asinhrono naložen)
            await page.wait_for_selector(
                'button[aria-label="Nadaljujte z e-pošto auth button"]'
            )

            # klikni gumb "Sign in" ali podobno (preveri selector na strani)
            await page.click(
                'button[aria-label="Nadaljujte z e-pošto auth button"]'
            )

            # počakamo, da se prikaže obrazec (če je asinhrono naložen)
            await page.wait_for_selector('input[name="username"]')

            # izpolni prijavne podatke
            await page.fill('input[name="username"]', user_name)
            await page.fill('input[name="password"]', password)

            # klikni gumb "Sign in" ali podobno (preveri selector na strani)
            await page.click(
                'button[type="submit"], button:has-text("Prijava")'
            )

            # počakaj, da se prijava zaključi in stran naloži
            await page.wait_for_load_state("networkidle")
            time.sleep(10)
            html = await page.content()
            await browser.close()
            return html

    html = await run()
    soup = BeautifulSoup(html, "lxml")

    meta = soup.find("meta", attrs={"property": "og:url"})
    if meta and meta.get("content"):
        return meta["content"]
    return None


def scrappe_video_data(
    season,
    episode,
    video_id,
    cover_url,
    title,
    description,
    runtime,
    target_video_height=1440,
):

    folder = f"data/movies/06-the-chosen/Season_{season}-Episode_{episode}"
    if not os.path.exists(folder):
        os.mkdir(folder)

    cover_file = f"{folder}/cover_image.jpg"
    if not os.path.exists(cover_file):
        with open(cover_file, "wb") as f:
            f.write(requests.get(cover_url).content)

    readme_file = f"{folder}/readme.json"
    if not os.path.exists(readme_file):
        metadata = {
            "Film": f"The Chosen S{season}E{episode}: {title}",
            "Title": f"The Chosen S{season}E{episode}: {title}",
            "Genres": ["Druzinski"],
            "Year": "2023-2027",
            "Runtimes": runtime,
            "Plot": description,
            "Plot outline": "Za slovenski zvok glejte preko lokalnega predvajalnika filmov (npr. VLC), kjer lahko izberete jezik zvoka. Brskalnik ne omogoča izbire zvoka.",
        }
        with open(readme_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)

    output_path = f"{folder}/The-Chosen_S{season}-E{episode}.mp4"
    if os.path.exists(output_path):
        return None

    url = asyncio.run(get_master_url(video_id))
    if url is None:
        logging.error(url)
        raise

    master = m3u8.load(url, headers=headers)
    # Izberi resolucijo najbližje 1080p
    video_best = max(
        master.playlists,
        key=lambda p: -abs(target_video_height - p.stream_info.resolution[1]),
    )
    audio_en_info = next(
        m for m in master.media if m.type == "AUDIO" and m.name == "English"
    )
    audio_sl_info = next(
        m for m in master.media if m.type == "AUDIO" and m.name == "Slovenian"
    )
    subs_en_info = next(
        m
        for m in master.media
        if m.type == "SUBTITLES" and m.name == "English"
    )
    subs_sl_info = next(
        m
        for m in master.media
        if m.type == "SUBTITLES" and m.name == "Slovenian"
    )
    logging.info(
        f"Izbrana kvaliteta: {video_best.stream_info.resolution} {video_best.stream_info.bandwidth} {[m.stream_info.resolution for m in master.playlists]}"
    )

    video_url = urljoin(url, video_best.uri)
    audio_en_url = urljoin(url, audio_en_info.uri)
    audio_sl_url = urljoin(url, audio_sl_info.uri)
    subs_en_url = urljoin(url, subs_en_info.uri)
    subs_sl_url = urljoin(url, subs_sl_info.uri)

    # funkcija za prenos enega streama (kot prej)
    def download_m3u8(url, out_file):
        logging.info(f"S{season} E{episode} {out_file}")
        if os.path.exists(f"{folder}/{out_file}"):
            return None
        try:
            pl = m3u8.load(url, headers=headers)
        except Exception as e:
            logging.error(e)
            logging.error(url)
            return None
        with open(f"{folder}/{out_file}", "wb") as f:
            for seg in pl.segments:
                seg_url = urljoin(url, seg.uri)
                r = requests.get(seg_url, headers=headers, stream=True)
                for chunk in r.iter_content(1024):
                    f.write(chunk)

    download_m3u8(video_url, "video.ts")
    download_m3u8(audio_en_url, "audio_en.aac")
    download_m3u8(audio_sl_url, "audio_si.aac")
    download_m3u8(subs_en_url, "subs_en.vtt")
    download_m3u8(subs_sl_url, "subs_si.vtt")

    combine_to_mp4(
        video_path=f"{folder}/video.ts",
        audio_tracks=[
            (f"{folder}/audio_en.aac", "eng", "English"),
            (f"{folder}/audio_si.aac", "slv", "Slovenian"),
        ],
        subtitle_tracks=[
            (f"{folder}/subs_si.vtt", "slv", "Slovenski podnapisi"),
            (f"{folder}/subs_en.vtt", "eng", "English Subtitles"),
        ],
        output_path=output_path,
    )


def scrappe_chosen():
    for video in videos.values():
        scrappe_video_data(
            video["season"],
            video["episode"],
            video["video_id"],
            video["cover_url"],
            video["title"],
            video["description"],
            video["runtime"],
        )
