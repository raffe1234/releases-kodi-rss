# Kodi RSS – upcoming movies and TV series

A compact English-language RSS 2.0 feed for Kodi's scrolling RSS ticker.

For a dated summary of changes, see the [changelog](CHANGELOG.md).

- **Movies:** [TMDB](https://www.themoviedb.org/), using US release dates for **cinema**, **digital**, and **disc** (physical media).
- **TV series:** [TVmaze](https://www.tvmaze.com/), using US broadcast schedules and global/local web schedules. **Only season premieres** (episode 1 of a season) are included.
- **Time window:** seven calendar days by default, including today, using Central European time (CET/CEST).
- **Schedule:** twice daily at 08:17 and 20:17 Central European time (CET/CEST) via GitHub Actions.

**Regional coverage:** Anyone can use the public feed, but release dates are not globally uniform. Movie dates use the US (`movie_region: US`), and TVmaze uses US broadcast schedules plus web/streaming premieres from international services. The seven-day window uses CET/CEST, with automatic daylight saving time adjustment. If you host your own copy, you can change `movie_region`, `tv_country`, and `timezone` in `config.json`.

## Use the feed in Kodi

The address is unchanged:

```text
https://raffe1234.github.io/releases-kodi-rss/releases.xml
```

1. In Kodi, open **Settings → Interface → Skin**.
2. Enable **Show RSS news feeds** and choose **Edit RSS**.
3. Install the **RSS Editor** add-on if prompted and add the URL above.
4. An update interval of 60 minutes is reasonable. Your skin must support RSS.

Or edit Kodi's `RssFeeds.xml` manually:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rssfeeds>
  <set id="1">
    <feed updateinterval="60">https://raffe1234.github.io/releases-kodi-rss/releases.xml</feed>
  </set>
</rssfeeds>
```

## What the headlines look like

```text
>> [Movie · cinema · 17/11] Example Movie
>> [Movie · digital · 18/11] Example Movie
>> [Movie · disc · 19/11] Another Movie
>> [TV series · Netflix · 20/11] Example Series Season 1
```

The examples are illustrative, not confirmed upcoming titles. Every item links to its corresponding entry on TMDB or TVmaze.

**Disc** is TMDB's *Physical* release category. TMDB does not reliably distinguish DVD from Blu-ray, 4K Blu-ray, or SteelBook, so these formats cannot be listed separately. **Digital** is a release type, not a guarantee of availability on a specific streaming platform; TMDB does not supply a named service for this category.

TVmaze season premieres are recognized by episode number **1** and a positive season number. Specials and subsequent episodes are ignored. US network television is selected by country, but the web/streaming schedule includes worldwide web channels (some launches may not be available in the US). TVmaze availability, timing, and channel labels depend on the completeness of its records.

## One-time setup: free TMDB API key

TVmaze's public schedule API needs **no key**. TMDB requires a free developer API key for non-commercial use; comply with [TMDB's terms and attribution rules](https://developer.themoviedb.org/docs/faq).

1. Register or log in at [TMDB](https://www.themoviedb.org/signup).
2. Open [Account Settings → API](https://www.themoviedb.org/settings/api).
3. Request a **Developer API key**, accept the terms and describe this RSS project. For the website, use your public GitHub repository URL.
4. Copy the **API Key (v3 auth)**, not the long **API Read Access Token**.
5. Open GitHub repository **Settings → Secrets and variables → Actions → New repository secret**.
6. Set the **Name** to `TMDB_API_KEY`, and the **Secret** to your v3 key; click **Add secret**.
7. In the repository's **Actions**, run **Update Kodi RSS → Run workflow** once to verify.

**Never commit the key** to `config.json`, a script, or a file in the repository. The GitHub Actions workflow supplies it from secrets to Python. No Python installation is required on your NAS.

## Updating the repository from your NAS

Copy a downloaded patch to the parent `Github` directory, then work from your `releases-kodi-rss` clone. Replace `PATCH_NAME.patch` with the actual file name:

```sh
git pull --ff-only
git apply --check ../PATCH_NAME.patch
git apply ../PATCH_NAME.patch
git status
git add README.md docs/index.html  # Example: stage only files changed by a docs patch
git commit -m "Update documentation"
git push origin main
```

For other patches, adjust the `git add` paths to match the changed files. If Git asks for an author, set `git config user.name` and `git config user.email` in this repository once.

## Hosting your own copy

1. Upload/fork the project to a public GitHub repository.
2. Add your `TMDB_API_KEY` secret as described above.
3. In **Settings → Actions → General**, allow read and write workflow permissions.
4. Enable GitHub Pages in **Settings → Pages → Deploy from a branch**, branch `main`, folder `/docs`.
5. Run **Actions → Update Kodi RSS → Run workflow**. After success, the RSS is at:
   `https://YOUR-USERNAME.github.io/REPOSITORY-NAME/releases.xml`
6. Update the feed URL in Kodi and `feed_link` in `config.json` if you are hosting a different copy.

## Configuration

`config.json` contains:

| Field | Purpose |
| --- | --- |
| `days_ahead` | Days to fetch (1–31), default 7 |
| `start_offset_days` | `0` = today, `1` = tomorrow |
| `timezone` | Calendar clock for the window, default `CET` (automatically observes CET/CEST daylight saving time) |
| `movie_region` | TMDB regional movie dates, default `US` |
| `tv_country` | TVmaze broadcast country, default `US`; web channels still include global services |
| `tmdb_max_pages` | Safety limit per movie release type, fails instead of silently truncating |
| `feed_link` | Link to your hosted GitHub Pages homepage |
| `movie_label`, `tv_label` | Type names in titles |
| `date_format` | Date label inside brackets (`%-d/%-m`) |
| `include_platform` | Include `cinema`, `digital`, `disc`, or TV channel name |
| `excluded_platforms` | Optional whole-channel exclusions; e.g., `"disc"` |
| `request_delay_seconds` | Delay before each API request (default 0.5s) |
| `minimum_kodi_items` | Add harmless filler lines if Kodi needs at least 3 entries |
| `output_file` | Generated RSS location: `docs/releases.xml` |

The original options `check_robots_txt` and Releases.com-specific platform exclusions were removed because this version uses official API endpoints rather than HTML scraping.

## Safety and troubleshooting

- GitHub Actions runs unit tests before generating RSS.
- Both APIs use bounded HTTP retries/backoff on 429 and temporary server errors.
- If the TMDB key is missing/invalid, an API request fails, or the feeds are empty, the existing `docs/releases.xml` remains untouched.
- TMDB pagination is exhaustive up to `tmdb_max_pages` per release type; beyond that the workflow fails instead of publishing an incomplete feed.
- After a successful fetch, RSS is written atomically and GitHub Actions commits only a changed `docs/releases.xml`.
- The existing `docs/releases.xml` from Releases.com is deliberately not replaced by this code patch; the **first successful Action run** creates the new feed from TMDB and TVmaze.
- The script uses documented APIs, not Releases.com or its `robots.txt`.
- GitHub Actions has only `contents: write` permission and does not print the API key.

### Run locally (optional; not needed on NAS)

```sh
python -m pip install -r requirements.txt
TMDB_API_KEY=your_v3_key python scripts/generate_feed.py
python -m pytest -q
```

## Project history

### November 2026 – migration from Releases.com to TMDB and TVmaze

The feed originally collected upcoming movie and television release dates from Releases.com calendar pages. In November 2026, automated requests from GitHub Actions began receiving HTTP 403 (Forbidden) responses, first for `robots.txt` and then for the calendar pages. This prevented reliable feed updates.

Rather than attempting to bypass the site's access restrictions, the project switched to documented APIs:

- **TMDB** provides cinema, digital and physical movie release dates. Physical releases appear as **disc**, since DVD and Blu-ray are not reliably distinguished.
- **TVmaze** provides television and streaming season premieres (the first episode of each new season).

This removed the dependency on scraping Releases.com HTML and its page structure. The RSS URL and Kodi headline style were retained, so existing subscribers did not need to reconfigure Kodi. Coverage differs from Releases.com, and release dates can vary by region; see **Regional coverage** at the top of this README.

## Credits and licences

Movie metadata and release dates: [TMDB](https://www.themoviedb.org/). **This product uses the TMDB API but is not endorsed or certified by TMDB.** Approved TMDB branding and attribution: [TMDB Logos & Attribution](https://www.themoviedb.org/about/logos-attribution).

TV premiere metadata: [TVmaze](https://www.tvmaze.com/), API material used with attribution under [CC BY-SA](https://www.tvmaze.com/api). Original TVmaze show links are preserved in the feed. Your use must comply with TVmaze's ShareAlike requirements.

The project's [public index / credits page](https://raffe1234.github.io/releases-kodi-rss/) includes both sources and the required TMDB notice. The RSS ticker is text only; the credits page also references TMDB's approved brand logo. If using the feed elsewhere, preserve these credits and required notices.
