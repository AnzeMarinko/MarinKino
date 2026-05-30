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
3. Če uporabljaš Google AI prevajanje, dodaj `credentials/gen-lang-client.json`.

### 3. Ustvari virtualno okolje in namesti odvisnosti
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install uv
uv install .
pre-commit install
pre-commit run --all-files
```

### 4. Namesti Redis
```
sudo apt update && sudo apt install -y redis-server
sudo systemctl enable --now redis-server
```

### 5. Zaženi aplikacijo lokalno
```
uv run python src/app.py
```

Ob prvem zagonu se ustvari `data/users.json` z začetnim uporabnikom. Po prvi prijavi:
* ročno spremeni uporabniško ime administratorja in posodobi e-naslov,
* shrani in odstrani začetno geslo `initial_password`.

### 6. Dodaj vsebine
V mape `movies`, `memes` in `music` dodaj datoteke glede na [navodila za dodajanje datotek](docs/adding_data.md).

### 7. Nastavi pravice za `data` mapo
```
sudo apt-get install -y acl
sudo setfacl -R -d -m o::rx ./data
sudo setfacl -R -m o::rx ./data
```

## Strežniška namestitev

### 1. Nastavi Fail2Ban
```
sudo apt update && sudo apt install -y fail2ban
```

Kopiraj konfiguracijske datoteke iz repozitorija v `/etc/fail2ban`:
```
sudo cp configuration/fail2ban/filter.d/nginx-404.conf /etc/fail2ban/filter.d/nginx-404.conf
sudo cp configuration/fail2ban/filter.d/marinkino-auth.conf /etc/fail2ban/filter.d/marinkino-auth.conf
sudo cp configuration/fail2ban/jail.local /etc/fail2ban/jail.local
```

Zaženi in preveri:
```
sudo systemctl restart fail2ban
sudo fail2ban-client status
sudo fail2ban-client status marinkino-auth
```

### 2. Namesti Docker in zaženi aplikacijo
```
sudo apt update && sudo apt install -y curl
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable --now docker
```

Zaženi začetni Docker setup:
```
sudo ./scripts/setup.sh
sudo chmod -R 777 cache
```

Ob koncu izvajanja te skripte mora biti stran dostopna preko HTTPS in vašega URL (DuckDNS poddomena).


Če želiš uporabljati Docker brez `sudo`, dodaj uporabnika v skupino `docker` in ponovno zaženi sejo:
```
sudo usermod -aG docker $USER
newgrp docker
```

### 3. Posodabljanje aplikacije po spremembah
Po spremembah v `src`, `.env`, Dockerfile ali `docker-compose.yml` ponovno pregradi:
```
docker compose up -d --build
```

## Varna sinhronizacija v oblak z rclone

Namesti in konfiguriraj rclone:
```
sudo curl https://rclone.org/install.sh | sudo bash
rclone config
```

Primer konfiguracije za Google Drive:
1. `n` – New remote
2. izberi ime, npr. `gdrive`
3. izberi ponudnika (Google Drive)
4. pusti `Client ID` in `Secret` prazno, razen če želiš napredno konfiguracijo
5. izberi `Scope` = Full access
6. `Edit advanced config` = n
7. uporabi spletni brskalnik za avtentikacijo

Preveri dostopnost:
```
rclone ls gdrive:
```

Ročno poženite sinhronizacijo:
```
./scripts/rclone/rclone-sync-gdrive.sh
```

Za samodejno sinhronizacijo dodaj cron nalogo:
```
sudo crontab -e
```

Dodaj vrstico (poskrbi, da pot ustreza tvojemu okolju):
```
0 7 * * * /home/marinko/Desktop/MarinKino/scripts/rclone/rclone-sync-gdrive.sh
```

## Uporaba lastne domene

DuckDNS uporabljaj kot dinamičen DNS samo, če nimaš fiksnega IP ali želiš hitro testno rešitev.
Za produkcijsko rabo priporočam svojo domeno, kjer upravljaš DNS zapise pri ponudniku domene.

1. Nastavi A zapis na svoj fiksni javni IP naslov.
2. Če imaš IPv6, dodaj tudi AAAA zapis.
3. Za boljšo varnost nastavi tudi CAA zapise za izdajo SSL certifikatov.
4. Če želiš, lahko lastno domeno usmeriš prek CNAME na DuckDNS poddomeno, vendar je najbolj stabilna rešitev neposredni A/AAAA zapis na ciljni strežnik.

Za HTTPS uporabi certbot ali drugo TLS rešitev z lastno domeno, ne pa URL-ja DuckDNS kot primarno končno ime. DuckDNS naj ostane pomočnik za dinamičen DNS in začasno preusmeritev, če nimaš statičnega naslova.
