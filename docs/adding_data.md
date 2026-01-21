## Dodajanje novih vsebin v MarinKino

### Dodajanje filmov:
* če imamo film, ki ni v lastni mapi (recimo samo ena `mp4` datoteka), postavi film v mapo z imenom filma,
* postavi mapo v `data/movies/0x-neurejeni-filmi`,
* spremeni ime mape s pikami v obliko: `<naslov.filma>.<letnica><(.slosinh/Collection)>` (npr. `La.Vita.E.Bella.1997`, `Inside.Out.2.2024.SloSih`, `Bacek.Jon.Collection`),
* odstrani vse pomožne datoteke, ki niso film ali datoteka s `.srt` podnapisi,
* poženi `python src/prepare_movies.py` (to lahko traja kar dolgo, ker po potrebi predeluje video datoteke),
* če je z interneta pridobilo več datotek s podnapisi, izberi najboljše (po možnosti slovenke, čim bolje prilegajoče filmu) in ostale odstrani,
* če z IMDB ni pridobilo podrobnosti o filmu, jih dodaj ročno (pripravi `.json` kot drugod), kar se zgodi običajno le ob zelo neznanih filmih ali pa ob zbirkah/serijah (Collection),
* ponovno poženi `python src/prepare_movies.py`,
* znova zaženi server z ukazom `docker compose restart app` in preveri vse na novo dodane filme (naslovne slike, opise, podnapise ipd.),
* prestavi mapo s filmom v drugo podmapo `data/movies/0y-abc` (npr. `data/movies/01-risanke`, `data/movies/02-zbirke-risank`, `data/movies/03-slovenski-filmi`, `data/movies/04-drugi-filmi`),
* znova zaženi server z ukazom `docker compose restart app`, da se posodobijo lokacije filmov.

### Dodajanje glasbe, šal in navdihov:
* v mapo `data/memes` dodamo `png`, `jpg`, `gif`, `webp` ali `mp4` datoteke s šalami (meme-i) in navdihujočimi mislimi (brez podmap),
* v mapo `data/music` dodamo `mp3` datoteke z glasbo (lahko organizirano v podmape, kar se bo smatralo kot albumi),
* znova zaženi server z ukazom `docker compose restart app`, da se posodobijo seznami datotek.

### Dodajanje parov besed za družabno igro Pod krinko:
* Po potrebi ustvari datoteko `data/pod_krinko_besede.csv` in vanjo dodaj prvo vrstico `0;1`,
* V datoteko dodaj pare besed (vsak par svoja vrstica) `prva beseda;druga beseda`,
* znova zaženi server z ukazom `docker compose restart app`, da se posodobi seznam parov besed.
