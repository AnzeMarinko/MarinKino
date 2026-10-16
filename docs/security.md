# Varnost in samodejno vzdrževanje

Na obstoječem Raspberry Pi z Docker Engine in Compose v2 zaženi iz repozitorija:

```sh
sudo --preserve-env=SSH_CONNECTION bash scripts/setup.sh
```

Ukaz spreminja produkcijsko namestitev in požarni zid. Ohrani trenutno SSH
povezavo; po namestitvi preveri novo SSH povezavo iz svojega upravljavskega
omrežja. Privzeto so novi SSH dostopi dovoljeni iz zasebnih LAN/ULA omrežij in
iz zaznanega trenutnega SSH naslova. Dodatna omrežja določi v
`MARINKINO_MGMT_CIDRS` (CIDR, ločena z vejico). Geselska SSH prijava se ne
izključi samodejno; najprej preveri dostop s ključem.

## Spremembe aplikacije

- Nepublikovane bloge lahko prek neposredne povezave berejo vsi prijavljeni
  uporabniki. Seznam, iskanje in kazalo jih prikazujejo samo skrbnikom;
  neprijavljeni dobijo 404. Zasebni filmski zapisi in e-naslovi niso vključeni
  v HTML/JSON kataloga ali prenose arhivov.
- Menjava in ponastavitev gesla prekličeta vse naprave in stare obnovitvene
  povezave. Različica poverilnic v zasebnem JSON prepreči ponovno uporabo
  stare seje tudi po povrnitvi Redisovih zapisov. Največ pet naprav; sedem dni nedejavnosti, absolutno največ
  30 dni oziroma 12 ur za skrbnika. Ob nadgradnji stare seje zahtevajo prijavo.
- Odjava uporablja POST + CSRF. Vnosi, zahteve, komentarji, predpomnilniki,
  statistike in zunanje poizvedbe imajo omejitve; 404 URL-ji se agregirajo.
- JSON zapisi se zaklepajo čez celoten popravek in zapisujejo atomsko.
- Blog HTML čisti `nh3`; predogled čisti DOMPurify. Ranljivi SimpleMDE je
  nadomeščen z EasyMDE. JS/CSS/fonti so lokalni, izvor in SHA-256 so zapisani
  v `configuration/vendor-assets.json`; prenosi preverijo npm SHA-512.
- Prenosi ZIP uporabljajo disk, eno pripravo hkrati, omejitev velikosti in
  časovno omejen FFmpeg brez dostopa do HTTP/HTTPS virov.
- Ročni urejevalnik posluša samo na `127.0.0.1:8080`, preverja izvor in CSRF.
  Za oddaljeno uporabo uporabi SSH tunel.

CSP že uveljavlja omejitve za `base`, objekte, okvirjanje in oddajo obrazcev.
Strožji `script-src` je za zdaj `Report-Only`, ker stare predloge vsebujejo
inline dogodke. Nonce je dodan skriptam; samo strožji CSP zato še ni popolna
zaščita pred XSS. Turnstile ostane namenska zunanja skripta Cloudflare.

## Vsebniki in gostitelj

Aplikacija teče z neprivilegiranim UID/GID, korenski datotečni sistem je samo
za branje, zmožnosti so odstranjene. Priprava vsebin/ML in pripadajoči ključi
so ločeni od produkcijskih odvisnosti. Waitress posluša samo na Unix vtičniku
v zasebnem volumnu; samo Nginx posreduje zaupanja vredna IP/HTTPS podatka.
Nginxovi mediji so samo za branje. App ne vidi Nginxovih dnevnikov ali Redis
volumnov. Redis nima objavljenih vrat. Prijave in omejitve imajo ločen
Redis s 64 MiB in `noeviction`; javna statistika jih ne more izriniti.
Podatkovni Redis ima 128 MiB in `volatile-lru`, zato se najprej odstranjujejo
začasni zapisi s TTL, trajni napredek ogledov se ohrani. AOF se zapisuje
vsako sekundo. Pri izpadu prijavnega Redisa se prijava ne dovoli brez preverjanja.

Prvi prehod prenese ustavljeni Redis v ločen označen volumen in pretvori
RDB v AOF po uradnem postopku; ponovni zagon mora ohraniti število ključev.
`MARINKINO_REDIS_VOLUME` shrani izbrani volumen. Prvotna mapa
`data/redis_data` ostane. Ponovitev migracije iz starega vira ustvari nov
volumen in ne prepiše nepraznega. Neuporabljene volumne po uspehu preveri
in po potrebi odstrani ročno. UID/GID
ne spreminjaj ročno med delujočimi namestitvami.

Lastna nft tabela `inet marinkino_security` zapre gostiteljske storitve,
razen HTTP/HTTPS, dovoljenega SSH in potrebnega omrežnega prometa. Novi
izhodni dostopi aplikacije/Nginxa do LAN, link-local in ULA naslovov so
blokirani; DNS je dovoljen. Za dodatno ločitev uporabi namenski VLAN/DMZ
na usmerjevalniku. Medijski podatki ostajajo zapisljivi aplikaciji zaradi
skrbniških funkcij; zaščiti jih še z verzioniranimi kopijami oziroma posnetki. Dockerjeve tabele se ne brišejo. Spletni Fail2Ban
jaili uporabljajo `DOCKER-USER`; SSH uporablja `INPUT`. To predpostavlja
Dockerjev običajni iptables backend. Pri prehodu na native nftables backend
prilagodi tudi Fail2Ban akcije. Stabilni `server.log` se rotira v aplikaciji,
Nginxovi dnevniki z logrotate.

## Cron in posodobitve

`/etc/cron.d/marinkino-security` vsebuje:

- vsak dan ob **03:17**: vzdrževanje in preverjena nadgradnja;
- ob **05:11 in 17:11**: enkraten Certbot renew + preverjen Nginx reload;
- vsakih pet minut: ponoven izračun LAN pravil, tudi po spremembi IPv6 predpone;
- vsakih deset minut: DuckDNS, kadar sta domena in žeton nastavljena.
- vsako minuto: omejen pregled gostitelja za skrbniški prikaz dnevnikov.
- ob **07:00**: prenos arhivov in zrcala projekta na Drive, če obstaja
  `/etc/marinkino-security/rclone.conf` z nastavljenim oddaljenim mestom `gdrive`.

Cron izvaja root-owned kopije v `/usr/local/lib/marinkino`. Po spremembi teh
skript v repozitoriju ponovno zaženi setup, da namesti nove kopije.
Sočasni zagoni se preprečijo s `flock`.

Dnevni postopek naredi šifrirano kopijo, posodobi sistemske pakete in Docker
slike, osveži kompatibilne Python/JS odvisnosti, zgradi kandidata in ga
preveri. OSV zavrne znane ranljivosti nameščenih Python/JS paketov; Trivy
zavrne popravljive HIGH/CRITICAL ranljivosti slik. Nedosegljiv pregled ali
neuspešen test prepreči namestitev kandidata. Major različice Python,
Redis in JS se menjajo po ročnem preverjanju združljivosti.

Pred namestitvijo teče izoliran test s svojim Redisom in začasnimi podatki:
CSRF, prijava, zasebnost, osnutki, gostitelj in proxy. Po namestitvi se preveri
zdravje, Nginx konfiguracija in lokalni HTTPS dostop. Ob neuspehu se obnovijo
prejšnje slike, okolje, priklopi in Nginx konfiguracija. Sistemskih paketov
in podatkovnih zapisov ta povrnitev ne vrača. Predhodne slike se ohranijo;
stare lastne slike in stari gradbeni predpomnilniki se čistijo. Volumni se
ne brišejo. Posodobitve kode iz Git se ne prenašajo samodejno.

Dnevnik in zadnji uspeh:

```sh
sudo tail -n 100 /var/log/marinkino-security.log
sudo cat /var/lib/marinkino-security/status.json
sudo fail2ban-client status
sudo nft list table inet marinkino_security
```

Ponovni zagon strežnika se nikoli ne izvede samodejno. Preverjaj potrebo po
ponovnem zagonu po nadgradnji jedra in spremljaj dnevnik: cron sam ne pošlje
zunanjega obvestila o napaki. Skripte ne morejo zagotoviti odsotnosti novih
ranljivosti ali ustaviti volumetričnega DDoS na domači internetni povezavi.

## Dnevniki v administraciji

`/admin/logs` omogoča izbiro aplikacijskega dnevnika, zadnjih treh rclone
zagonov, posodobitev in certifikatov, Nginx dostopov/napak, SSH/Fail2Ban in
požarnega zidu, stanja vsebnikov, dogodkov obeh Redisov ter zadnjih petih
šifriranih kopij. Rclone dnevnike poišče v `cache/logs/rclone/rclone_sync_*.log`.
Prikaz ne zaganja sinhronizacije in ne preverja vsebine Google Drive; prikaže
dejanske lokalne dnevnike in izide ukazov. Gostiteljski dogodki zajemajo
zadnjih 24 ur. Dnevnik aplikacije se bere ob odprtju strani.

Root-owned `export_admin_logs.py` vsako minuto objavi atomski pregled v
`/var/lib/marinkino-observability/overview.json`. App vidi samo to namensko
mapo prek priklopa samo za branje; nima dostopa do Docker socketa, sistemskih
dnevniških map gostitelja, celotnega stanja nadgradenj ali ključa za kopije.
Priprava pregleda ima zaklep, časovne omejitve ukazov in omejitve izpisa.
Posamezen dnevnik je omejen na 200 vrstic oziroma 64 KiB. Znane skrivnosti
iz konfiguracije, prepoznana gesla, žetoni in obnovitvene povezave se skrijejo.
To ne nadomesti pravila, da se skrivnosti sploh ne zapisujejo v dnevnike.

Dostop zahteva prijavljenega skrbnika zunaj načina predogleda uporabnika.
HTML je ubežan, odgovori se ne predpomnijo. Izbira dnevnika uporablja vnaprej
določene vire; URL ne sprejema poljubnih poti ali ukazov. Stran pokaže čas
pregleda in opozori, ko je starejši od treh minut. Za nove podatke klikni
**Osveži dnevnik**. Po namestitvi teh sprememb ponovno zaženi `setup.sh`,
da namesti izvozni program, priklop in cron.

## Kopije in obnova

Kopije kritičnih JSON/SQLite podatkov in `.env` so šifrirane z age, hranjene
14 dni v `/var/backups/marinkino`. SQLite uporablja konsistenten online
backup. Mediji in Redisov napredek ogledov niso del teh age arhivov; medije
prenaša projektno zrcalo, Redis pa ločen datiran RDB posnetek. Prijavne seje se ob
obnovi ustvarijo znova. Po odločitvi lastnika rclone prenaša tudi `.env`,
credentials, zasebne JSON/SQLite podatke in celotno konfiguracijo certifikatov
v običajni obliki. Izločeni ostanejo razvojne in začasne mape, Git in cache.
Žive kopije SQLite v zrcalu niso nadomestilo za konsistentne posnetke v age
arhivih. Dockerjevi imenovani volumni ležijo zunaj projekta in niso v zrcalu.

**Kopiraj `/etc/marinkino-security/backup.agekey` in šifrirane kopije izven
strežnika.** Ključ in kopija na istem Pi ne pomagata pri izgubi naprave.
Zasebnega ključa ne objavljaj ali shranjuj v repozitorij.

Ključ odklepa arhive `.tar.age`; za zagon strani ga ne potrebuješ. Če Pi
odpove in izgubiš edini izvod ključa, arhivov ni mogoče obnoviti. Shrani
ločeno kopijo ključa v upravitelju gesel ali na drugem varnem mestu.
Rclone najprej kopira dokončane arhive iz `/var/backups/marinkino` v
`gdrive:MarinKino-backups`, za delujoči podatkovni Redis ustvari RDB v
`gdrive:MarinKino-redis`, nato sinhronizira projekt v `gdrive:MarinKino`.
RDB nastane z `redis-cli -e SAVE` in kopiranjem dokončanega `/data/dump.rdb`;
SAVE za čas zapisovanja zadrži ukaze Redisa (največ 128 MiB podatkov).
Prijavnega Redisa ne obnavljaj iz teh kopij; seje se ustvarijo znova.
Arhivi postanejo vidni za prenos šele po uspešnem šifriranju. Stari oddaljeni
arhivi se ne brišejo samodejno; lokalna hramba ostane 14 dni. Ključ shrani
ločeno na Mac oziroma v upravitelja gesel; skripta ga ne nalaga na Drive.

`rclone-sync-gdrive.sh` prenaša prepise in izbrise iz zrcala v datirano mapo
`gdrive:MarinKino-history`. Zgodovina se ne čisti samodejno; spremljaj prostor
na Drive. `--links` shrani simbolne povezave certifikatov kot `.rclonelink`;
pri obnovi prek rclone ponovno uporabi `--links`. Skripta teče kot root, da
lahko bere zasebne datoteke, in uporablja root-owned kopijo rclone nastavitve.
Setup pri omogočenem novem Drive opravilu odstrani stare cron vrstice te
projektne skripte v uporabnikovem/rootovem crontabu. Druga opravila ohrani.
Celoten postopek namestitve je v [navodilih](installation.md#namestitev-na-obstoječem-pi-in-kopije-na-drive).

Preverjanje vsebine brez spreminjanja produkcije:

```sh
sudo age -d -i /etc/marinkino-security/backup.agekey /var/backups/marinkino/IZBRANA.tar.age | tar -tf -
```

Obnavljaj v zasebno začasno mapo in zapise vrni šele po preverjanju ter ob
ustavljeni aplikaciji. Prejšnja Compose konfiguracija z občutljivim okoljem
je v `/var/lib/marinkino-security/previous-compose.json` (0600), Nginx v
`previous-app.conf`. Obnova vsebnikov zahteva ustavitev in odstranitev samo
prizadetih vsebnikov, nato `docker compose -f ... up -d --no-build`; podatkovnih
volumnov ne briši.

## Dostop do Pi brez zaslona

SSH ostane na konfiguriranih vratih iz dovoljenih upravljavskih omrežij.
Privzeto to vključuje lokalna zasebna IPv4 in ULA omrežja ter izvorni naslov
trenutne SSH povezave, če je bil ohranjen pri zagonu setupa. Iz lokalnega
omrežja delujejo terminal SSH, SFTP/SCP in VS Code Remote SSH. Nastavitve
SSH gesel, ključev in posredovanja setup ne spreminja. Samodejni ponovni
zagon Pi ni nastavljen.

Na usmerjevalniku lahko za spletno stran ostaneta preusmerjeni samo vrati
80/443; to ne prepreči lokalnega SSH na vratih 22 oziroma izbranih SSH vratih.
Za dostop iz drugega omrežja je potrebna posebej urejena pot, na primer VPN
na usmerjevalniku in ustrezni `MARINKINO_MGMT_CIDRS`. Privzeta pravila
ne odprejo vrat VNC/RDP, novega VPN ali drugih upravljavskih storitev.
Obstoječi VPN z naslovi zunaj dovoljenih omrežij potrebuje dodatna pravila.
Pred zaprtjem stare SSH seje preveri novo povezavo.

Admin dnevniki so dostopni prek spletnega HTTPS dostopa, dokler delujeta
aplikacija in Nginx. Če stran odpove, za diagnostiko uporabi SSH. Ob izgubi
vseh omrežnih poti potrebuješ fizični dostop do Pi oziroma kartice/diska.

## Skrbniška 2FA

Izberi aplikacijo TOTP. V zasebnem okolju generiraj skrivnost z
`uv run python -c 'import pyotp; print(pyotp.random_base32())'`, jo najprej
vpiši v aplikacijo TOTP in nato v `.env` kot `ADMIN_TOTP_SECRET`.
Ponovno zaženi setup. Skrivnost velja za skrbniške račune; napačna ali že
uporabljena koda zavrne prijavo. Obnovitveni izvodi skrivnosti sodijo v
upravitelja gesel. Aktivacija zahteva ročno vpisovanje v TOTP aplikacijo.

## Primarni tehnični viri

- [Waitress: Unix socket in trusted proxy](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)
- [Docker: požarni zid in posredovan promet](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [Trivy: pregled slik](https://trivy.dev/docs/latest/references/configuration/cli/trivy_image/)

- [DuckDNS: uradni HTTPS GET API](https://www.duckdns.org/spec.jsp)

## Lokalno preverjanje sprememb

Preverjeni so regresijski testi za zasebnost, CSRF, seje, omejitve, varno
pisanje in generirano konfiguracijo ter brskalniški testi urejevalnika,
prijave in predvajalnika. Celotna zbirka vsebuje starejši neuspešen test
`test_next_full_moon_countdown_returns_positive_hours`: pri fazi `0.5`
pričakuje 709 ur, izvorna funkcija in trenutna različica vrneta 0. Izračun
lune ni spremenjen z varnostnimi popravki.

Docker Engine, Nginx in nftables na razvojnem Macu niso na voljo. Njihova
končna preverjanja in izolirani kontejnerski test se izvedejo na Pi znotraj
vzdrževalnega postopka; ta lokalni pregled ne potrjuje že izvedene namestitve.
