# MarinKino

To je repozitorij za domači kino. Preko HTTPS serverja so tako filmi z domačega diska varno dostopni preko spleta le izbranemu krogu uporabnikom (prijavljenim). Ta server omogoča enostavno izbiro in ogled filmov kar v brskalniku. Koda avtomatizirano poskrbi:
* da je vsak film v eni `mp4` datoteki za zmanjšanje datoteke in tudi za združevanje `.vob` ter drugih podobnih nekompresiranih formatov, 
* priskrbi naslovnice, opise in druge podatke o filmih ter opise po potrebi z umetno inteligenco prevede v slovenščino,
* po potrebi priskrbi podnapise z interneta (ročno je potrebno izbrani najboljšo datoteko),
* z umetno inteligenco zazna govor in poravna podnapise z zvokom (zamik in skaliranje),
* preveri jezik podnapisov in jih po potrebi z umetno inteligenco prevede v slovenščino.

> Mimogrede: Filme sem uredil in osnovno stran za izbiro filmov pripravil že preden je ven prišel Sloflix, ki je na nek način podobna stvar. Poleg osebnega zadovoljstva ob učenju novega in pripravi celotnega lastnega sistema je namen te strani predvsem zbirka vsebinsko kvalitetnih filmov in risank brez oglasov.

Preko strani pa je dostopno tudi:
* šale (meme) in spodbude, ki sem jih zbiral skozi leta. Del šal je seveda časovno specifičen predvsem zaradi zborovskih in koronskih let.
* zbirka kvalitetne glasbe brez oglasov (slovenske, klasične, krščanske, rokerske, ...). Stran z glasbo je že pripravljena, je pa izbor pesmi še potreben pregleda, saj sem pesmi počasi zbiral skozi leta in je vmes tudi, kaj vsebinsko nekvalitetnega, kar mi je bilo v nekem času zanimivo. Marsikatera zvrst, ki je nisem toliko poslušal, pa tudi manjka.
* družabna igra Pod krinko (slovenska verzija igre Undercover).

> Stran je dostopna preko [anzemarinko.duckdns.org](https://anzemarinko.duckdns.org). Je pa večina vsebin zaklenjenih le za prijavljene uporabnike.

## Navodila za razvijalce
* [Nastavitev MarinKino serverja](docs/installation.md)
* [Dodajanje novih vsebin](docs/adding_data.md)
* [Avtomatsko testiranje API-ja](docs/pytest.md)

V primeru napak, pomanjkljivosti navodil ali slabega delovanja priprave filmov in strežnika bom vesel predlogov.
