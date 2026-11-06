# Glasbena knjižnica

Nove MP3 postavi v `Neurejena-glasba/Izvajalec - Album/`. Najprej preglej načrt iz korena repozitorija:

```bash
python3 src/prepare_content.py --kind music --folder data/music/Neurejena-glasba --dry-run
uv run python src/prepare_content.py --kind music --folder data/music/Neurejena-glasba
```

Skladba `Pesem.mp3` dobi istoimensko mapo `Pesem/` s HLS in `metadata.json`; izvorni MP3 ostane ohranjen. Dokončane skladbe se ob ponovitvi preskočijo. Analiza zvoka je izbirna (`--analyze`).

Naslov, izvajalca in album lahko urediš v lokalnem urejevalniku (`uv run --extra preparation python src/manual_editor.py`, naslov `http://127.0.0.1:8080`). Po pregledu premakni MP3 in pripadajočo mapo HLS skupaj v želeno glasbeno mapo. Osveži knjižnico z `docker compose restart app`.

Celoten postopek, orodja in obnovitev: [Dodajanje vsebin](../../docs/adding_data.md).
