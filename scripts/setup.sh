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

# Preverimo, če sta spremenljivki nastavljeni
if [ -z "$DUCKDNS_DOMAIN" ] || [ -z "$GMAIL_USERNAME" ]; then
    echo "❌ NAPAKA: V .env datoteki manjkata DUCKDNS_DOMAIN ali GMAIL_USERNAME!"
    echo "Prepričaj se, da imaš v .env zapisano:"
    echo "DUCKDNS_DOMAIN=tvoja-poddomena.duckdns.org"
    echo "GMAIL_USERNAME=tvoj-naslov@gmail.com"
    exit 1
else
    EMAIL="$GMAIL_USERNAME"
    DOMAIN="$DUCKDNS_DOMAIN"
fi

echo "🚀 Začenjam avtomatsko vzpostavitev za $DOMAIN ($EMAIL)..."

chmod +x ./scripts/duckdns_refresh.sh
chmod +x ./scripts/run_tests.sh
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

# 1. Ustvarimo začasno HTTP konfiguracijo (samo za verifikacijo)
mkdir -p cache/logs/server
mkdir -p configuration/nginx/conf
mkdir -p configuration/certbot/conf

echo "📝 Generiram začasno HTTP konfiguracijo..."
cat > configuration/nginx/conf/app.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 "Certbot validation mode"; }
}
EOF

# 2. Zaženemo Nginx v ozadju
echo "🐳 Zaganjam Nginx..."
docker compose up -d nginx

echo "⏳ Čakam 10 sekund, da se Nginx postavi..."
sleep 10

# 3. Zaženemo Certbot
echo "🔑 Zahtevam certifikat..."
docker compose run --rm --entrypoint "certbot" certbot certonly --webroot --webroot-path /var/www/certbot \
    -d $DOMAIN \
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
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    server_name $DOMAIN;

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

echo "✅🎉 KONČANO! Tvoja aplikacija je dostopna na https://$DOMAIN"
echo "Poglej log-e: docker compose logs -f"
echo "Ustavi celotno storitev: docker compose down"
