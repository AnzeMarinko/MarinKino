# Priprava in dodajanje vsebin

Priprava teče ločeno od javne aplikacije. Ukaze izvajaj iz korena repozitorija, po možnosti na računalniku z dovolj prostora; na RPi obdeluj zaporedno. Filmov in glasbe ne pripravljaj znotraj produkcijskega vsebnika `app`.

## Najprej preglej načrt

```bash
python3 src/prepare_content.py --dry-run
python3 src/prepare_content.py --kind movies --check
python3 src/prepare_content.py --kind music --check
```

`--dry-run` izpiše najdene izvore, skupno velikost, prosti prostor in razpoložljiva orodja. Skripta pri tem ničesar ne zapisuje, ne uporablja omrežja in ne nalaga pripravljalnih knjižnic. `--check` vrne izhodno kodo `1`, če katero potrebno orodje manjka. Glasba potrebuje `ffmpeg` in `ffprobe`, filmi dodatno Shaka Packager (`packager` na `PATH`). Prosti prostor je prikazan informativno: izvor, začasne datoteke in končni HLS med pripravo obstajajo hkrati.

Za celoten filmski postopek in lokalni urejevalnik namesti dodatne Python odvisnosti:

```bash
uv sync --extra preparation
```

Orodja FFmpeg/FFprobe in Shaka Packager niso Python paketi; namesti različice za arhitekturo pripravljalnega računalnika. Nastavitve TMDB, prevajalnika in ponudnikov podnapisov potrebuješ samo za njihove korake. Gesel in API ključev ne vpisuj v ukaze ali dokumentacijo. Osnovna priprava MP3 brez analize uporablja odvisnosti glavne aplikacije.

## Filmi: pregled → podatki → podnapisi → HLS

1. Vsak film postavi v svojo mapo pod `data/movies/0x-neurejeni-filmi`, npr. `La.Vita.E.Bella.1997`. Več zaporednih delov poimenuj `01…`, `02…`; združitev uporablja abecedni vrstni red. Za samostojne epizode ali zbirko izberi način »Zbirka« oziroma pripono `.Collection`.
2. V mapo dodaj izvorne videe in želene `.srt`/`.vtt` podnapise. Podprti video formati: MP4, MKV, AVI, VOB, MOV, WebM. Izvori se po uspešni obdelavi ohranijo v skriti mapi `.originals` s pripono `.source`.
3. Preglej samo izbrani film, nato zaženi pripravo:

   ```bash
   python3 src/prepare_content.py --kind movies --folder data/movies/0x-neurejeni-filmi/La.Vita.E.Bella.1997 --dry-run
   uv run --extra preparation python src/prepare_content.py --kind movies --folder data/movies/0x-neurejeni-filmi/La.Vita.E.Bella.1997 --threads 2
   ```

4. V terminalu potrdi način pretvorbe, izberi metapodatke in preglej podnapise. Prazni odgovor uporabi prikazano privzeto izbiro; `y`, `yes`, `d`, `da` in `ja` pomenijo potrditev. `n` preskoči vprašani korak. Že shranjeni podatki so v `readme.json`; prenos, poravnava in prevod se izvajajo glede na manjkajoče datoteke. Polja `confirmed` so evidenca, ne splošno stikalo za preskok vseh ponovnih vprašanj.
5. Preglej naslov, opis, naslovnico, sliko, zvok in podnapise. Začasna mapa ob neuspehu ni objavljena kot dokončan HLS. Pri združevanju neuspešen del prekine združitev; končni film ne sme vsebovati samo uspešnega dela izvora.
6. Končno mapo prestavi v želeno kategorijo, npr. `data/movies/01-risanke` ali `data/movies/04-drugi-filmi`. Nato osveži knjižnico:

   ```bash
   docker compose restart app
   ```

Brez možnosti (`uv run --extra preparation python src/prepare_content.py`) ostane interaktivni postopek za glasbo/otroški radio in nato vse nove filme. `--kind movies` preskoči vprašanje za glasbo. `Ctrl+C` prekine postopek; pri ponovitvi preveri izpis in mapo. Napake se izpišejo, obdelava drugih filmov nadaljuje, končna izhodna koda je `1`, če je bila zaznana napaka.

### Zbirke in epizode

Pri načinu »Zbirka« vsaka epizoda dobi svoj HLS, npr.
`Zbirka.Collection/01 Prvi/master.m3u8` in
`Zbirka.Collection/02 Drugi/master.m3u8`. Pred pretvarjanjem zbirk posodobi
tudi spletno aplikacijo na različico s podporo več HLS virom.

Predvajalnik ponudi izbor epizode in za vsako ohrani napredek ogleda. Med
postopno pretvorbo podpira tudi mešanico MP4 in HLS; če sta prisotni obe
obliki iste epizode, jo prikaže enkrat in uporabi HLS.

»Prenesi« pripravi ZIP z vsemi epizodami kot ločenimi MP4. HLS se zaporedno
pretvori nazaj v MP4 s kopiranjem tokov, brez ponovnega kodiranja. Omejitev
prenosa 4 GB velja za celotno zbirko; večji prenos se zavrne. Za predvajanje
posameznih epizod ta omejitev arhiva ne velja.

Ikona za prenos v predvajalniku odpre stran »Prenos filma«. Tam izberi
»Pripravi prenos«, počakaj na pripravo in nato »Prenesi film«. Če je ZIP že
pripravljen, se prenese neposredno.

## Glasba in otroški radio

Priporočena struktura za uvoz glasbe:

```text
 data/music/Neurejena-glasba/Izvajalec - Album/
 ├── Skladba.mp3
 └── Skladba/                 # nastane po pripravi
     ├── index.m3u8
     ├── stream.m4s
     └── metadata.json
```

```bash
python3 src/prepare_content.py --kind music --folder data/music/Neurejena-glasba --dry-run
uv run python src/prepare_content.py --kind music --folder data/music/Neurejena-glasba --threads 2
uv run python src/prepare_content.py --kind radio --threads 2
```

`--kind music` brez `--folder` obdeluje vse MP3 pod `data/music`; `--kind radio` obdeluje `data/radio-stories`. Pretvorba teče po eni skladbi, prikaže zaporedno številko in na koncu število pripravljenih, preskočenih in neuspešnih datotek. Dokončan HLS se ponovno uporabi, MP3 ostane na disku. Obstoječi metapodatki ostanejo ohranjeni. Imena MP3 in pripadajoče HLS mape naj ostanejo enaka, da knjižnica oba formata prepozna kot eno skladbo.

Privzeto se pripravijo HLS in osnovni metapodatki iz ID3, brez normalizacije, analize zvoka ali klicev semantične storitve. `--analyze` vključi dodatno analizo pri **novih** HLS pretvorbah; zanjo namesti `preparation` odvisnosti in zahtevane storitve. Že pripravljeni HLS se tudi s to možnostjo preskočijo.

Po preverjanju premakni MP3 **in** istoimensko HLS mapo iz `Neurejena-glasba` v izbrano mapo glasbene knjižnice, nato izvedi `docker compose restart app`. Uvozna mapa je pri glasbi namenjena skrbniškemu pregledu.

## Lokalni spletni urejevalnik

```bash
uv run --extra preparation python src/manual_editor.py
```

Odpri `http://127.0.0.1:8080`. Urejevalnik posluša samo na lokalnem vmesniku; dostop preko javne domene ni podprt. Če teče na RPi, na svojem računalniku odpri SSH tunel:

```bash
ssh -L 8080:127.0.0.1:8080 marinko@IME_ALI_IP_RPI
```

Odpri isti lokalni naslov v brskalniku. Zagon urejevalnika in prikaz strani ne normalizirata, pretvarjata ali preimenujeta vsebin.

- **Glasba:** iskanje, predogled, urejanje naslova/izvajalca/albuma, shranjevanje posamezne skladbe ali vseh sprememb. Iskanje ohrani neshranjena polja. Gumb »Pripravi manjkajoči HLS« izrecno sproži pretvorbo. Prenos iz YouTube zahteva HTTPS povezavo in se sproži šele z gumbom; po prenosu se izvede priprava.
- **Filmi:** pet korakov s povzetkom pred potrditvijo. Metapodatke vnesi ročno ali vpiši IMDb ID (`tt…`) in uporabi »Pridobi po IMDb ID«. Ta spletni korak ne čaka na terminalski vnos. Predogled bere dejansko filmsko mapo; formati, ki jih brskalnik ne podpira, zahtevajo lokalni pregled.
- **Podnapisi:** neizbrani se arhivirajo v `.originals`, ne izbrišejo. Prazen rezultat prenosa ali prevoda se prikaže brez lažne potrditve uspeha.

Pretvorbe in prenosi so lokalni sinhroni postopki. Med delom ostane status viden, gumbi so onemogočeni, podroben napredek je v terminalu. Pusti stran in proces urejevalnika odprta. Druga sočasna sprememba dobi odgovor »Priprava že poteka«. To ni trajna čakalna vrsta: po prekinitvi preveri izpis in datoteke ter ponovno poženi izbrani korak. CLI in urejevalnika ne zaganjaj hkrati nad istimi datotekami.

## Viri, prostor in ponovna priprava

FFmpeg privzeto uporablja dve niti za kodiranje/dekodiranje in eno za filtre; omejitev velja za tukajšnji pretvornik, ni trda omejitev celotnega procesa ali knjižnic analize. `--threads 1` zmanjšuje tekmovanje z javno aplikacijo, več niti lahko pospeši obdelavo. Za lokalni urejevalnik uporabi npr. `MARINKINO_PREP_THREADS=1 uv run --extra preparation python src/manual_editor.py`.

Izvori filmov so arhivirani v `.originals/IME_DATOTEKE.source`; kolizija imena dobi dodatno številko. Obnovi jih v ločeno delovno mapo in odstrani **zadnjo** pripono `.source`. Arhiv ni ločena varnostna kopija diska. Obnovljene izvore in stare HLS pred ponovno pretvorbo najprej ročno premakni iz ciljne mape; obstoječi dokončani HLS se namenoma ne prepisujejo. Arhive odstrani šele po preverjenem predvajanju in lastni varnostni kopiji. Pri glasbi MP3 ostane poleg HLS in za ponovni zagon ni treba ničesar obnavljati.

Meritve RPi, Docker omejitve in merilni ukaz: [Zmogljivost in poraba](performance.md). Namestitev: [Namestitev](installation.md).

## Druge vsebine

- Meme in navdihujoče slike/videe dodaj v `data/memes` brez podmap: PNG, JPG, GIF, WebP ali MP4. Nato osveži aplikacijo.
- Pari za igro Pod krinko so v `data/pod_krinko_besede.csv`: glava `0;1`, nato po en par `prva beseda;druga beseda` v vsaki vrstici. Po spremembi ponovno zaženi `app`.
