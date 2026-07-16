# Kodi RSS for upcoming movies and TV series

This repository creates a compact RSS 2.0 feed for Kodi's RSS ticker.

Example headlines:

- `Movie: 17/7 – The Odyssey`
- `TV series: 17/7 – The East Palace Season 1`

The feed contains releases from today through the next seven calendar days, as configured in `config.json`. It fetches separate date pages from:

- `https://www.releases.com/calendar/movies`
- `https://www.releases.com/calendar/tv-series`

GitHub Actions runs automatically at **08:17 and 20:17 Swedish local time**. The workflow can also be started manually.

## Set up the repository

1. Create a new public GitHub repository.
2. Upload all files in this folder to the repository root.
3. Open **Settings → Actions → General**.
4. Under **Workflow permissions**, select **Read and write permissions** and save.
5. Open **Actions**, select **Update Kodi RSS**, and click **Run workflow**.
6. Confirm that `docs/releases.xml` contains actual release entries.
7. Open **Settings → Pages**.
8. Select **Deploy from a branch**, branch `main`, and folder `/docs`.
9. The RSS URL will normally be:

   `https://YOUR-USERNAME.github.io/REPOSITORY-NAME/releases.xml`

## Add the feed to Kodi

Use the RSS Editor add-on or edit `RssFeeds.xml`.

Example:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rssfeeds>
  <set id="1">
    <feed updateinterval="60">https://YOUR-USERNAME.github.io/REPOSITORY-NAME/releases.xml</feed>
  </set>
</rssfeeds>
```

`updateinterval="60"` tells Kodi to check the feed every hour. The feed itself is generated twice a day.

## Configuration

Settings are stored in `config.json`.

- `days_ahead`: number of calendar days included in the feed.
- `start_offset_days`: `0` includes today; `1` starts tomorrow.
- `date_format`: short date format used in item titles.
- `movie_label` and `tv_label`: text placed before each title.
- `language`: RSS language code.
- `check_robots_txt`: should normally remain `true`.
- `request_delay_seconds`: short delay between requests.

## Safeguards

- Requests use a descriptive User-Agent.
- `robots.txt` is checked before calendar pages are fetched.
- A short delay is used between requests.
- If no titles are found, the existing RSS file is not replaced with an empty file.
- The RSS file is written atomically.
- The GitHub token is limited to `contents: write`.

## Source considerations

The feed republishes only short title and date information and links back to Releases.com. Check the site's current terms and `robots.txt`. Stop the workflow or use an official data source if Releases.com blocks or prohibits automated fetching.

The HTML structure of an external website can change. If the workflow begins to fail, the parser in `scripts/generate_feed.py` may need to be updated.

## Run locally

```bash
python -m pip install -r requirements.txt
python scripts/generate_feed.py
```

Tests:

```bash
python -m pip install pytest
pytest
```
