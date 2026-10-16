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

Postopek velja za obstoječi Pi z Docker Engine, Compose v2, domeno in .env.
Najprej prenesi vse nove datoteke z Maca prek svojega Git postopka. Ukaze
izvajaj kot običajni uporabnik Pi, poti in uporabniško ime prilagodi namestitvi.
Počakaj, da se trenutno vzdrževanje in stari rclone končata. Ne dodajaj novih
ročnih cron vrstic; setup upravlja načrt in zamenja stare vrstice te skripte.

1. Pripravi trajno terminalno sejo in posodobi kodo:

   ```sh
   sudo apt update
   sudo apt install -y tmux rclone python3
   sudo loginctl enable-linger "$USER"
   tmux new -s marinkino-setup
   cd ~/Desktop/MarinKino
   git pull --ff-only
   ```

   Po prekinitvi uporabi `tmux attach -t marinkino-setup`. Obstoječih .env,
   podatkov in certifikatov ne prepisuj z vzorci. Preveri domene, pošto in
   Turnstile; PUBLIC_BASE_URL naj ustreza HTTPS izvoru WWW_DOMAIN.

2. Preveri povezavo Drive. Če že deluje, ponovna prijava ni potrebna:

   ```sh
   rclone lsd gdrive:
   rclone config file
   ```

   Če manjka, jo ustvari z `rclone config`, z imenom `gdrive`. Za avtorizacijo
   brez brskalnika na Pi sledi postopku rclone za prijavo na drugem računalniku.

3. Samo ob prvi nastavitvi kopiraj konfiguracijo v zasebno mapo root.
   Če ciljna datoteka že obstaja, je NE prepisuj; vsebuje ključe obstoječih kopij.
   Izvorno pot prilagodi izpisu `rclone config file`:

   ```sh
   sudo install -d -m 700 /etc/marinkino-security
   if ! sudo test -e /etc/marinkino-security/rclone.conf; then
       sudo install -o root -g root -m 600 "$HOME/.config/rclone/rclone.conf" /etc/marinkino-security/rclone.conf
   fi
   sudo python3 scripts/secure_backup.py init
   sudo python3 scripts/secure_backup.py check
   ```

   Inicializacija ustvari crypt brez izpisovanja gesel. Ponovitev ohrani ključe.
   Ob napaki ne briši konfiguracije ali prstnega odtisa; obnovi shranjeno kopijo.

4. Pred prvim prenosom shrani rclone.conf izven Pi. Na Pi pripravi kopijo:

   ```sh
   install -d -m 700 "$HOME/.marinkino-recovery"
   sudo install -o "$(id -u)" -g "$(id -g)" -m 600 /etc/marinkino-security/rclone.conf "$HOME/.marinkino-recovery/rclone.conf"
   ```

   Na Macu v istem LAN oziroma prek nastavljenega VPN, z dejanskim IP Pi:

   ```sh
   mkdir -p "$HOME/MarinKino-recovery"
   chmod 700 "$HOME/MarinKino-recovery"
   scp marinko@IP_RPI:.marinkino-recovery/rclone.conf "$HOME/MarinKino-recovery/rclone.conf"
   chmod 600 "$HOME/MarinKino-recovery/rclone.conf"
   test -s "$HOME/MarinKino-recovery/rclone.conf"
   ```

   Kopijo zaščiti tudi na Macu, npr. v upravitelju gesel ali šifrirani shrambi.
   rclone.conf vsebuje dejanske ključe, čeprav jih rclone prikaže kot obscure.
   Tudi Macova mapa za obnovo mora ostati zunaj sinhronizacije z Drive.

5. Preveri načrt, preglej izpisano pot dnevnika, nato prenesi prvo kopijo:

   ```sh
   sudo bash scripts/rclone/rclone-sync-gdrive.sh --project "$PWD" --dry-run
   sudo less IZPISANA_POT_DNEVNIKA
   sudo bash scripts/rclone/rclone-sync-gdrive.sh --project "$PWD"
   ```

   Vse ciljne poti potekajo skozi crypt. Na Drive bo nastala nova mapa
   `MarinKino-encrypted`, z neberljivimi imeni in vsebino. Stare nešifrirane
   mape ostanejo. Velikosti in časi datotek ostanejo vidni ponudniku.

6. Namesti zaščite, vsebnike, admin dnevnike in cron:

   ```sh
   sudo --preserve-env=SSH_CONNECTION bash scripts/setup.sh
   ```

   Prek Connect zadostuje `sudo bash scripts/setup.sh`. Obstoječo povezavo
   ohrani in preveri novo povezavo. Setup kriptografske ključe ohrani in namesti
   root-owned kopije skript. Če rclone.conf še ni nastavljen, oblačni cron
   ostane izključen; po konfiguraciji ponovno zaženi setup.

7. Shrani še ključ age, ki ga je ustvarilo vzdrževanje. Na Pi:

   ```sh
   sudo install -o "$(id -u)" -g "$(id -g)" -m 600 /etc/marinkino-security/backup.agekey "$HOME/.marinkino-recovery/backup.agekey"
   ```

   Na Macu:

   ```sh
   scp marinko@IP_RPI:.marinkino-recovery/backup.agekey "$HOME/MarinKino-recovery/backup.agekey"
   chmod 600 "$HOME/MarinKino-recovery/backup.agekey"
   test -s "$HOME/MarinKino-recovery/backup.agekey"
   ```

   Za obnovo oblačnih datotek potrebuješ rclone.conf; za dodatno šifrirane age
   arhive še backup.agekey. Skripte ju ne nalagajo na Drive.

8. Preveri delovanje, prenesi nove arhive in preveri njihovo integriteto:

   ```sh
   sudo docker compose ps
   sudo cat /var/lib/marinkino-security/status.json
   sudo cat /etc/cron.d/marinkino-security
   sudo fail2ban-client status
   sudo /usr/local/lib/marinkino/rclone-sync-gdrive.sh --project "$PWD"
   sudo rclone --config /etc/marinkino-security/rclone.conf cryptcheck /var/backups/marinkino marinkino_secure:archives --include '*.tar.age' --one-way
   ```

   V brskalniku preveri prijavo, predvajanje, osnutke in `/admin/logs`.
   Dnevnik vključuje stanje šifriranja oblačnih kopij. Logične poti so
   `marinkino_secure:project`, `:history`, `:archives` in `:redis` (vse z istim
   predponom `marinkino_secure`). Podatkovni Redis dobi datiran RDB posnetek,
   prijavne seje se ob obnovi ustvarijo znova. SQLite v age arhivih je
   konsistenten; živa datoteka v zrcalu tega ne zagotavlja.

9. Preizkusi obnovo na ločeno mesto, preden izbrišeš stare kopije:

   ```sh
   sudo install -d -m 700 /var/lib/marinkino-restore-check
   sudo rclone --config /etc/marinkino-security/rclone.conf copyto marinkino_secure:project/.env /var/lib/marinkino-restore-check/env.restored
   sudo cmp .env /var/lib/marinkino-restore-check/env.restored
   sudo rclone --config /etc/marinkino-security/rclone.conf lsf marinkino_secure:archives
   ```

   Izberi dejanski arhiv iz zadnjega izpisa:

   ```sh
   sudo rclone --config /etc/marinkino-security/rclone.conf copyto marinkino_secure:archives/IZBRANA.tar.age /var/lib/marinkino-restore-check/IZBRANA.tar.age
   sudo age -d -i /etc/marinkino-security/backup.agekey /var/lib/marinkino-restore-check/IZBRANA.tar.age | tar -tf -
   ```

   To preveri prenos in oba ključa, produkcije ne prepiše. Za polno obnovo
   najprej uporabi `rclone copy marinkino_secure:project ZASEBNA_MAPA --links`
   z ustrezno `--config`; podatke preglej in vrni ob ustavljeni aplikaciji.
   Na novem Pi namesti rclone, obnovi rclone.conf kot root 0600, poženi
   `secure_backup.py init` (uporabi shranjene ključe) in obnovi backup.agekey.
   Ne izvajaj init z na novo prazno konfiguracijo za obstoječo šifrirano kopijo.

10. Šele po uspešni obnovi preglej stare navadne mape na Drive: `MarinKino`,
    `MarinKino-history`, `MarinKino-redis` in morebitne druge kopije .env,
    credentials ali ključev. Odstrani odvečne nešifrirane izvode in izprazni koš;
    novo mapo `MarinKino-encrypted` ohrani. Izbris starih kopij ni avtomatiziran.
    Če so bile skrivnosti izpostavljene drugim, jih zamenjaj pri ponudnikih.

Vzdrževanje teče ob 03:17, certifikati ob 05:11 in 17:11, Drive ob 07:00 po
času Pi. Lokalni age arhivi ostanejo 14 dni; zgodovina in arhivi na Drive se
ne brišejo samodejno. Spremljaj prostor in rezultate v administraciji.
Ob spremembah kode prenesi spremembe in ponovno zaženi setup. Ne ponavljaj
kopiranja stare uporabniške rclone.conf čez konfiguracijo, ki že vsebuje crypt.

## Uporaba lastne domene

DuckDNS uporabljaj kot dinamičen DNS samo, če nimaš fiksnega IP ali želiš hitro testno rešitev.
Za produkcijsko rabo priporočam svojo domeno, kjer upravljaš DNS zapise pri ponudniku domene.

1. Nastavi A zapis na svoj fiksni javni IP naslov.
2. Če imaš IPv6, dodaj tudi AAAA zapis.
3. Za boljšo varnost nastavi tudi CAA zapise za izdajo SSL certifikatov.
4. Če želiš, lahko lastno domeno usmeriš prek CNAME na DuckDNS poddomeno, vendar je najbolj stabilna rešitev neposredni A/AAAA zapis na ciljni strežnik.

Za HTTPS uporabi certbot ali drugo TLS rešitev z lastno domeno, ne pa URL-ja DuckDNS kot primarno končno ime. DuckDNS naj ostane pomočnik za dinamičen DNS in začasno preusmeritev, če nimaš statičnega naslova.
