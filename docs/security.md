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
  stare seje tudi po povrnitvi Redisovih zapisov. Največ deset naprav; sedem dni nedejavnosti, absolutno največ
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

Privzeti `Referrer-Policy` je `same-origin`: brskalnik ohrani Referer za
obrazce na istem izvoru, zunanjim stranem pa ga ne pošilja. HTTPS obrazci
ohranijo Flask-WTF `WTF_CSRF_SSL_STRICT`; politika `no-referrer` na prijavni
strani bi blokirala veljaven POST. Nginx uporabi aplikacijsko politiko, če je
nastavljena, sicer `same-origin`, in odstrani podvojeno upstream glavo.
Občutljive preusmeritve lahko še vedno izberejo `no-referrer`; obrazec za
naročnine uporablja `same-origin`. Izolirani test preveri dejansko HTTPS
prijavo ter zavrnitev veljavnega CSRF žetona brez Referer ali s tujim izvorom.

`/etc/cron.d/marinkino-security` vsebuje:

- vsak dan ob **03:17**: vzdrževanje in preverjena nadgradnja;
- ob **05:11 in 17:11**: enkraten Certbot renew + preverjen Nginx reload;
- vsakih pet minut: ponoven izračun LAN pravil, tudi po spremembi IPv6 predpone;
- vsakih deset minut: DuckDNS, kadar sta domena in žeton nastavljena.
- vsako minuto: omejen pregled gostitelja za skrbniški prikaz dnevnikov.
- ob **07:00**: prenos arhivov in zrcala projekta na Drive, če obstaja
  `/etc/marinkino-security/rclone.conf` z veljavnim šifriranim mestom `marinkino_secure`.

Cron izvaja root-owned kopije v `/usr/local/lib/marinkino`. Po spremembi teh
skript v repozitoriju ponovno zaženi setup, da namesti nove kopije.
Sočasni zagoni se preprečijo s `flock`.

Trivy uporablja zasebno začasno mapo na disku v
`/var/lib/marinkino-security/run.*/trivy-tmp`, ne omejenega RAM tmpfs.
Prenos baze ranljivosti in razpakiranje slik lahko presežeta 64 MB; začasna
mapa se odstrani tudi ob napaki. Baza ostane v namenskem cache za ponovne
preglede. Za pregled sta potrebna prostor za izvoz slike in začasne datoteke.

Certbot teče enkratno kot UID/GID 0 z odstranjenimi capabilities in dodanimi
`DAC_OVERRIDE`, `FOWNER`, `CHOWN`. Te omogočijo zaklepanje in posodobitev
obstoječih certifikatov, tudi če datoteke pripadajo staremu UID. Vse ostale
capabilities ostanejo izključene; `no-new-privileges` ostane vključen.
Zasebnim ključem zaradi napake `.certbot.lock: Permission denied` ne odpiraj
pravic za vse uporabnike. Po spremembi Compose konfiguracije ponovi setup.

Dnevni postopek naredi šifrirano kopijo, posodobi sistemske pakete in Docker
slike, osveži kompatibilne Python/JS odvisnosti, zgradi kandidata in ga
preveri. OSV zavrne znane ranljivosti nameščenih Python/JS paketov; Trivy
zavrne popravljive HIGH/CRITICAL ranljivosti slik. Nedosegljiv pregled ali
neuspešen test prepreči namestitev kandidata. Major različice Python,
Redis in JS se menjajo po ročnem preverjanju združljivosti.

Redis za oba vsebnika dobi lastno kandidatno sliko iz `redis:7-alpine` in
`configuration/redis/Dockerfile`. Vsak pregled ponovno izvede `apk upgrade
--no-cache`, da zajame popravke Alpine paketov, tudi kadar uradna Redis
slika še ni bila ponovno zgrajena. Kandidata najprej pregleda Trivy, nato
ga uporabljajo izolirani test, migracija ter podatkovni in prijavni Redis.
Uspešno nameščeni kandidat dobi oznako `marinkino-redis:current`, privzeti
cilj Compose. `MARINKINO_REDIS_IMAGE` med vzdrževanjem izbere točnega
kandidata. Čiščenje ohrani uporabljene in obnovitvene slike obeh repozitorijev.
Če repozitorij popravka še ne ponuja ali pregled še vedno najde popravljivo
HIGH/CRITICAL ranljivost, se namestitev še vedno ustavi.

Certbot se prav tako gradi lokalno v `configuration/certbot-image/Dockerfile`:
posodobljena Python 3.12 slim osnova in ločen virtualenv s svežim Certbotom
ter njegovimi odvisnostmi. Graditelj uv in pip nista vključena v končno sliko.
S tem vzdrževanje ni odvisno od zastarelih knjižnic v uradni sliki Certbot.
Trivy preveri kandidata, nato se preveri CLI in izvede obnova certifikatov.
Oznaka `marinkino-certbot:current` se premakne šele po uspešnem vzdrževanju;
običajni certifikatni cron uporablja to preverjeno sliko. Ob prvi izdaji,
ko certifikat še ne obstaja, setup zgradi ločeno sliko `bootstrap`; celoten
pregled in namestitev sledita v rednem vzdrževanju. Nginxov pripravljalni
pregled ima `DAC_OVERRIDE` za branje obstoječih zasebnih ključev, enako kot
dejanski Nginx vsebnik.

Nginxov začasni runtime priklop uporablja `/run`, ne njegove Alpine povezave
`/var/run`. Tako priklop prek povezave ne prekrije skupnega volumna
`/run/marinkino`, v katerem aplikacija odpre Unix socket. Po zagonu se
iz Nginx vsebnika preveri obstoj socketa, nato še HTTPS povezava do aplikacije.

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

Oblačna kopija loči zasebne in običajne datoteke. Pravila so v
`scripts/rclone/rclone-sensitive.txt`; ista pravila vključijo zasebne datoteke
v šifrirano kopijo in jih izključijo iz navadne. `.env` in različice, credentials,
ključi/certifikati, uporabniki, naročniki, SQLite/DB datoteke (tudi WAL/SHM),
zasebni glasbeni podatki ter filmski JSON metapodatki gredo skozi `rclone crypt`
v `marinkino_secure:project`, ki ovija `gdrive:MarinKino-encrypted`.
Filmski JSON vsebuje tudi e-pošto, avtorje komentarjev in uporabniške ocene.
Redis in age arhivi prav tako ostanejo šifrirani. Mediji, koda, dokumentacija
in ostali običajni podatki gredo nešifrirano v `gdrive:MarinKino`, zgodovina
teh datotek v `gdrive:MarinKino-history`. Obstoječi filmi na tej isti poti se
ne prenašajo znova zaradi šifriranja; rclone še vedno preveri razlike.
To je razvrstitev po poteh/imenih, ne pregled vsebine: skrivnosti ne sodijo v
kodo, dokumentacijo ali poljubno poimenovane datoteke. Nove zasebne poti dodaj
v skupni seznam pred prenosom. Cache, začasne datoteke in obnovitveni ključi
so izločeni iz obeh kopij. Skripta zavrne prenos, če seznam manjka.
Velikost datotek in časi sprememb ostanejo vidni ponudniku; POSIX metadata
se ne nalagajo z `--metadata`. Pi potrebuje dostop do aktivnih skrivnosti;
ta nastavitev ne šifrira njegovega diska in ne varuje pred napadalcem z root.

`scripts/secure_backup.py init` enkrat ustvari dva neodvisna naključna
384-bitna skrivna niza. V rclone.conf sta shranjena v rclone obscure obliki,
ki sama ni varnostno šifriranje. Datoteka zato ostane root-owned 0600 zunaj
projekta, v `/etc/marinkino-security` (0700), in ni priklopljena aplikaciji.
Ponovni setup ključe ohrani. Inicializacija ima zaklep; lokalni prstni odtis
zavrne nenamerno odstranitev/zamenjavo ključev. Ne prepisuj konfiguracije z
uporabniško kopijo po prvi nastavitvi šifriranja.

Pred vsakim prenosom se preverijo tip crypt, varen cilj, šifriranje vsebine
in imen ter ujemanje ključev. Manjkajoča/spremenjena nastavitev ustavi prenos.
RCLONE okoljske preglasitve se odstranijo; vsak zagon uporablja zasebni
posnetek preverjene konfiguracije. Ključi ne potujejo prek argumentov ukazov
in se ne izpisujejo. Izvirni rclone.conf se med kopiranjem ne prepisuje.

`marinkino_secure:archives` vsebuje age arhive kritičnih JSON/SQLite podatkov
in `.env`. SQLite posnetki so konsistentni, arhivi so lokalno hranjeni 14 dni
v `/var/backups/marinkino` in objavljeni za prenos šele po šifriranju.
`marinkino_secure:project` vsebuje samo zasebne poti. Živa SQLite datoteka
v zrcalu ne nadomesti konsistentnega age
posnetka. Tudi credentials dobijo lokalno 0700 za mape in 0600 za datoteke.

`marinkino_secure:redis` vsebuje datirane RDB posnetke delujočega podatkovnega
Redisa, ki leži v Docker volumnu zunaj projekta. `redis-cli -e SAVE` pred
kopiranjem dokonča RDB; med zapisovanjem zadrži Redisove ukaze. Prijavnih sej
iz teh kopij ne obnavljaj. Če Redis ne deluje, se odsotnost novega posnetka
zapiše v dnevnik. `marinkino_secure:history` ohrani prepisane/izbrisane datoteke.
Oddaljeni arhivi in zgodovina se ne čistijo samodejno; spremljaj prostor.
Povezave certifikatov se shranijo z `--links`; enako možnost uporabi ob obnovi.

**Na Mac oziroma v upravitelja gesel shrani oba obnovitvena dokumenta:**

- `/etc/marinkino-security/rclone.conf`: ključi crypt in prijava v Drive;
- `/etc/marinkino-security/backup.agekey`: dodatni ključ za age arhive.

Nobene od teh datotek ne shranjuj v projekt, Git ali isto oblačno kopijo.
Izguba rclone.conf pomeni izgubo dostopa do celotne šifrirane oblačne kopije;
za age arhive potrebuješ še backup.agekey. Prstni odtis ni nadomestilo ključev.
Pred prehodom preveri konfiguracijo in shrani rclone.conf izven Pi. Pred
odstranitvijo starih kopij preveri tudi prenos, odklepanje in obnovo na drugo
mesto. Vse varne korake opisujejo [navodila](installation.md#namestitev-na-obstoječem-pi-in-kopije-na-drive).

**Stare nešifrirane skrivnosti ostanejo nešifrirane.** Nova nastavitev jih ne
pretvori in jih ne briše samodejno. Po preverjeni obnovi preglej mape
MarinKino, MarinKino-history in MarinKino-redis ter druge izvode zasebnih
konfiguracij. Odstrani samo stare nešifrirane zasebne datoteke in njihove
zgodovinske različice, nato izprazni koš. Navadne medije in projekt ohrani.
Tudi že preneseni šifrirani mediji ostanejo; ne nalagajo se več v crypt.
Če so bile skrivnosti izpostavljene, jih zamenjaj pri ponudnikih; samo izbris ne
razveljavi ukradenega žetona. Za Google račun uporabi passkey ali močno 2FA.

Obnovi najprej v zasebno začasno mapo, nikoli neposredno čez delujočo stran.
Prejšnja Compose konfiguracija je v `/var/lib/marinkino-security/previous-compose.json`
(0600), Nginx v `previous-app.conf`. Sistemske posodobitve in zapisi podatkov
niso del avtomatske povrnitve vsebnikov. Dockerjevih volumnov ne briši.

Pred preklopom se slike delujočih vsebnikov ohranijo pod zasebnimi lokalnimi
oznakami `marinkino-rollback:security-*`; shranjeni Compose uporablja te
oznake. Če prvotni manifest ni več dostopen, se poskusi `docker commit` iz
obstoječega vsebnika. Ta lahko vsebnik kratko zaustavi; priklopljeni podatki
niso del te slike in ostanejo v izvirnih bind mapah/volumnih. Slike lahko
vsebujejo skrivnosti iz okolja, zato jih ne objavljaj v registrih.
Če ohranitev ali preverjanje slike ne uspe, se namestitev ustavi pred
preklopom. Razpoložljivost slik in veljavnost obnovitvene konfiguracije se
preverita tudi pred odstranitvijo vsebnikov ob povrnitvi. Ob neuspešnem
vzdrževanju se slike ne čistijo; zasebni posnetki ostanejo v `run.*` mapah.
Snapshot zajema delujoče vsebnike; po prejšnjem izpadu lahko teh ni več,
zato prazen snapshot ne pomeni zagotovljene povrnitve prejšnje strani.

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
