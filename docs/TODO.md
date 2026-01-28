# TODO:

* popravi prikazovanje statistike odprtih strani
* dodaj angleške podnapise (vsak dan jih doda 20)
* pošlji prve predloge filmov na mail in dodaj, da se zadnji predlog pošlje tudi novemu uporabniku
* nov release v1.2.0 glede na commit messages

Nova glasba:
    * naredi playlisto vsega kar bi rad imel (najprej Youtube music in nato še navaden Youtube)
    * potem pa (predelaj ta ukaz še malo):
    yt-dlp --extract-audio --audio-format mp3 \
    --embed-thumbnail --embed-metadata \
    --add-metadata \
    -o "%(playlist_index)s - %(title)s.%(ext)s" \
    <URL_PLAYLISTE>
    * dodaj tudi kakšne meni v tem času ljube pesmi: Res je prijetno, Molim te ponižno, Jezus se ob morju ustavi, Tezejske ... narobno-zabavna glasba, MPP, ..., novejše duhovne mladinske (razni avtorji slovenski in zbori), lepe zborovske cerkvene
    Bob Dylan, Blaž Podobnik (Pesmi o nebesih), Po vodi pridi bos, Hamo, Gjurin, Svetnik, Smolar …
    * pesmim uredi metapodatke v uporabniškem vmesniku
