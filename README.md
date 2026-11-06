# MarinKino

Javni blog **Sončnice** in zasebna zbirka filmov, glasbe ter otroškega radia.
Flask aplikacija teče na Raspberry Pi za Nginx; medijske datoteke ostanejo na
domačem disku. Javna stran: [anzemarinko.si](https://anzemarinko.si).

## Vsebine in dostop

| Dostop | Vsebine |
| --- | --- |
| Javno | Blog, prevodi in potrjene e-poštne naročnine; vreme, Pod krinko in šale (nekatere funkcije imajo omejitve za goste) |
| Prijavljeni | Filmi in risanke, glasba, otroški radio, predlogi in razširjen dostop do ostalih vsebin |
| Skrbniki | Uporabniki, blog in obvestila, statistika, šale, dnevniki, gibanje in dodatna orodja |

Račune povabi skrbnik. Naročnina na blog ne ustvari uporabniškega računa.
Osnutki bloga niso javni; prek neposredne povezave jih lahko berejo prijavljeni.

## Kje začeti

- [Namestitev in razvoj](docs/installation.md): okolje, dostop, Docker, posodobitve.
- [Priprava filmov in glasbe](docs/adding_data.md): pregled vhodov, pretvorba, urejanje in nadaljevanje.
- [Uporaba strani](docs/usage.md): obiskovalci, člani in skrbniki.
- [Arhitektura](docs/architecture.md): zahteve, podatki in opravila v ozadju.
- [RPi: RAM, CPU in temperatura](docs/performance.md): en ukaz za meritve, cgroup in izmerjena poraba.
- [Varnost, vzdrževanje in obnova](docs/security.md): setup, kopije, migracije in povrnitev.

## Lokalni razvoj

Potrebuješ Python 3.12+, `uv` in lokalni Redis. V `.env` nastavi vrednosti
iz [navodil](docs/installation.md); vzorci niso produkcijska konfiguracija.

```sh
cp .env.example .env
uv sync --extra dev
uv run python src/app.py
```

Razvoj uporablja `data/test_users.json` in `data/fitness-development.sqlite3`.
Začetno enkratno skrbniško geslo je v `data/.initial-admin-password`.
**Ostale zbirke v `data/` se lahko spreminjajo tudi lokalno**; za razvoj
uporabi svojo kopijo podatkov. Produkcije ne zaganjaj z razvojnim strežnikom.

```sh
PYTHONPATH=src uv run --extra dev pytest -q
```

Brskalniški testi so vključeni posebej; postopek je v
[navodilih za razvoj](docs/installation.md#preverjanje-sprememb).
Priprava medijev ima ločene, težje odvisnosti (`uv sync --extra preparation`)
in ne teče ob HTTP zahtevah. Pregled vhodov brez pretvorbe:

```sh
uv run python src/prepare_content.py --dry-run
```

## Struktura

```text
src/app.py                 Flask, prijava in registracija blueprintov
src/blueprints/             Javni, uporabniški in skrbniški HTTP vmesniki
src/templates/, src/static/ Jinja, CSS, JavaScript in lokalne knjižnice
src/content_preparation/   Obdelava medijev zunaj spletne aplikacije
src/prepare_content.py      CLI za pripravo vsebin
src/manual_editor.py        Lokalni urejevalnik metapodatkov in pretvorb
data/                      Vsebine, zasebni JSON in SQLite podatki
configuration/             Nginx, Redis in gradnja pomožnih slik
scripts/                   Namestitev, varnostne kopije, vzdrževanje, meritve
tests/                     Regresijski in brskalniški testi
docs/                      Navodila za uporabo in upravljanje
```
