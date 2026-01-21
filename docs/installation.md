# Nastavitev MarinKino

Spodaj so celotna navodila za nastavitev okolja, da se ob zagonu računalnika zažene tudi strežnik dostopen preko HTTPS.

## Zahteve sistema
* Računalnik, ki teče na Linux (recimo Ubuntu 24.04)
* rezerviran IP za strežnik
* nastavljen fail2ban za nginx-404, nginx-botsearch in nginx-http-auth
* TLC port forwarding za 80-80 (notranji in zunanji vhod) in 443-443 nastavljen na routerju za IP strežnika
* na duckdns.org nastavljeno poddomeno za svojo stran.

* za razvoj pa tudi Python 3.12 in ffmpeg

## Nastavitev programa

### 1. 📥 Kloniraj repozitorij
```
git clone https://github.com/AnzeMarinko/MarinKino.git
cd repozitorij
chmod +x ./scripts/setup.sh
```

```
# naloži docker
sudo apt-get update
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker

# zgradi docker compose z našo aplikacijo
sudo ./scripts/setup.sh
sudo chmod -R 777 cache

# dodaj pravice za docker brez sudo
sudo usermod -aG docker $USER
newgrp docker
```

... navodila za posodabljanje docker image ob spremembah v kodi:
docker compose restart app
ali pa (če so še kakšne ne s src kodo povezane spremembe - requirements, .env ... ipd.)
docker compose up -d --build

kako testirati lokalno

### 2. 🐍 Ustvari virtualno okolje
```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 📦 Namesti odvisnosti
```
sudo apt update && sudo apt upgrade
sudo apt install redis-server
pip install --upgrade pip
pip install -e .
```
### 4. Posodobi ključe
Posodobi datoteki `.env` and `credentials/gen-lang-client.json` in poženi
```
git update-index --assume-unchanged .env
```
S tem ohraniš ključe varne.

### 5. Preveri, da deluje
```
python app.py
```

Po potrebi popravi poti v kodi.
Dodaj `data/users.json` z vsaj enim administratorjem.

### 7. Varno shrani datoteke

V mape movies, memes in music postavi datoteke ter konfiguriraj rclone sinhronizacijo na oblak. Ko imaš rclone konfiguriran, ročno enkrat poženi skripto `./scripts/rclone/rclone-sync-gdrive.sh`. Nato pripravi "cron job":
```
sudo crontab -e
```

Dodaj (popravi pot do datoteke):
```
0 7 * * * /home/marinko/Desktop/MarinKino/scripts/rclone/rclone-sync-gdrive.sh
```

### 8. Nastavi omejitve IP-jem, ki iščejo luknje
```
sudo apt install fail2ban
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
```
S pomočjo umetne inteligence (npr. ChatGPT) uredi nginx-404, nginx-http-auth ipd.
```
sudo nano /etc/fail2ban/jail.local
sudo systemctl restart fail2ban
sudo fail2ban-client status
```
