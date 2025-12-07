# Nastavitev MarinKino

Spodaj so celotna navodila za nastavitev okolja, da se ob zagonu računalnika zažene tudi strežnik dostopen preko HTTPS.

## Zahteve sistema
* Računalnik, ki teče na Linux (recimo Ubuntu 24.04)
* Python 3.12
* ffmpeg
* TLC port forwarding za 80-80 (notranji in zunanji vhod) in 443-443 nastavljen na routerju
* na duckdns.org nastavljeno poddomeno za svojo stran.

## Nastavitev programa

### 1. 📥 Kloniraj repozitorij
```
git clone https://github.com/AnzeMarinko/MarinKino.git
cd repozitorij
```

### 2. 🐍 Ustvari virtualno okolje
```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 📦 Namesti odvisnosti
```
pip install --upgrade pip
pip install -r requirements.txt
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

### 6. Posodabljaj svoj IP na DuckDNS

Pripravi cron job:
```
sudo crontab -e
```

Dodaj (popravi pot do datoteke):
```
*/10 * * * * /media/marinko/Local2TB/GoogleDriveMirror/MarinKino/duckdns_refresh.sh
```

## Konfiguracija zagonskega programa

Naredimo `systemd` servis `movies.service`, da bo tvoja Flask/Waitress aplikacija tekla kot storitev ob zagonu sistema.
### 1. Ustvari servisno datoteko

Ustvari datoteko:
```
sudo nano /etc/systemd/system/movies.service
```

Vsebina (prilagodi poti, ime uporabnika ...!):
```
[Unit]
Description=MarinKino Flask Server
After=network.target
Requires=local-fs.target

[Service]
Type=simple
User=root
WorkingDirectory=/media/marinko/Local2TB/GoogleDriveMirror/MarinKino

# Če disk ni mountan, ga mounta
ExecStartPre=/bin/bash -c 'mountpoint -q /media/marinko/Local2TB || sudo mount /dev/sdb1 /media/marinko/Local2>

# Zažene tvoj skript
ExecStart=/bin/bash /media/marinko/Local2TB/GoogleDriveMirror/MarinKino/start_server.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
Pomembno:
* WorkingDirectory mora kazati na mapo, kjer je tvoja aplikacija.
* ExecStart mora kazati na Python znotraj tvojega venv.

### 2. Zaženi zagonsko aplikacijo
```
sudo systemctl daemon-reload
sudo systemctl enable movies.service
sudo systemctl start movies.service
systemctl status movies.service
```

## Konfiguracija Nginx strežnika
### 1. 📦 Namestitev potrebnih paketov in preverjanje delovanja
```
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx
systemctl status nginx
```

### 2. 🌐 Osnovna konfiguracija Nginx strežnika

Ustvari konfiguracijo za svojo domeno:
```
sudo nano /etc/nginx/sites-available/myapp
```

Primer konfiguracije (ime(-na) serverja spremeni iz example.com v ime(-na) svojega serverja/domene):
```
server {
    listen 80;
    server_name example.com www.example.com;

    # Certbot challenge
    location ^~ /.well-known/acme-challenge/ {
        alias /var/www/html/.well-known/acme-challenge/;
    }

    # Redirect na HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name example.com www.example.com;

    # Let's Encrypt certifikati
    ssl_certificate /etc/letsencrypt/live/anzemarinko.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/anzemarinko.duckdns.org/privkey.pem;

    # Za boljšo varnost (ni obvezno, je pa priporočljivo)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    # Reverse proxy do Flask/Waitress
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Omogoči konfiguracijo in jo preveri:
```
sudo ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled/
sudo nginx -t
```

Ponovno naloži:
```
sudo systemctl reload nginx
```
### 3. 🔒 Namestitev TLS/SSL certifikata preko Certbot

Za popolnoma avtomatsko konfiguracijo (zamenjaj s svojo domeno):
```
sudo certbot --nginx -d example.com -d www.example.com
```

Certbot bo:
* preveril DNS
* ustvaril certifikat
* konfiguriral Nginx
* postavil auto-renew hook

Preveri, ali certifikat deluje:
```
sudo certbot certificates
```
### 4. 🔁 Samodejna obnova certifikata (cron)

Certbot že avtomatično namesti systemd timer.
Preveri:
```
systemctl list-timers | grep certbot
```

Če želiš svoj cron job, ustvari:
```
sudo crontab -e
```

Dodaj:
```
0 3 * * * certbot renew --quiet --nginx
```

S tem vsak dan ob 03:00 preveri certifikat, ga obnovi samo, če je manj kot 30 dni do izteka in  poskrbi za reload nginx.

Za test:
```
sudo certbot renew --dry-run
```
