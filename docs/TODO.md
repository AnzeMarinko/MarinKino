# TODO:

* dodaj pytest
* uredi navodila za uporabo (/help) in za inštalacijo (instalation.md), configuration (fail2ban, nginx) ...

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
