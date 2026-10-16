# Nastavitev MarinKino

Tu so posodobljena navodila za lokalno in strežniško namestitev.

## Sistemske zahteve
* Linux (npr. Ubuntu 24.04 ali Raspberry Pi OS)
* Python 3.12
* FFMPEG
* Rezerviran IP za strežnik (na routerju nastavi rezerviran IP za MAC naslov mrežne kartice svojega strežnika)
* Port forwarding 80-80 (notranji in zunanji vhod) in 443-443 nastavljen na routerju za rezerviran IP strežnika
* DuckDNS poddomena, če nimaš fiksnega IP

## Lokalna namestitev in razvoj

### 1. Kloniraj repozitorij
```
git clone https://github.com/AnzeMarinko/MarinKino.git
cd MarinKino
chmod +x ./scripts/setup.sh
```

### 2. Pripravi konfiguracijo
1. Kopiraj `.env.example` v `.env`:
   ```
   cp .env.example .env
   ```
2. Uredi `.env` in nastavi svoje vrednosti.
   Gibanje v lokalnem razvoju uporablja ločeno bazo
   `data/fitness-development.sqlite3`. Produkcijski Docker Compose uporablja
   `data/fitness.sqlite3`, zato preizkušanje lokalnih sprememb ne spreminja
   produkcijskih zapisov. Pot lahko lokalno preglasiš z `FITNESS_DATABASE`.
3. Če uporabljaš Google AI prevajanje, dodaj `credentials/gen-lang-client.json`.
   Credential datotek ne kopiraj v Docker image. Uporablja jih samo
   ločeno okolje za pripravo vsebin (`uv sync --extra preparation`).
   Javni spletni vsebnik teh ključev ne prejme. Če je credential že bil vgrajen v prejšnji image,
   ga po namestitvi rotiraj pri ponudniku.
4. Za naročanje na blog ustvari Cloudflare Turnstile widget in v `.env` dodaj:
   ```
   TURNSTILE_SITE_KEY=...
   TURNSTILE_SECRET_KEY=...
   TURNSTILE_HOSTNAME=www.example.si
   PUBLIC_BASE_URL=https://www.example.si
   ```
   V produkciji sta ključa in javni URL obvezni; `TURNSTILE_HOSTNAME` mora
   ustrezati domeni, registrirani pri Turnstile. Prijave se v seznam naročnikov
   dodajo šele po kliku na potrditveno povezavo v e-pošti; povezava velja 24 ur.

### 3. Ustvari virtualno okolje in namesti odvisnosti
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install uv
uv sync --extra dev
pre-commit install
pre-commit run --all-files
```

### 3.1. Napredna analiza glasbe z librosa (opcijsko)

Za tempo, tonaliteto, akorde in naprednejše značilnosti namesti opcijsko
odvisnost:

```
uv pip install -e ".[smart-playlists]"
```

Nato nastavi analizni backend v okolju:

```
AUDIO_ANALYZER=auto
```

Možne vrednosti so `numpy`, `librosa` (zahteva namestitev) in
`auto` (privzeto; uporabi librosa, če je na voljo, sicer NumPy/FFmpeg
fallback).
Analiza se izvede pri predpripravi oziroma prvem osveževanju metadata in se
shrani v HLS `metadata.json`.

### 3.2. Semantična analiza naslovov z Gemini (opcijsko)

Pri predpripravi lahko Gemini glede na naslov, izvajalca in album doda
semantične ocene za smart playlist:

```
GEMINI_TOKEN=...
GEMINI_MODEL=gemini-2.0-flash
```

Klic se izvede samo pri ustvarjanju oziroma ponovni predpripravi
`metadata.json`, ne med predvajanjem. Če ključ ni nastavljen ali API ni
dosegljiv, audio analiza in predvajanje delujeta naprej brez semantične ocene.
Semantična komponenta ima pri izbiri naslednje pesmi privzeto težo `0.2`.

### 3.3. Jeziki javnega bloga in naročnin

Javni blog podpira slovenščino ter prevode v angleščino, nemščino,
španščino, italijanščino, francoščino, portugalščino, poljščino,
ukrajinščino, arabščino, poenostavljeno kitajščino in japonščino.
Spustni izbirnik z zastavicami in imeni jezikov v glavi strani odpre brezplačni
[Google Translate za spletne strani](https://support.google.com/translate/answer/2534559)
v novem zavihku. Prevede seznam, objavljene objave in pravne strani skupaj
z glavo, navigacijo in nogo. Opozorilo o avtomatskem prevodu je vidno samo
na prevedeni strani, v izbranem jeziku. Slovenski izvirnik nima opozorila
in ostane v prvotnem zavihku.
Osnutki in zasebne strani nimajo izbirnika.

Naslov izvirnika izhaja iz `PUBLIC_BASE_URL` ali `WWW_DOMAIN`; nastavljena
domena mora biti javno dosegljiva. Google prejme samo javni naslov in
preverjeno oznako jezika `lang`, brez drugih parametrov ali potrditvenih
žetonov. Aplikacija ne uporablja plačljivega prevajalskega API-ja in ne
shranjuje prevodov objav; njihovo osveževanje upravlja Google. Pravilo
obnovitve ob spremembi objave ali po 30 dneh bi bilo potrebno pri lastnem
predpomnilniku za API.

Gumb za naročanje odpre `/blog/subscribe?lang=…` na izvorni domeni.
Obrazec je lokaliziran in ponuja spremembo jezika obvestil. JavaScript
prenese tudi jezik z Googlove prevedene strani ter se izogne prepisovanju
povezav skozi proxy. CSRF, Turnstile, omejevanje poskusov in potrjevanje
naslova ostanejo vključeni. Potrditveni žeton velja 24 ur in se uporabi
samo enkrat. Potrditvene povezave se nikoli ne prevajajo prek Googla.

`data/blog_subscribers.json` uporablja zapise:

```json
[{"email": "reader@example.com", "language": "en"}]
```

Stari seznami e-poštnih naslovov se ob branju obravnavajo kot slovenski
naročniki; ob naslednjem shranjevanju dobijo novo obliko. Ponovna prijava z
istim naslovom in drugim jezikom spremeni nastavitev šele po potrditvi nove
povezave. Stare, še veljavne potrditvene povezave ostanejo uporabne.

Potrditve in obvestila imajo lokaliziran naslov, HTML in besedilno različico;
arabščina uporablja smer RTL. Besedila so v `src/blog_i18n.py`, zato
prevajalskih stroškov ni. Slovensko obvestilo o objavi ohrani naslov in
povzetek; tujejezično pošlje kratko lokalizirano obvestilo s povezavo do
prevedene objave, brez neprevedenega naslova ali povzetka.

Obvestila se pošiljajo ločeno za vsak jezik, naslovniki ostanejo v BCC.
Uspešno poslane jezikovne skupine se zabeležijo v `mail_languages_sent`,
zato jih ponovitev po napaki druge skupine ne pošlje znova. `mail_date`
se nastavi po uspehu vseh skupin. Delna zavrnitev naslovnikov prek SMTP
ostane napaka te skupine; pri ponovitvi lahko že sprejeti naslovniki te
skupine prejmejo podvojeno sporočilo.

### 4. Namesti Redis
```
sudo apt update && sudo apt install -y redis-server
sudo systemctl enable --now redis-server
```

### 4.1. Prijavljene naprave

Vsak uporabnik ima lahko največ **5 hkrati prijavljenih naprav**, tudi
administrator. Napravo predstavlja posamezna brskalniška seja z naključnim
`device_id` v podpisanem sejnem piškotku. ID ni povezan s FingerprintJS.
Šesta prijava je zavrnjena z opozorilom, naj se uporabnik odjavi na eni od
drugih naprav. Odjava takoj sprosti mesto.

Redis hrani ID-je in čas zadnje uporabe v urejenem naboru
`auth:devices:<uporabnik>`. Preverjanje omejitve in vpis naprave sta atomska,
zato omejitev velja tudi pri sočasnih prijavah. Vsaka preverjena uporaba seje
podaljša njeno veljavnost za **30 dni**. Po 7 dneh neaktivnosti seja ni več
veljavna in ne zaseda mesta: potekli vnosi se odstranijo ob preverjanju ali
novi prijavi, celoten neaktiven nabor pa poteče s TTL. Dodaten cron ni potreben.

Ob uvedbi omejitve se morajo uporabniki z obstoječimi sejami brez `device_id`
ponovno prijaviti. Prijava uporablja trajni sejni piškotek; stari
`remember_token` se odstrani in ne more obnoviti potekle naprave. Tudi izguba
evidence naprav v Redis zahteva ponovno prijavo.

Regresijski testi v okolju z nameščenimi odvisnostmi projekta:

```sh
python -m pip install pytest 'fakeredis[lua]'
PYTHONPATH=src python -m pytest tests/test_device_sessions.py tests/test_device_auth.py
```

### 5. Zaženi aplikacijo lokalno
```
uv run python src/app.py
```

Ob prvem zagonu se ustvari začetni skrbniški račun. Enkratno geslo je
v `data/.initial-admin-password` (pravice `0600`); v JSON se shrani samo
zgoščena vrednost. Prva prijava zahteva menjavo gesla. Nato datoteko z
enkratnim geslom izbriši. Razvoj uporablja `data/test_users.json`.

### 6. Dodaj vsebine
V mape `movies`, `memes` in `music` dodaj datoteke glede na [navodila za dodajanje datotek](docs/adding_data.md).

### 7. Pravice in strežniška namestitev

Pravice nastavi varnostni setup. Ne uporabljaj `chmod -R 777` ali javnih ACL
na celotni mapi `data`, ker vsebuje gesla, naročnike in zasebne zapise.

Docker Engine in Compose v2 morata biti že nameščena. Na Raspberry Pi zaženi:

```sh
sudo --preserve-env=SSH_CONNECTION bash scripts/setup.sh
```

Setup uredi dovoljenja, vsebnike, TLS, požarni zid, Fail2Ban in cron.
Podrobnosti posodobitev, obnovitev in šifriranih kopij:
[varnost in vzdrževanje](security.md).

### 3. Posodabljanje aplikacije po spremembah
Po spremembah v `src`, `.env`, Dockerfile ali `docker-compose.yml` ponovno pregradi:
```
sudo --preserve-env=SSH_CONNECTION bash scripts/setup.sh
```

Shranjevanje blog objave sprejme zahteve do 40 MB. Na obstoječem strežniku
nastavi `client_max_body_size 40m;` v `configuration/nginx/conf/app.conf`
in ponovno naloži Nginx:
```
docker compose exec nginx nginx -s reload
```

## Namestitev na obstoječem Pi in kopije na Drive

Postopek velja za obstoječi Pi z Docker Engine, Compose v2, delujočo domeno
in obstoječim `.env`. Ukaze izvajaj kot običajni uporabnik Pi. Pot projekta
prilagodi svoji namestitvi. Spremembe morajo biti najprej prenesene z Maca;
`git pull` jih dobi šele po commit/push.

1. Namesti pripomočka in odpri trajno terminalno sejo. To omogoča nadaljevanje
   namestitve, če nadgradnja Connect prekine povezavo:

   ```sh
   sudo apt update
   sudo apt install -y tmux rclone
   sudo loginctl enable-linger "$USER"
   tmux new -s marinkino-setup
   cd ~/Desktop/MarinKino
   git pull --ff-only
   ```

   Po prekinitvi se poveži nazaj in izvedi `tmux attach -t marinkino-setup`.
   `.env`, podatkov in certifikatov ne prepisuj z vzorci. V `.env` preveri
   `MAIN_DOMAIN`, `WWW_DOMAIN`, `PUBLIC_BASE_URL`, pošto in Turnstile.

2. Preveri obstoječi Drive remote. Če `gdrive:` že deluje, ponovne prijave
   ne potrebuješ:

   ```sh
   rclone lsd gdrive:
   rclone config file
   ```

   Če remote manjka, ga ustvari z `rclone config`: ime `gdrive`, Google Drive
   in prijava v svoj račun. Za prijavo brez brskalnika na Pi sledi navodilom
   rclone za avtorizacijo na Macu. Pot konfiguracije pokaže `rclone config file`.

3. Ustvari zasebno kopijo konfiguracije za samodejna root opravila. Če je
   konfiguracija drugje, zamenjaj izvorno pot. Obstoječo namensko konfiguracijo
   prepiši samo, kadar želiš posodobiti njene nastavitve/prijavo:

   ```sh
   sudo install -d -m 700 /etc/marinkino-security
   sudo install -o root -g root -m 600 "$HOME/.config/rclone/rclone.conf" /etc/marinkino-security/rclone.conf
   sudo rclone --config /etc/marinkino-security/rclone.conf lsd gdrive:
   ```

4. Pred prvo nadgradnjo preveri načrt prenosa, nato zaženi kopiranje:

   ```sh
   sudo bash scripts/rclone/rclone-sync-gdrive.sh --project "$PWD" --dry-run
   sudo bash scripts/rclone/rclone-sync-gdrive.sh --project "$PWD"
   ```

   Skripta izpiše pot dnevnika. Prvi ukaz pregleda dejanja brez spreminjanja
   Drive; pred drugim preglej izpis z `sudo less IZPISANA_POT_DNEVNIKA`.
   V zrcalo so vključeni `.env`, zasebni podatki, credentials in certifikati.
   Začasni cache, okolja Python, build in Git ostanejo izločeni. Če želiš
   kopijo trenutnega stanja produkcijskih datotek pred prenosom nove kode,
   izvedi dodatno kopiranje tudi pred `git pull`.

5. Namesti zaščite, posodobitve, vsebnike, admin dnevnike in cron:

   ```sh
   sudo --preserve-env=SSH_CONNECTION bash scripts/setup.sh
   ```

   Prek Connect zadostuje `sudo bash scripts/setup.sh`. Prvo povezavo ohrani;
   po uspehu preveri novo SSH/Connect povezavo. Setup ohrani obstoječe močne
   ključe, podatke in certifikate. Vzdrževanje teče ob 03:17, certifikati ob
   05:11 in 17:11, Drive ob 07:00 po času Pi. Root-owned kopije skript so v
   `/usr/local/lib/marinkino`; ob spremembi skript ponovno zaženi setup.

6. Preveri delovanje in kopiraj nove šifrirane arhive na Drive:

   ```sh
   sudo docker compose ps
   sudo cat /var/lib/marinkino-security/status.json
   sudo cat /etc/cron.d/marinkino-security
   sudo fail2ban-client status
   sudo /usr/local/lib/marinkino/rclone-sync-gdrive.sh --project "$PWD"
   sudo rclone --config /etc/marinkino-security/rclone.conf check /var/backups/marinkino gdrive:MarinKino-backups --include '*.tar.age' --one-way
   ```

   V brskalniku preveri prijavo, predvajanje in `/admin/logs`. Na Drive so:
   `MarinKino` (zrcalo), `MarinKino-history` (prepisi/izbrisi) in
   `MarinKino-backups` (datirani age arhivi) in `MarinKino-redis` (datirani
   RDB posnetki delujočega podatkovnega Redisa). Arhivi vsebujejo konsistentne
   SQLite posnetke in kritične JSON podatke; neposredna kopija žive baze v
   zrcalu tega ne zagotavlja. Zapis RDB za kratek čas zadrži Redisove ukaze;
   prijavne seje se ob obnovi ustvarijo znova.

7. Shrani ključ za obnovo izven Pi. Na Pi pripravi zasebno kopijo za prenos:

   ```sh
   install -d -m 700 "$HOME/.marinkino-recovery"
   sudo install -o "$(id -u)" -g "$(id -g)" -m 600 /etc/marinkino-security/backup.agekey "$HOME/.marinkino-recovery/backup.agekey"
   ```

   Nato na Macu, z dejanskim IP in uporabniškim imenom Pi:

   ```sh
   mkdir -p "$HOME/MarinKino-recovery"
   chmod 700 "$HOME/MarinKino-recovery"
   scp marinko@IP_RPI:.marinkino-recovery/backup.agekey "$HOME/MarinKino-recovery/backup.agekey"
   chmod 600 "$HOME/MarinKino-recovery/backup.agekey"
   test -s "$HOME/MarinKino-recovery/backup.agekey"
   ```

   Ključ lahko shraniš tudi v upravitelju gesel. Ni potreben za delovanje
   strani, potreben je za odklepanje `.tar.age`. Skripta ga ne nalaga na Drive.

8. Preveri odklepanje enega arhiva, brez spreminjanja podatkov:

   ```sh
   sudo ls -lh /var/backups/marinkino
   sudo age -d -i /etc/marinkino-security/backup.agekey /var/backups/marinkino/IZBRANA.tar.age | tar -tf -
   ```

   Zamenjaj `IZBRANA.tar.age` z dejanskim imenom. Lokalno ostane 14 dni
   arhivov; zgodovina in arhivi na Drive se ne brišejo samodejno. Spremljaj
   prostor in rezultat dnevnih opravil v administraciji. Novih cron vrstic
   za ta opravila ne dodajaj ročno.

## Uporaba lastne domene

DuckDNS uporabljaj kot dinamičen DNS samo, če nimaš fiksnega IP ali želiš hitro testno rešitev.
Za produkcijsko rabo priporočam svojo domeno, kjer upravljaš DNS zapise pri ponudniku domene.

1. Nastavi A zapis na svoj fiksni javni IP naslov.
2. Če imaš IPv6, dodaj tudi AAAA zapis.
3. Za boljšo varnost nastavi tudi CAA zapise za izdajo SSL certifikatov.
4. Če želiš, lahko lastno domeno usmeriš prek CNAME na DuckDNS poddomeno, vendar je najbolj stabilna rešitev neposredni A/AAAA zapis na ciljni strežnik.

Za HTTPS uporabi certbot ali drugo TLS rešitev z lastno domeno, ne pa URL-ja DuckDNS kot primarno končno ime. DuckDNS naj ostane pomočnik za dinamičen DNS in začasno preusmeritev, če nimaš statičnega naslova.
