# TODO:

naredi naslovno stran, kjer se gre lahko na filme, glasbo ...
vsaka stran naj ima svoj logo, barvo, gumb domov
malo uredi css

Glasba:
* naj bodo metapodatki (naslov, izvajalec ...) vidni
* naredi playlisto vsega kar bi rad imel (najprej Youtube music in nato še navaden Youtube)
* potem pa (predelaj ta ukaz še malo):
yt-dlp --extract-audio --audio-format mp3 \
  --embed-thumbnail --embed-metadata \
  --add-metadata \
  -o "%(playlist_index)s - %(title)s.%(ext)s" \
  <URL_PLAYLISTE>
* uredi zbirko glasbe (dodaj tudi kakšne meni v tem času ljube pesmi: Res je prijetno, Molim te ponižno, Jezus se ob morju ustavi, Tezejske ...)

* navodila za dodajanje filma:
    * postavi film v mapo z imenom filma, če je izven mape
    * postavi mapo v movies/07-neurejeni-filmi
    * spremeni ime mape s pikami naslov.filma.letnica(.slosinh)
    * odstrani vse kar ni film ali datoteka s .srt podnapisi
    * poženi main.py
    * če je z interneta pridobilo več datotek s podnapisi, izberi najboljše (po možnosti slovenke, čim bolje prilegajoče filmu) in ostale odstrani
    * ponovno poženi main.py
    * prestavi mapo s filmom v drugo podmapo movies/0x-abc
    