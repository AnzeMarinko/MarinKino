## Dodajanje novih vsebin v MarinKino

### Dodajanje filmov:
* če imamo film, ki ni v lastni mapi (recimo samo ena `mp4` datoteka), postavi film v mapo z imenom filma,
* postavi mapo v `data/movies/0x-neurejeni-filmi`,
* spremeni ime mape s pikami v obliko: `<naslov.filma>.<letnica><(.slosinh/Collection)>` (npr. `La.Vita.E.Bella.1997`, `Inside.Out.2.2024.SloSih`, `Bacek.Jon.Collection`),
* odstrani vse pomožne datoteke, ki niso film ali datoteka s `.srt` podnapisi (ohrani le slovenske in/ali angleške podnapise),
* poženi `uv run python src/prepare_content.py` — skripta gre interaktivno po vsakem filmu iz `0x-neurejeni-filmi` in za vsak korak vpraša za potrditev/izbiro v terminalu:
  1. **Pretvorba videa**: če je v mapi več video datotek, vpraša ali gre za zbirko (`.Collection`); sicer združi datoteke v en `mp4`, izvleče vgrajene podnapise in kasneje pretvori v `m3u8`.
  2. **Metapodatki**: poišče kandidate na TMDB, odpre galerijo (naslovnice + opisi) v brskalniku in v terminalu ponudi izbiro po številki, ročni vnos IMDb ID-ja ali ročno urejanje polj.
  3. **Preverjanje/prenos podnapisov**: če manjkajo slovenski in/ali angleški podnapisi, vpraša ali naj jih poskusi prenesti (opensubtitles/podnapisi.net).
  4. **Izbira podnapisov**: če je podnapisov več, odpre pregled izsekov v brskalniku in v terminalu vprašaj, katere obdržimo.
  5. **Poravnava podnapisov**: poravna SAMO tiste podnapise, ki jih je skripta sama prenesla (ne že obstoječih iz videa); predlaga zamik/raztezek, omogoči odprtje predvajalnika v brskalniku za vizualno potrditev in ročno prilagoditev.
  6. **Prevod podnapisov**: če manjka slovenski prevod, vpraša ali naj ga samodejno prevede.
  7. **Zvočne datoteke**: na koncu vpraša, ali naj obdela tudi glasbo/radijske zgodbe (pretvorba v `m3u8` + metapodatki).
  * korak/film, ki ga preskočiš (odgovoriš z `n`), se ne ponavlja - skripta gre naprej na naslednji korak/film,
  * že potrjeni koraki (metapodatki, preverjanje/izbira/poravnava/prevod podnapisov) se zapišejo v `readme.json` pod `confirmed`, zato jih ob ponovnem zagonu ne bo znova spraševala (razen če eksplicitno rečeš, da želiš ponoviti),
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
