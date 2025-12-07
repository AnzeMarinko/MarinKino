# MarinKino

To je repozitorij za domači kino. Preko HTTPS serverja so tako filmi z domačega diska varno dostopni preko spleta. Ta server omogoča enostavno izbiro in ogled filmov kar v brskalniku (deluje pa seveda le, kadar je računalnik s serverjem prižgan). Koda avtomatizirano poskrbi:
* da vsak film v eni mp4 datoteki za zmanjšanje datoteke in tudi za združevanje .vob in drugih podobnih formatov, 
* priskrbi naslovnice, opise in druge podatke o filmih ter opise z umetno inteligenco prevede v slovenščino,
* priskrbi podnapise z interneta (ročno je potrebno izbrani najboljšo datoteko),
* z umetno inteligenco zazna govor in poravna podnapise z zvokom (zamik in skaliranje),
* preveri jezik podnapisov in po potrebi z umetno inteligenco prevede v slovenščino.

Poleg tega je tu tudi koda za avtomatsko pridobitev serije The Chosen in snemanje filmov s Sloflix, saj Mojblink.si nima mnogih filmov, partis.si pa že dolgo ne deluje več.
> Mimogrede: Filme sem uredil in večino kode pripravil že preden je ven prišel Sloflix, ki na nek način podobna stvar. Poleg osebnega zadovoljstva ob učenju novega in pripravi celotnega lastnega sistema je namen te strani predvsem zbirka vsebinsko kvalitetnih filmov in risank.

> Stran je dostopna preko [anzemarinko.duckdns.org](anzemarinko.duckdns.org).

Preko strani pa so dostopne tudi šale (meme) in spodbude, ki sem jih zbiral skozi leta. Del šal je seveda časovno specifičen predvsem zaradi zborovskih in koronskih let.

## Nastavitev
[Nastavitev MarinKino serverja](installation.md)

V primeru napak ali pomanjkljivosti navodil ali delovanja priprave filmov in strežnika bom vesel predlogov.

## TODO:

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
