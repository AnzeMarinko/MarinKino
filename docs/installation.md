# Nastavitev MarinKino

Spodaj so celotna navodila za nastavitev okolja, da se ob zagonu računalnika zažene tudi strežnik dostopen preko **HTTPS**.

## Zahteve sistema
* Računalnik z operacijskim sistemom **Linux** (recimo Ubuntu 24.04 ali Raspberry Pi OS)
* **Python 3.12** in **FFMPEG**
* **Rezerviran IP** za strežnik (na routerju nastavi rezerviran IP za MAC naslov mrežne kartice svojega strežnika)
* TLC **port forwarding** za 80-80 (notranji in zunanji vhod) in 443-443 nastavljen na routerju za rezerviran IP strežnika
* Na **duckdns.org** nastavljeno poddomeno za svojo stran.

## Navodila za lokalno vzpostavitev

### 1. Kloniraj repozitorij
Kloniraj repozitorij:
```
git clone https://github.com/AnzeMarinko/MarinKino.git
cd repozitorij
chmod +x ./scripts/setup.sh
```

### 2. Posodobi ključe
Kopiraj datoteko `.env.example` v `.env` ter posodobi vrednosti spremenljivk na
svoje nastavitve in gesla. Dodaj tudi datoteko `credentials/gen-lang-client.json`,
kjer je ključ za tvoje Google AI storitve. Slednja datoteka se uporablja le za prevajanje opisov filmov. Če tega ne potrebuješ, lahko odstraniš.

### 3. Ustvari virtualno okolje
```
python3 -m venv .venv
pip install --upgrade pip
pip install -e .
```

### 4. Namesti odvisnosti (Redis)
```
sudo apt update && sudo apt upgrade
sudo apt install redis-server
```

### 5. Preveri, da ti deluje lokalno (pomembno zaradi razvoja)
Postavi lokalno Flask aplikacijo dostopno znotraj tvojega Wi-Fi omrežja:
```
python src/app.py
```

Po potrebi popravi poti v kodi.
Ob prvem zagonu se avtomatsko generira datoteka `data/users.json` s prvim uporabnikom, ki je tudi administrator. Priporočeno je, da ročno spremenite uporabniško ime tega administratorja, uredite njegov e-naslov in iz datoteke obvezno odstranite dejansko vrednost gesla `initial_password`, ki vam služi za prvi vpis.

### 6. Dodaj vsebine
V mape `movies`, `memes` in `music` postavi datoteke glede na [navodila za dodajanje datotek](docs/adding_data.md).

## Nastavitev serverja

### 1. Nastavi omejitve IP-jem, ki iščejo luknje

Naložite paket Fail2Ban:
```
sudo apt update && sudo apt upgrade
sudo apt install fail2ban -y
```

Odprite konfiguracijo filtra za Nginx 404 odzive:
```
sudo nano /etc/fail2ban/filter.d/nginx-404.conf
```
in vso vsebino zamenjajte z vsebino datoteke `configuration/fail2ban/filter.d/nginx-404.conf` (Shranite s pritiskom na CTRL+O in nato Enter, ter zaprete s CTRL+X).

Zdaj odprite glavno konfiguracijo:
```
sudo nano /etc/fail2ban/jail.local
```
in vso vsebino zamenjajte z vsebino datoteke `configuration/fail2ban/jail.local`.

Posodobite konfiguracijo:
```
sudo systemctl restart fail2ban
sudo fail2ban-client status
```
in čez nekaj sekund preverite status:
```
sudo systemctl restart fail2ban
sudo fail2ban-client status
```

### 2. Naloži Docker in zgradi Docker compose
Naloži Docker:
```
sudo apt update && sudo apt upgrade
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo systemctl enable docker
```

Zgradi docker compose z našo aplikacijo:
```
sudo ./scripts/setup.sh
sudo chmod -R 777 cache
```
Ob koncu izvajanja te skripte mora biti stran dostopna preko HTTPS in vašega URL (DuckDNS poddomena).

Dodaj pravice za docker brez sudo:
```
sudo usermod -aG docker $USER
newgrp docker
```

V primeru sprememb v kodi (karkoli v mapi `src`) ali ob ročnih spremembah v mapi `data` (vključno z ročnimi zagoni python skript) posodobimo docker image aplikacije:
```
docker compose restart app
```
Če pa imamo še kakšne infrastrukturne spremembe (uporabljene python knjižnice, `.env` ipd.), na novo zgradimo celotno strukturo:
```
docker compose up -d --build
```

## Nastavi varno shranje kopije datotek v oblak

Naloži in konfiguriraj rclone sinhronizacijo na oblak:
```
sudo curl https://rclone.org/install.sh | sudo bash
rclone config
```
Sledite tem korakom (primer za Google Drive):
1. **n) New remote** – vpišite ime (npr. `gdrive`).
1. **Storage** – izberite številko za ponudnika (npr. Google Drive).
1. **Client ID & Secret** – pustite prazno (pritisnite Enter), razen če ste napreden uporabnik.
1. **Scope** – izberite 1 (Full access).
1. **Edit advanced config** – n (No).
1. **Use web browser to authenticate?** –
    * Če delate na **osebnem računalniku**, vpišite y.
    * Če delate na **oddaljenem strežniku brez grafičnega vmesnika**, vpišite n (sledite navodilom za "Remote Config").
1. Ko se v brskalniku prijaviš in potrdiš dostop, se vrni v terminal in potrdi z y (Yes, this is OK).

Preveri vsebino 
```
rclone ls gdrive:
```

Ko imaš rclone konfiguriran, uredi poti in ročno enkrat poženi skripto `./scripts/rclone/rclone-sync-gdrive.sh`. Ko konča, pripravi "cron job":
```
sudo crontab -e
```

Dodaj (popravi pot do datoteke):
```
0 7 * * * /home/marinko/Desktop/MarinKino/scripts/rclone/rclone-sync-gdrive.sh
```
