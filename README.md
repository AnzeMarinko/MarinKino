## Dependencies:
* Python 3.12
* port forwarding 80-80 in 443-443, nginx, certbot (ga bo v virtualno okolje naložil pip) generiraj certifikat in nastavi cron job za redno posodobitev

## Instalation
* Clone repository
* install `requirements.txt`
* update `.env` and `credentials/gen-lang-client.json`
* run `git update-index --assume-unchanged .env` to keep credentials secure

# TODO:

* naj se pod gumbom za tip filmov kaže koliko je že pogledano od tega tipa

Glasba:
* naredi playlisto vsega kar bi rad imel (najprej Youtube music in nato še navaden Youtube)
* potem pa:
yt-dlp --extract-audio --audio-format mp3 \
  --embed-thumbnail --embed-metadata \
  --add-metadata \
  -o "%(playlist_index)s - %(title)s.%(ext)s" \
  <URL_PLAYLISTE>

* dol potegni vse od Karoline YouTubeMusic in uredi glasbo (odstrani večino moje stare glasbe, ki ni krščanska ali pa vsaj klasična), dodaj kakšne meni v tem času ljube pesmi (Res je prijetno, Molim te ponižno, Jezus se ob morju ustavi, Tezejske ...)
* dodaj stran za predvajanje glasbe
