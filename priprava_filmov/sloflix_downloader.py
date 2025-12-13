"""
Skripta za snemanje videov s Sloflix 
- ali drugih podobnih ponudnikov video vsebin
  (najbrž tudi YouTube ipd. z morebitno kakšno spremembo kode, 
  da se zares začne predvajanje v celozaslonskem načinu)

Spodaj nastavite ime mape OUTPUT_DIR, kamor se bodo videi shranili in
slovar URLS s ključem za ime videa in vrednostjo kot
par (URL povezava do "sf.strp2p.com" lokacije videa, trajanje videa v sekundah).
URL povezavo do videa najdete v HTML strani izbranega videa (inspect).
Poiščete povezavo oblike "https://sf.strp2p.com/#ebqgm...".
Potem poženete skripto. Če želite snemati v nižji ločljivosti, začasno zmanjšajte
ločljivost glavnega zaslona na izbrano ločljivost. Zvok naj bo vklopljen.
Predvajanju zvoka se lahko izognete z uporabo slušalk, da se ne uporabijo glavni zvočniki.
Morebitni podnapisi bodo avtomatsko "zapečeni" v sliko videa. Zaslon je lahko izklopljen,
ampak računalnik ne sme v način spanja ali zaklenjenega zaslona ipd.
"""
import os
import time
import shlex
import subprocess
import webbrowser
import pyautogui

URLS = {
    # "21. Anglež z omleto": ("https://sf.strp2p.com/#ow6i9", 26 * 60),
    "The.Social.Dilemma": ("movies/07-neurejeni-filmi/The.Social.Dilemma", 'https://sf.strp2p.com/#356et&subs=%5B%7B%22language%22:%22sl%22,%22label%22:%22Slovenski%22,%22url%22:%22https://sloflix.com/subtitles/14730_1.vtt%22%7D%5D', 120*60)
}

def start_recording(output_path, duration):
    ffmpeg_cmd = f"""
    ffmpeg -y \
        -framerate 30 -f x11grab -i :0.0 \
        -f pulse -ac 2 -i default \
        -c:v h264_nvenc -preset fast -b:v 4000k \
        -c:a aac -ar 48000 -b:a 128k \
        "{output_path}"
    """
    if duration > 0:
        ffmpeg_cmd += f" -t {duration}"
    print(f"Začenjam snemanje: {output_path}")
    process = subprocess.Popen(shlex.split(ffmpeg_cmd))
    print(f"Recording... Saving to {output_path}")
    time.sleep(duration)
    process.terminate()
    process.wait()
    print("Recording stopped. (CTRL+C to stop before next)")

if __name__ == "__main__":
    for name, (output_dir, url, duration) in URLS.items():
        filename = os.path.join(output_dir, f"{name}.mp4")
        if not os.path.exists(filename):
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            webbrowser.open_new_tab(url)  # odpri video v brskalniku
            time.sleep(5)  # počakaj, da se naloži
            x, y = 300, 250
            pyautogui.moveTo(x, y)  # pojdi z miško nekam sredi okna
            pyautogui.click()  # pritisni za začetek predvajanja
            pyautogui.moveTo(0, y)  # umakni miško na rob
            time.sleep(1) # počakaj, da se naloži
            pyautogui.press('f11') # celozaslonski način
            time.sleep(1)
            start_recording(
                filename,
                duration=duration + 30  # trajanje v sekundah
                ) 
            pyautogui.hotkey('ctrl', 'w') # zapri zavihek
            time.sleep(180)  # počakaj, če bo uporabnik pritisnil CTRL+C za izhod
