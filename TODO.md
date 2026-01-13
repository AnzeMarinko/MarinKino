# TODO:

previdno (najprej nekakšen aux, ki ga kot admin preveriš, potem pa zamenjaš, ko je aux dober:
* s tmdb pridobi slovenske in originalne naslove (https://chatgpt.com/c/6965f429-b7f8-832f-99c4-733d27a2529a), 
* če že obstaja slovenski opis, ga pridobi,
* uporabi kvalitetnejšo naslovno sliko če obstaja
* na strani začni uporabljati slovenski in originalen naslov ter samo en opis, ko bo to mogoče

* postavi vse v docker-compose (flask, postgresql, nginx, certbot, fail2ban) https://gemini.google.com/u/1/app/036b4492a1b2d79c

Glasba:
* naredi playlisto vsega kar bi rad imel (najprej Youtube music in nato še navaden Youtube)
* potem pa (predelaj ta ukaz še malo):
yt-dlp --extract-audio --audio-format mp3 \
  --embed-thumbnail --embed-metadata \
  --add-metadata \
  -o "%(playlist_index)s - %(title)s.%(ext)s" \
  <URL_PLAYLISTE>
* uredi zbirko glasbe (dodaj tudi kakšne meni v tem času ljube pesmi: Res je prijetno, Molim te ponižno, Jezus se ob morju ustavi, Tezejske ... narobno-zabavna glasba, MPP, ...)
