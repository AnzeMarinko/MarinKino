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

## Navodila za razvijalce
* [Nastavitev MarinKino serverja](docs/installation.md)
* [Dodajanje novih vsebin](docs/adding_data.md)

V primeru napak, pomanjkljivosti navodil ali slabega delovanja priprave filmov in strežnika bom vesel predlogov.
