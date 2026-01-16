# MarinKino

To je repozitorij za domači kino. Preko HTTPS serverja so tako filmi z domačega diska varno dostopni preko spleta. Ta server omogoča enostavno izbiro in ogled filmov kar v brskalniku (deluje pa seveda le, kadar je računalnik s serverjem prižgan). Koda avtomatizirano poskrbi:
* da je vsak film v eni mp4 datoteki za zmanjšanje datoteke in tudi za združevanje .vob ter drugih podobnih formatov, 
* priskrbi naslovnice, opise in druge podatke o filmih ter opise z umetno inteligenco prevede v slovenščino,
* priskrbi podnapise z interneta (ročno je potrebno izbrani najboljšo datoteko),
* z umetno inteligenco zazna govor in poravna podnapise z zvokom (zamik in skaliranje),
* preveri jezik podnapisov in jih po potrebi z umetno inteligenco prevede v slovenščino.

Poleg tega je tu tudi koda za avtomatsko pridobitev serije The Chosen in snemanje filmov s Sloflix, saj Mojblink.si nima mnogih filmov, partis.si pa že dolgo ne deluje več.
> Mimogrede: Filme sem uredil in osnovno stran za izbiro filmov pripravil že preden je ven prišel Sloflix, ki je na nek način podobna stvar. Poleg osebnega zadovoljstva ob učenju novega in pripravi celotnega lastnega sistema je namen te strani predvsem zbirka vsebinsko kvalitetnih filmov in risank brez oglasov.

> Stran je dostopna preko [anzemarinko.duckdns.org](https://anzemarinko.duckdns.org).

Preko strani pa je dostopno tudi:
* šale (meme) in spodbude, ki sem jih zbiral skozi leta. Del šal je seveda časovno specifičen predvsem zaradi zborovskih in koronskih let.
* zbirka kvalitetne glasbe brez oglasov (slovenske, klasične, krščanske, rokerske, ...). Stran z glasbo je že pripravljena, je pa izbor pesmi še potreben pregleda, saj sem pesmi počasi zbiral skozi leta in je vmes tudi, kaj vsebinsko nekvalitetnega, kar mi je bilo v nekem času zanimivo.
* družabna igra Pod krinko (slovenska verzija igre Undercover).

## Nastavitev
[Nastavitev MarinKino serverja](docs/installation.md)

V primeru napak, pomanjkljivosti navodil ali slabega delovanja priprave filmov in strežnika bom vesel predlogov.

## Dodajanje novih vsebin

### Dodajanje filmov:
* če imamo film, ki ni v lastni mapi (recimo samo ena `mp4` datoteka), postavi film v mapo z imenom filma,
* postavi mapo v `movies/0x-neurejeni-filmi`,
* spremeni ime mape s pikami v obliko: `<naslov.filma>.<letnica><(.slosinh/Collection)>` (npr. `La.Vita.E.Bella.1997`, `Inside.Out.2.2024.SloSih`, `Bacek.Jon.Collection`),
* odstrani vse pomožne datoteke, ki niso film ali datoteka s `.srt` podnapisi,
* poženi `main.py` (to lahko traja kar dolgo, ker po potrebi predeluje video datoteke),
* če je z interneta pridobilo več datotek s podnapisi, izberi najboljše (po možnosti slovenke, čim bolje prilegajoče filmu) in ostale odstrani,
* če z IMDB ni pridobilo podrobnosti o filmu, jih dodaj ročno (pripravi `.json` kot drugod), kar se zgodi običajno le ob zelo neznanih filmih ali pa ob zbirkah/serijah (Collection),
* ponovno poženi `main.py`,
* znova zaženi server z ukazom `sudo systemctl restart marinkino.service` in preveri vse na novo dodane filme (naslovne slike, opise, podnapise ipd.),
* prestavi mapo s filmom v drugo podmapo `movies/0y-abc` (npr. `movies/01-risanke`, `movies/02-zbirke-risank`, `movies/03-slovenski-filmi`, `movies/04-drugi-filmi`),
* znova zaženi server z ukazom `sudo systemctl restart marinkino.service`, da se posodobijo lokacije filmov.

### Dodajanje glasbe, šal in navdihov:
* v mapo `memes` dodamo `png`, `jpg`, `gif`, `webp` ali `mp4` datoteke s šalami (meme-i) in navdihujočimi mislimi (brez podmap),
* v mapo `music` dodamo `mp3` datoteke z glasbo (lahko organizirano v podmape, kar se bo smatralo kot albumi),
* znova zaženi server z ukazom `sudo systemctl restart marinkino.service`, da se posodobijo seznami datotek.

### Dodajanje parov besed za družabno igro Pod krinko:
* Po potrebi ustvari datoteko `data/pod_krinko_besede.csv` in vanjo dodaj prvo vrstico `0;1`,
* V datoteko dodaj pare besed (vsak par svoja vrstica) `prva beseda;druga beseda`
