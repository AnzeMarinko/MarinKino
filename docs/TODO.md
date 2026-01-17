# TODO:

* pridobi manjkajoče slovenske originalne podnapise
* postavi vse v docker-compose (python app, nginx, certbot, redis) https://gemini.google.com/u/1/app/036b4492a1b2d79c, fail2ban pa izven
* uredi navodila za uporabo (/help) in za inštalacijo (instalation.md)

Glasba:
* naredi playlisto vsega kar bi rad imel (najprej Youtube music in nato še navaden Youtube)
* potem pa (predelaj ta ukaz še malo):
yt-dlp --extract-audio --audio-format mp3 \
  --embed-thumbnail --embed-metadata \
  --add-metadata \
  -o "%(playlist_index)s - %(title)s.%(ext)s" \
  <URL_PLAYLISTE>
* uredi zbirko glasbe (dodaj tudi kakšne meni v tem času ljube pesmi: Res je prijetno, Molim te ponižno, Jezus se ob morju ustavi, Tezejske ... narobno-zabavna glasba, MPP, ...)
* urejaj z uporabniškim vmesnikom, ki omogoča predvajanje in urejanje vsakega dela posebej (avtor, album, naslov)
