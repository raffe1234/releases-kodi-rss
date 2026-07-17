# Kodi RSS for upcoming movies and TV series

This repository creates a compact RSS 2.0 feed for Kodi's RSS ticker.

## Use the feed directly in Kodi

You do not need to fork this repository or create your own GitHub repository. You can add the hosted feed directly to Kodi:

```text
https://raffe1234.github.io/releases-kodi-rss/releases.xml
```

To add the feed:

1. Open **Settings → Interface → Skin** in Kodi.
2. Enable **Show RSS news feeds**.
3. Select **Edit RSS**.
4. Install the **RSS Editor** add-on if Kodi asks you to.
5. Add or replace the existing feed with:

   ```text
   https://raffe1234.github.io/releases-kodi-rss/releases.xml
   ```

6. Set the update interval, for example, to 60 minutes.

The selected Kodi skin must support the RSS ticker.

### Add the feed manually

You can also edit the `RssFeeds.xml` file in Kodi's userdata folder:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rssfeeds>
  <set id="1">
    <feed updateinterval="60">https://raffe1234.github.io/releases-kodi-rss/releases.xml</feed>
  </set>
</rssfeeds>
```

`updateinterval="60"` tells Kodi to check the feed every hour. The feed itself is generated twice a day.

## Feed contents

Example headlines:

- `Movie (cinema): 17/7 – The Odyssey`
- `Movie (Disney+): 16/7 – Descendants: Wicked Wonderland`
- `TV series (Netflix): 17/7 – The East Palace Season 1`

The feed retrieves upcoming movie and TV series releases for one week ahead, as configured in `config.json`.

Each item includes the release channel or platform when Releases.com provides one. A title can therefore appear more than once, for example first as a cinema release and later as a Netflix or VOD release.

By default, physical-only DVD and Blu-ray releases are excluded.

The feed fetches separate date pages from:

- `https://www.releases.com/calendar/movies`
- `https://www.releases.com/calendar/tv-series`

## Update schedule

GitHub Actions generates the feed twice a day.

The corresponding UTC run times are:

- **06:17 and 18:17 UTC** during daylight-saving periods.
- **07:17 and 19:17 UTC** during standard-time periods.

The workflow can also be started manually.

## Host your own copy

This is optional. You only need your own repository if you want to change the configuration or maintain a separate feed.

1. Create a new public GitHub repository.
2. Upload all files from this repository to the repository root.
3. Open **Settings → Actions → General**.
4. Under **Workflow permissions**, select **Read and write permissions** and save.
5. Open **Actions**, select **Update Kodi RSS**, and click **Run workflow**.
6. Confirm that `docs/releases.xml` contains actual release entries.
7. Open **Settings → Pages**.
8. Select **Deploy from a branch**, branch `main`, and folder `/docs`.
9. Your RSS URL will normally be:

   ```text
   https://YOUR-USERNAME.github.io/REPOSITORY-NAME/releases.xml
   ```

Use this URL instead of the hosted feed URL when configuring Kodi.

## Configuration

Settings are stored in `config.json`.

- `days_ahead`: number of calendar days included in the feed.
- `start_offset_days`: `0` includes today; `1` starts tomorrow.
- `date_format`: short date format used in item titles.
- `movie_label` and `tv_label`: text placed before each title.
- `language`: RSS language code.
- `include_platform`: set to `false` to return to the old title format without parentheses.
- `excluded_platforms`: release formats omitted from the feed. DVD and Blu-ray formats are excluded by default.
- `check_robots_txt`: should normally remain `true`.
- `request_delay_seconds`: short delay between requests.

## Safeguards

- Requests use a descriptive User-Agent.
- `robots.txt` is checked before calendar pages are fetched.
- A short delay is used between requests.
- If no titles are found, the existing RSS file is not replaced with an empty file.
- If platform detection fails, entries fall back to the previous `Movie: date – title` format.
- RSS GUIDs include date and platform so cinema and later streaming releases remain separate items.
- The RSS file is written atomically.
- The GitHub token is limited to `contents: write`.

## Source considerations

The feed republishes only short title, date, and release-channel information and links back to Releases.com. Dates use the USA region selected by the source site.

Check the site's current terms and `robots.txt`. Stop the workflow or use an official data source if Releases.com blocks or prohibits automated fetching.

The HTML structure of an external website can change. If the workflow begins to fail, the parser in `scripts/generate_feed.py` may need to be updated.

## Run locally

```bash
python -m pip install -r requirements.txt
python scripts/generate_feed.py
```

Run the tests with:

```bash
python -m pip install pytest
pytest
```
