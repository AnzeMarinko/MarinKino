#!/bin/bash

set -e

echo "🐳 MarinKino Docker Setup"
echo "========================"

# Nastavitve
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "❌ NAPAKA: Datoteka .env ne obstaja!"
    exit 1
fi

# Preveri spremenljivke
if [ -z "$DUCKDNS_DOMAIN" ] || [ -z "$MAIN_DOMAIN" ] || [ -z "$GMAIL_USERNAME" ] || [ -z "$WWW_DOMAIN" ]; then
    echo "❌ NAPAKA: V .env manjka DUCKDNS_DOMAIN, MAIN_DOMAIN, GMAIL_USERNAME ali WWW_DOMAIN!"
    exit 1
fi

EMAIL="$GMAIL_USERNAME"
DOMAIN="$MAIN_DOMAIN"
WWW_DOMAIN="$WWW_DOMAIN"

echo "🚀 Začenjam vzpostavitev za $DOMAIN and $WWW_DOMAIN ..."

chmod +x ./scripts/duckdns_refresh.sh
chmod +x ./scripts/rclone/rclone-sync-gdrive.sh

# 1. Pridobimo trenutni crontab (če ne obstaja, ustvarimo praznega)
crontab -l > mycron 2>/dev/null || touch mycron

# 2. Dodajanje DuckDNS osveževanja (vsakih 10 min). Če že obstaja, preskoči
if ! grep -q "duckdns" mycron; then
    echo "*/10 * * * * cd $(pwd) && ./scripts/duckdns_refresh.sh > /dev/null" >> mycron
    echo "✅ Dodano DuckDNS osveževanje."
    echo "🦆 Prvič osvežujem DuckDNS IP naslov ... (To lahko traja nekaj minut)"
    ./scripts/duckdns_refresh.sh
fi

# 1. Začasna HTTP konfiguracija za Certbot (vključuje vse poddomene)
mkdir -p cache/logs/server
mkdir -p configuration/nginx/conf
mkdir -p configuration/certbot/conf
echo "📝 Generiram začasno HTTP konfiguracijo za verifikacijo..."
cat > configuration/nginx/conf/app.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN $WWW_DOMAIN *.$DOMAIN $DUCKDNS_DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 "Certbot validation mode"; }
}
EOF

# 2. Zaženemo Nginx v ozadju
echo "🐳 Zaganjam Nginx..."
docker compose up -d nginx

echo "⏳ Čakam 10 sekund, da se Nginx postavi..."
sleep 10

# 2. Zahtevamo certifikat za več imen hkrati
echo "🔑 Zahtevam certifikate..."
docker compose run --rm --entrypoint "certbot" certbot certonly --webroot --webroot-path /var/www/certbot \
    -d $DOMAIN -d $WWW_DOMAIN -d $DUCKDNS_DOMAIN \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    --force-renewal

# Preverimo uspeh
if [ ! -d "configuration/certbot/conf/live/$DOMAIN" ]; then
    echo "❌ NAPAKA: Certifikata ni bilo mogoče pridobiti."
    echo "Preveri, če imaš odprt port 80 na routerju in če DNS deluje."
    exit 1
fi

# 4. Če je certifikat tu, prepišemo konfiguracijo s pravo HTTPS verzijo
echo "✅ Certifikat pridobljen! Nameščam HTTPS konfiguracijo..."

cat > configuration/nginx/conf/app.conf <<EOF
# 1. Preusmeritev vseh HTTP na HTTPS
server {
    listen 80;
    server_name $DOMAIN $WWW_DOMAIN *.$DOMAIN $DUCKDNS_DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://\$host\$request_uri; }
}

# 2. Preusmeritev DuckDNS na WWW
server {
    listen 443 ssl;
    server_name $DUCKDNS_DOMAIN;

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    ssl_certificate /etc/letsencrypt/live/anzemarinko.si/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/anzemarinko.si/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    return 301 https://$WWW_DOMAIN\$request_uri;
}

# 3. WWW poddomena
server {
    listen 443 ssl;
    server_name $WWW_DOMAIN;

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://app:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # --- Za hitro pretakanje vsebin ---
    # Samo za interne preusmeritve, uporabnik ne more dostopati direktno (Pot ZNOTRAJ Nginx kontejnerja)
    location /protected_music/ {internal; alias /music_data/;}
    location /protected_movies/ {internal; alias /movies_data/;}
    location /protected_memes/ {internal; alias /memes_data/;}
    location /protected_blog_images/ {internal; alias /blog_images_data/;}
}

# 4. WILDCARD preusmeritev (Vse na WWW)
server {
    listen 443 ssl;
    server_name $DOMAIN *.$DOMAIN;

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    return 301 https://$WWW_DOMAIN\$request_uri;
}
EOF

# 5. Ponovno naložimo Nginx in zaženemo še aplikacijo
echo "🔄 Ponovno nalagam Nginx in zaganjam aplikacijo..."
docker compose down
docker compose up -d --build

# 2. Obnavljanje certifikata (vsakih 12 ur)
if ! grep -q "certbot renew" mycron; then
    # cd v mapo projekta, poskus obnove in osvežitev Nginxa
    echo "0 */12 * * * cd $(pwd) && docker compose run --rm certbot renew && docker compose exec nginx nginx -s reload" >> mycron
    echo "✅ Dodano: Samodejno podaljševanje certifikata."
fi

# 4. Namestitev novega crontaba in brisanje začasne datoteke
crontab mycron
rm mycron

echo "📅 Cron opravila so aktivna. Preveriš jih z: crontab -l"

echo "⏳ Počakajmo, da se vse zažene ..."
sleep 5

echo "✅🎉 KONČANO! Tvoja aplikacija je dostopna na https://$WWW_DOMAIN"
echo "Poglej log-e: docker compose logs -f app"
echo "Ustavi celotno storitev: docker compose down"
