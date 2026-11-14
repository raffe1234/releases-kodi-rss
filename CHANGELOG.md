# Changelog

Notable project changes are recorded here. Entries are grouped by date because
this repository has not used formal versioned releases.

The [README](README.md) explains the current setup and configuration.

## Unreleased

No changes recorded yet.

## 2026-11-14 — Migration to TMDB and TVmaze

### Changed

- Replaced Releases.com calendar-page scraping with documented APIs: TMDB for
  movie release dates and TVmaze for television and streaming season premieres.
- Standardized movie release labels to `cinema`, `digital`, and `disc` (physical
  media). Individual DVD and Blu-ray formats are no longer distinguished.
- TVmaze entries represent season premieres (episode 1), rather than every
  upcoming TV episode.
- Kept the public RSS URL, Kodi title format, and twice-daily GitHub Actions
  publishing workflow.
- Used Central European time (CET/CEST) for the feed window and schedule,
  without a location-specific timezone label in the documentation.

### Added

- TMDB v3 API key support through the `TMDB_API_KEY` GitHub Actions secret;
  TVmaze's public schedule API does not require a key.
- Updated tests, configuration, error handling, source attribution, and setup
  instructions for the API-based implementation.
- Explicit source links for TMDB movies and TVmaze shows in the RSS entries.

### Fixed

- Restored feed generation after Releases.com started returning HTTP 403
  responses to automated requests from GitHub Actions.
- Added timezone-data support for the `CET` timezone on GitHub Actions runners.

### Removed

- Dependence on Releases.com HTML layout and `robots.txt` lookups.

### Notes

- Movie release dates default to the US region; TV schedules combine the
  configured broadcast country with international web premieres. Coverage is
  therefore not identical to the original Releases.com feed.
- A `digital` release does not identify or guarantee a particular streaming
  service. A `disc` release does not specify DVD versus Blu-ray.

## Before November 2026 — Original implementation

- Generated a seven-day Kodi-compatible RSS ticker from Releases.com movie
  and TV calendar pages.
- Published `docs/releases.xml` through GitHub Pages, with twice-daily GitHub
  Actions updates and optional manual runs.
- Included release dates, distribution platforms, source links, and safeguards
  against replacing a working feed after failed or empty retrievals.
