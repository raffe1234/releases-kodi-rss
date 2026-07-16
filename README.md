# Kodi RSS för kommande filmer och TV-serier

Detta repo skapar ett kort RSS 2.0-flöde för Kodis RSS-ticker.

Exempel på rubriker:

- `Film: 17/7 – The Odyssey`
- `TV-serie: 17/7 – The East Palace Season 1`

Flödet innehåller premiärer från i dag och sju kalenderdagar framåt enligt
`config.json`. Det hämtar separata datumsidor från:

- `https://www.releases.com/calendar/movies`
- `https://www.releases.com/calendar/tv-series`

GitHub Actions kör automatiskt klockan **08.17 och 20.17 svensk tid**.
Körningen kan också startas manuellt.

## Starta lösningen

1. Skapa ett nytt publikt GitHub-repo.
2. Ladda upp hela innehållet i denna mapp till repots rot.
3. Öppna **Settings → Actions → General**.
4. Under **Workflow permissions**, välj **Read and write permissions** och spara.
5. Öppna fliken **Actions**, välj **Uppdatera Kodi RSS** och klicka på
   **Run workflow**.
6. Kontrollera att `docs/releases.xml` har fått riktiga premiärer.
7. Öppna **Settings → Pages**.
8. Välj **Deploy from a branch**, branch `main` och mappen `/docs`.
9. RSS-adressen blir normalt:

   `https://DITT-ANVÄNDARNAMN.github.io/REPO-NAMN/releases.xml`

## Lägg in flödet i Kodi

Du kan använda RSS Editor-tillägget eller redigera `RssFeeds.xml`.

Exempel:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rssfeeds>
  <set id="1">
    <feed updateinterval="60">https://DITT-ANVÄNDARNAMN.github.io/REPO-NAMN/releases.xml</feed>
  </set>
</rssfeeds>
```

`updateinterval="60"` betyder att Kodi kontrollerar flödet varje timme.
Själva flödet byggs två gånger per dygn.

## Anpassa

Inställningar finns i `config.json`.

- `days_ahead`: antal dagar i flödet.
- `start_offset_days`: `0` inkluderar i dag, `1` börjar i morgon.
- `date_format`: kort datum i rubriken.
- `movie_label` och `tv_label`: text före titeln.
- `check_robots_txt`: bör normalt vara `true`.
- `request_delay_seconds`: liten paus mellan anropen.

## Säkerhetsfunktioner

- Hämtningen identifierar sig med en egen User-Agent.
- `robots.txt` kontrolleras före kalenderanropen.
- Förfrågningar görs med en liten paus.
- Om inga titlar hittas skrivs ingen tom RSS-fil över den gamla.
- RSS-filen skrivs atomiskt.
- GitHub-token får bara rättigheten `contents: write`.

## Viktigt om källan

Lösningen återpublicerar endast korta titel- och datumuppgifter och länkar
tillbaka till Releases.com. Kontrollera ändå webbplatsens aktuella villkor och
`robots.txt`. Om Releases.com blockerar eller förbjuder automatiserad hämtning
ska körningen stoppas eller en officiell datakälla användas.

HTML-strukturen på en extern webbplats kan ändras. Om arbetsflödet börjar
misslyckas behöver parsern i `scripts/generate_feed.py` justeras.

## Lokal kontroll

```bash
python -m pip install -r requirements.txt
python scripts/generate_feed.py
```

Tester:

```bash
python -m pip install pytest
pytest
```
