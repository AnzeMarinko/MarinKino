# Filmska knjižnica

Vsak film ima svojo mapo: `kategorija/Naslov.Filma.2026/`. Nove filme postavi v `0x-neurejeni-filmi/`, skupaj s podnapisi. Samostojne epizode označi kot zbirko (`.Collection`); dele enega filma poimenuj po vrstnem redu (`01`, `02` …).

Iz korena repozitorija:

```bash
python3 src/prepare_content.py --kind movies --dry-run
uv run --extra preparation python src/prepare_content.py --kind movies --threads 2
```

Za en film dodaj `--folder data/movies/0x-neurejeni-filmi/Naslov.Filma.2026`. Alternativa je lokalni urejevalnik na `http://127.0.0.1:8080/videos/editor` po zagonu `src/manual_editor.py`.

Po pripravi preveri predvajanje, metapodatke in podnapise. Mapo premakni v končno kategorijo in izvedi `docker compose restart app`. Izvorne datoteke ostanejo v `.originals` s pripono `.source`; to ni ločena varnostna kopija diska.

Celoten postopek, predpogoji, SSH tunel in obnovitev: [Dodajanje vsebin](../../docs/adding_data.md).
