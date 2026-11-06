# Raspberry Pi: RAM, CPU, temperatura in odzivnost

## En ukaz za meritve

Iz korena repozitorija na Pi:

```sh
sudo bash scripts/rpi_metrics.sh
```

Pregled traja približno 20 sekund. Izpiše RAM/swap, CPU in I/O pressure,
temperaturo, zastavice omejevanja hitrosti, Docker porabo in omejitve,
OOM/ponovne zagone, prostor ter imena procesov. Ne izpisuje okolja,
argumentov procesov, aplikacijskih dnevnikov ali skrivnosti; ne ustvarja
obremenitve in ne spreminja nastavitev.

Pošlji izpis skupaj z opisom dela: mirovanje, predvajanje filma, nalaganje
fotografije, priprava ZIP ali vzdrževanje. Za primerjavo ponovi isti scenarij.
`docker stats` je trenutni vzorec, ne zgodovina vrhov. Prva vrstica `vmstat`
je povprečje od zagona; naslednje so trenutni vzorci. `OOMKilled` je stanje
vsebnika, ne popoln arhiv incidentov.

## Potrjene meritve ob nastavitvi

RPi 5 Model B, 8 GB RAM, aarch64, NVMe. Uporabniški izpis po vključitvi
memory cgroup in nastavitvi omejitev; brez namerno ustvarjene obremenitve:

| Vsebnik | RAM v vzorcu | Omejitev RAM | CPU v vzorcu |
| --- | ---: | ---: | ---: |
| marinkino-app | 176,1 MiB | 1 GiB | 0,01 % |
| marinkino-nginx | 15,98 MiB | 192 MiB | 0,00 % |
| marinkino-redis | 32,73 MiB | 256 MiB | 0,56 % |
| marinkino-redis-auth | 9,625 MiB | 128 MiB | 0,58 % |

Skupaj približno **234 MiB** za te štiri vsebnike v tem vzorcu. Meja RAM
ni rezervirana poraba. Prejšnji pregled je pokazal približno 58 °C in
94–99 % prostega CPU; največ RAM sta porabljala procesa VS Code Server
(približno 1,46 GiB in 603 MiB RSS), ne spletna aplikacija. RSS različnih
procesov lahko vključuje skupne strani in ni enak Docker obračunu.

To ni meritev največje porabe, odzivnih časov ali dokaz prihranka po spremembi
kode. Posebej še izmeri pretvarjanje slik, pripravo filmskega arhiva in
vzdrževanje. Swap, ki je zaseden, sam po sebi ne pomeni trenutnega
preobremenjevanja; opazuj `si`/`so` in pressure. Firmware zastavice lahko
vključujejo zgodovinske dogodke; ne zamenjaj jih s trenutno omejitvijo hitrosti.

## Docker in cgroup

```sh
sudo docker info --format 'cgroup={{.CgroupVersion}} memory={{.MemoryLimit}} swap={{.SwapLimit}}'
cat /sys/fs/cgroup/cgroup.controllers
```

Pri cgroup v2 mora seznam vsebovati `memory`, Docker pa vrniti
`memory=true swap=true`. Izpis `0B / 0B`, `memory=false` ali opozorilo
`No memory limit support` pomeni, da nastavljenih mej še ne moreš upoštevati
kot zaščito. Preveri jedrno ukazno vrstico:

```sh
tr ' ' '\n' </proc/cmdline | awk '/^cgroup_/'
```

Na preverjenem Pi je bil vzrok `cgroup_disable=memory`. Rešitev je bil
`cgroup_enable=memory` na koncu **ene same obstoječe vrstice** v
`/boot/firmware/cmdline.txt`, nato ponovni zagon. Pred urejanjem naredi kopijo
te datoteke; ne prepisuj parametrov za korenski disk in ne dodajaj nove
vrstice. Zagon spremeni le, kadar podpora manjka, in po ponovnem zagonu
ponovi zgornje preverjanje. Razlaga: [Raspberry Pi kernel #6980](https://github.com/raspberrypi/linux/issues/6980)
in [uradna navodila za cmdline.txt](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-the-kernel-command-line).

Trajne meje so v `docker-compose.yml`: aplikacija privzeto 1024m
(`MARINKINO_APP_MEMORY`), Nginx 192m, Redis 256m, prijavni Redis 128m.
Setup jih uveljavi ob ustvarjanju vsebnikov. Za že delujoče vsebnike je bil
uporabljen spodnji ukaz; `docker update` ne spremeni Compose datoteke:

```sh
sudo bash <<'LIMITS'
set -e
docker update --memory 1024m --memory-swap 2048m marinkino-app
docker update --memory 192m --memory-swap 384m marinkino-nginx
docker update --memory 256m --memory-swap 512m marinkino-redis
docker update --memory 128m --memory-swap 256m marinkino-redis-auth
docker stats --no-stream marinkino-app marinkino-nginx marinkino-redis marinkino-redis-auth
LIMITS
```

`--memory-swap` pomeni skupno mejo RAM + swap: 1024m/2048m pomeni največ
1024m RAM in dodatnih 1024m swap. To ne ustvari swap prostora na gostitelju.
Compose brez izrecnega `memswap_limit` ob podpori swap uporablja Dockerjevo
privzeto skupno mejo dvakratnika RAM. [Docker: pomnilniške omejitve](https://docs.docker.com/engine/containers/resource_constraints/).

## Kje se delo izvaja

- **Spletne zahteve:** Waitress ima štiri niti; bere pripravljene medijske
  metapodatke. Analiza zvoka, Gemini in pretvorba celotne zbirke ne tečejo
  ob zagonu aplikacije ali predvajanju.
- **Priprava vsebin:** ločeno okolje `preparation`; CLI ponuja `--dry-run`,
  `--check`, `--kind`, `--folder`, `--threads`. Privzeto FFmpeg uporablja
  dve niti; dražja analiza glasbe zahteva `--analyze`. Glej [postopek](adding_data.md).
- **Blog slike:** pri nalaganju nastanejo WebP velikosti; stare fotografije
  postopno pripravi `python -m blog_images --prepare-existing` v omejenem
  vsebniku med posodobitvijo. HTTP bere pripravljene različice; izvirniki
  ostanejo. Brez pripravljene slike se uporabi izvirnik.
- **Statika:** gradnja ustvari `/static/v/<vsebinski hash>/…` in predhodno
  stisnjene gzip datoteke. Nginx kopira statiko iste aplikacijske slike.
  `immutable` velja le za različice s hashom; stare poti se ponovno preverijo.
  Pri obnovi vedno uporabi ujemajoči se aplikacijsko in Nginx sliko.
- **Predpomnilniki:** skrbniška statistika 30 sekund, vsebina bloga glede na
  revizijo datoteke in očiščen Markdown. Celoten HTML s CSRF, piškotki ali
  CSP nonce se ne deli med uporabniki.

Plyr uporablja lokalni `vendor/blank.mp4` za ponastavitev predvajanja.
Izvor je `https://cdn.plyr.io/static/blank.mp4`, SHA-256
`5747997d80825cbafcdbe5ab97d7b5502c06b1aae85fed9610845348b3da4d98`.

## Opravila v ozadju

`python -m serve` in `python src/app.py` zaženeta ločena porabnika za pošto
in filmske arhive. Arhiv zato ne zasede niti HTTP in ne zadrži ponastavitve
gesla. Vrsta v `data/jobs.sqlite3` sprejme največ 128 čakajočih/tekočih
opravil in 2 MiB na vsebino opravila. Baza in kopije vsebujejo zasebno pošto.

Po ponovnem zagonu se prekinjen arhiv pripravi znova. Prekinjeno ali delno
sprejeto SMTP pošiljanje je `uncertain` in se ne ponovi samodejno.
Pri običajni napaki kampanje ponovitev izpusti uspešno poslane jezikovne
skupine. SMTP ob prekinitvi povezave ne zagotavlja natanko ene dostave.
Zaključena opravila odstranijo vsebino pošte; stanje se hrani sedem dni.

Javni ogledi bloga so dnevni skupni števci, ne unikatni obiskovalci.
Migracija `python -m analytics_privacy` odstrani stare IP/geolokacijske
zapise, ohrani skupne števce in se ne dotika prijav. Obstoječe varnostne
kopije imajo svojo politiko hrambe.

## Pred namestitvijo

Zaženi regresijske in brskalniške teste. Setup na gostitelju z Dockerjem
zgradi slike, preveri Nginx in izoliran runtime, nato zamenja vsebnike.
Lokalni Python testi ne nadomestijo `nginx -t`, gradnje ARM slike ali
meritve porabe pod obremenitvijo na dejanskem Pi.
