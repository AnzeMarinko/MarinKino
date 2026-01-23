# TODO:

* dodaj pytest (https://gemini.google.com/u/1/app/e130f713237e3fb2)
* ko poženem prepare_movies se metadata, ki je v json shranijo v SQL bazo in se potem v app.py samo to uporablja (od tam briše ipd.). naj ima ta skripta tudi svoj flask za pregled delovanja, ročno spreminjanje vrednosti v jsonih
* pošlji prve predloge filmov na mail
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
* urejaj z uporabniškim vmesnikom, ki omogoča predvajanje in urejanje vsakega dela posebej (avtor, album, naslov)
