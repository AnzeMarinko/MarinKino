#!/bin/bash

# Nastavitve
DOMAIN="anzemarinko.duckdns.org"
EMAIL="anze.marinko96@gmail.com"

echo "🚀 Začenjam avtomatsko vzpostavitev za $DOMAIN..."

# 1. Ustvarimo začasno HTTP konfiguracijo (samo za verifikacijo)
echo "📝 Generiram začasno HTTP konfiguracijo..."
mkdir -p configuration/nginx/conf
mkdir -p configuration/certbot/conf
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
docker compose run --rm certbot certonly --webroot --webroot-path /var/www/certbot \
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
docker compose restart nginx
docker compose up -d

echo "🎉 KONČANO! Tvoja aplikacija je dostopna na https://$DOMAIN"
