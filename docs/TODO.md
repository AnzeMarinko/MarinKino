# TODO:

* s flask ročno uredi glasbo, nato poženi da se tudi datoteke preimenujejo lepo glede na podatke in da so v primernih mapah glede na žanr
* ta uporabniški vmesnik uporabi tudi ob dodajanju novih pesmi
* pošlji prve predloge filmov na mail in dodaj, da se zadnji predlog pošlje tudi novemu uporabniku
* nov release v1.2.0 glede na commit messages

Glasba:
* naredi playlisto vsega kar bi rad imel (najprej Youtube music in nato še navaden Youtube)
* potem pa (predelaj ta ukaz še malo):
yt-dlp --extract-audio --audio-format mp3 \
  --embed-thumbnail --embed-metadata \
  --add-metadata \
  -o "%(playlist_index)s - %(title)s.%(ext)s" \
  <URL_PLAYLISTE>
* uredi zbirko glasbe (dodaj tudi kakšne meni v tem času ljube pesmi: Res je prijetno, Molim te ponižno, Jezus se ob morju ustavi, Tezejske ... narobno-zabavna glasba, MPP, ...)
Bob Dylan, Blaž Podobnik (Pesmi o nebesih), Po vodi pridi bos, Bach
