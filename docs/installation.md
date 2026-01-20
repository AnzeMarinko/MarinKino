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
chmod +x ./scripts/duckdns_refresh.sh
chmod +x ./scripts/start_server.sh
chmod +x ./scripts/rclone/rclone-sync-gdrive.sh
chmod +x ./scripts/docker-setup.sh
```

```
# naloži docker
sudo apt-get update
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker

# zgradi docker compose z našo aplikacijo
sudo ./scripts/docker-setup.sh
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

### 6. Posodabljaj svoj IP na DuckDNS

Pripravi cron job:
```
sudo crontab -e
```

Dodaj (popravi pot do datoteke):
```
*/10 * * * * /home/marinko/Desktop/MarinKino/duckdns_refresh.sh
```

### 7. Varno shrani datoteke

V mape movies, memes in music postavi datoteke ter postavi rclone sinhronizacijo na oblak. Ko imaš rclone konfiguriran, ročno enkrat poženi skripto v spodnjem "cron job" in nato dodaj v cron job:
```
0 7 * * * /home/marinko/Desktop/MarinKino/rclone/rclone-sync-gdrive.sh
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

## Postavi NGINX + CERTBOT (DuckDNS) HTTPS server
### 0️⃣ Predpogoj (OBVEZNO, pred vsem)

Preveri, da DNS DELA:
```
dig anzemarinko.duckdns.org +short
```

👉 mora vrniti tvoj javni IP
Če ne → Certbot NE bo delal (ne glede na nginx)

### 1️⃣ 📦 Namestitev paketov
```
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx
```

### 2️⃣ 🌐 HTTP konfiguracija
Odpri datoteko:
```
sudo nano /etc/nginx/sites-available/marinkinoapp
```

Vanjo postavi HTTP config:
```
server {
    listen 80;
    server_name anzemarinko.duckdns.org;

    # ACME challenge (Certbot)
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/html;
        default_type "text/plain";
    }

    location / {
        return 200 "OK\n";
    }
}
```

Omogoči config in preveri
```
sudo ln -s /etc/nginx/sites-available/marinkinoapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Preveri v brskalniku:
```
http://anzemarinko.duckdns.org
```

### 3️⃣ 🔒 Pridobi certifikat
```
sudo certbot certonly \
  --webroot \
  -w /var/www/html \
  -d anzemarinko.duckdns.org
```

✅ Uspeh izgleda tako:
```
Congratulations! Your certificate and chain have been saved at:
/etc/letsencrypt/live/anzemarinko.duckdns.org/
```

### 4️⃣ 🔐 Dodaj HTTPS + redirect

Zdaj šele posodobi nginx config:
```
sudo nano /etc/nginx/sites-available/marinkinoapp
```
Naj bo tole notri:
```
server {
    listen 80;
    server_name anzemarinko.duckdns.org;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    server_name anzemarinko.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/anzemarinko.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/anzemarinko.duckdns.org/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Aktiviraj HTTPS
```
sudo nginx -t
sudo systemctl reload nginx
```

### 5️⃣ 🔁 Samodejna obnova certifikata

Certbot že namesti systemd timer.

Preveri:
```
systemctl list-timers | grep certbot
```

Test obnove:
```
sudo certbot renew --dry-run
```
