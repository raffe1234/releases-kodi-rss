#!/usr/bin/env python3
"""Build a Kodi RSS ticker from the documented TMDB and TVmaze APIs.

TMDB returns movie dates by US release type (cinema, digital, physical).
TVmaze provides US broadcast and worldwide web season premieres.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


TMDB_API = "https://api.themoviedb.org/3"
TVMAZE_API = "https://api.tvmaze.com"
TMDB_SITE = "https://www.themoviedb.org"
TVMAZE_SITE = "https://www.tvmaze.com"
USER_AGENT_TOKEN = "KodiReleaseRSS"
# TMDB release types: 2=limited theatrical, 3=theatrical,
# 4=digital, 5=physical (DVD/Blu-ray/4K disc not distinguished).
MOVIE_RELEASE_TYPES = (
    ("cinema", "3|2"),
    ("digital", "4"),
    ("disc", "5"),
)


@dataclass(frozen=True)
class Release:
    release_date: date
    kind: str
    title: str
    url: str
    platform: str | None = None
    source: str = ""


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with (project_root() / "config.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_session() -> requests.Session:
    repository = os.getenv("GITHUB_REPOSITORY", "local/releases-kodi-rss")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": f"{USER_AGENT_TOKEN}/2.0 (+https://github.com/{repository})",
            "Accept": "application/json",
        }
    )
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def get_json(
    session: requests.Session,
    url: str,
    params: dict[str, str | int],
    delay_seconds: float,
) -> dict | list:
    # Throttle calls to avoid hammering either service, even during pagination.
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    response = session.get(url, params=params, timeout=45)
    response.raise_for_status()
    return response.json()


def parse_iso_day(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def fetch_tmdb_movies(
    session: requests.Session,
    api_key: str,
    first_day: date,
    last_day: date,
    region: str,
    delay_seconds: float,
    max_pages: int,
) -> list[Release]:
    """Discover exact regional dates separately for each release type.

    TMDB's discover endpoint returns the first *matching* regional release date
    for `with_release_type`, not necessarily the movie's worldwide premiere.
    Separate requests retain cinema/digital/disc variants for the same title.
    """
    if not api_key:
        raise RuntimeError(
            "TMDB_API_KEY is missing. Add it to GitHub Settings > "
            "Secrets and variables > Actions > New repository secret."
        )
    if max_pages < 1 or max_pages > 500:
        raise ValueError("tmdb_max_pages must be between 1 and 500.")

    all_releases: list[Release] = []
    for platform, release_type in MOVIE_RELEASE_TYPES:
        params: dict[str, str | int] = {
            "api_key": api_key,
            "language": "en-US",
            "region": region,
            "release_date.gte": first_day.isoformat(),
            "release_date.lte": last_day.isoformat(),
            "with_release_type": release_type,
            "include_adult": "false",
            "sort_by": "popularity.desc",
            "page": 1,
        }
        page = 1
        while True:
            params["page"] = page
            payload = get_json(session, f"{TMDB_API}/discover/movie", dict(params), delay_seconds)
            if not isinstance(payload, dict):
                raise RuntimeError("Invalid TMDB discover response: expected an object.")
            pages = payload.get("total_pages")
            if not isinstance(pages, int) or pages < 0:
                raise RuntimeError("TMDB discover did not return valid pagination data.")
            if pages > max_pages:
                # Do not silently publish an incomplete or misleading feed.
                raise RuntimeError(
                    f"TMDB returned {pages} pages for {platform}, above the "
                    f"configured tmdb_max_pages={max_pages}. Increase that limit."
                )
            records = payload.get("results")
            if not isinstance(records, list):
                raise RuntimeError("TMDB discover results are missing or invalid.")
            print(f"TMDB {platform}: page {page}/{pages}, {len(records)} movies")
            for movie in records:
                if not isinstance(movie, dict):
                    continue
                movie_id = movie.get("id")
                title = movie.get("title") or movie.get("original_title")
                release_day = parse_iso_day(movie.get("release_date"))
                if (
                    not isinstance(movie_id, int)
                    or not isinstance(title, str)
                    or not title.strip()
                    or release_day is None
                    or not (first_day <= release_day <= last_day)
                ):
                    continue
                all_releases.append(
                    Release(
                        release_day,
                        "movie",
                        title.strip(),
                        f"{TMDB_SITE}/movie/{movie_id}",
                        platform,
                        "TMDB",
                    )
                )
            if page >= pages:
                break
            page += 1
    return deduplicate_releases(all_releases)


def parse_tvmaze_schedule(payload: object, requested_day: date) -> list[Release]:
    """Keep only first episodes of a season, not each weekly episode.

    Ordinary episodes and specials with an unknown episode number are excluded.
    TVmaze schedules include the show as `_embedded.show`.
    """
    if not isinstance(payload, list):
        raise RuntimeError("TVmaze schedule response is not an array.")
    releases: list[Release] = []
    for episode in payload:
        if not isinstance(episode, dict) or episode.get("number") != 1:
            continue
        season = episode.get("season")
        if type(season) is not int or season < 1:
            continue
        day = parse_iso_day(episode.get("airdate"))
        if day != requested_day:
            continue
        embedded = episode.get("_embedded")
        show = embedded.get("show") if isinstance(embedded, dict) else None
        if not isinstance(show, dict):
            continue
        title = show.get("name")
        if not isinstance(title, str) or not title.strip():
            continue
        show_url = show.get("url")
        if not (isinstance(show_url, str) and show_url.startswith(f"{TVMAZE_SITE}/")):
            # Only link to TVmaze, not arbitrary URLs from source data.
            show_id = show.get("id")
            if not isinstance(show_id, int):
                continue
            show_url = f"{TVMAZE_SITE}/shows/{show_id}"
        channel = show.get("webChannel") or show.get("network")
        platform = channel.get("name") if isinstance(channel, dict) else None
        if not isinstance(platform, str) or not platform.strip():
            platform = None
        releases.append(
            Release(
                day,
                "tv",
                f"{title.strip()} Season {season}",
                show_url,
                platform,
                "TVmaze",
            )
        )
    return deduplicate_releases(releases)


def fetch_tvmaze_premieres(
    session: requests.Session,
    days_to_fetch: list[date],
    country: str,
    delay_seconds: float,
) -> list[Release]:
    releases: list[Release] = []
    for day in days_to_fetch:
        # Broadcast schedule defaults to a specific country; web schedule with
        # no `country` parameter includes local and global streaming channels.
        endpoints = (
            (f"{TVMAZE_API}/schedule", {"country": country, "date": day.isoformat()}),
            (f"{TVMAZE_API}/schedule/web", {"date": day.isoformat()}),
        )
        for url, params in endpoints:
            payload = get_json(session, url, params, delay_seconds)
            found = parse_tvmaze_schedule(payload, day)
            releases.extend(found)
            print(f"TVmaze {day.isoformat()} ({url.rsplit('/', 1)[-1]}): "
                  f"{len(found)} season premieres")
    return deduplicate_releases(releases)


def deduplicate_releases(releases: Iterable[Release]) -> list[Release]:
    unique: dict[tuple[date, str, str, str], Release] = {}
    for release in releases:
        # Identical show/season may appear in US broadcast and web schedules.
        key = (
            release.release_date,
            release.kind,
            release.url,
            (release.platform or "").casefold(),
        )
        unique[key] = release
    return sorted(
        unique.values(),
        key=lambda item: (
            item.release_date,
            0 if item.kind == "movie" else 1,
            item.title.casefold(),
            (item.platform or "").casefold(),
        ),
    )


def filter_excluded_platforms(
    releases: Iterable[Release], excluded_platforms: Iterable[str]
) -> list[Release]:
    excluded = {platform.strip().casefold() for platform in excluded_platforms}
    return deduplicate_releases(
        release
        for release in releases
        if (release.platform or "").casefold() not in excluded
    )


def format_short_date(day: date, configured_format: str) -> str:
    try:
        return day.strftime(configured_format)
    except ValueError:
        return f"{day.day}/{day.month}"


def add_text_element(parent: ET.Element, tag: str, value: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = value
    return element


def release_guid(release: Release) -> str:
    return (
        f"{release.url}|{release.release_date.isoformat()}|"
        f"{release.platform or 'unspecified'}"
    )


def build_rss(releases: list[Release], config: dict, now: datetime) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    add_text_element(channel, "title", config["feed_title"])
    add_text_element(
        channel, "link",
        config.get("feed_link", "https://raffe1234.github.io/releases-kodi-rss/"),
    )
    add_text_element(channel, "description", config["feed_description"])
    add_text_element(channel, "language", config.get("language", "en-US"))
    add_text_element(channel, "lastBuildDate", format_datetime(now.astimezone(timezone.utc)))
    add_text_element(channel, "generator", "KodiReleaseRSS")
    labels = {"movie": config["movie_label"], "tv": config["tv_label"]}
    include_platform = bool(config.get("include_platform", True))
    local_zone = ZoneInfo(config["timezone"])

    for release in releases:
        item = ET.SubElement(channel, "item")
        short_date = format_short_date(release.release_date, config["date_format"])
        parts = [labels[release.kind]]
        if include_platform and release.platform:
            platform = release.platform
            if platform.casefold() in {"cinema", "digital", "disc"}:
                platform = platform.lower()
            parts.append(platform)
        parts.append(short_date)
        add_text_element(item, "title", f">> [{' · '.join(parts)}] {release.title}")
        add_text_element(item, "link", release.url)
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = release_guid(release)
        release_noon = datetime.combine(
            release.release_date, datetime_time(hour=12), tzinfo=local_zone
        )
        add_text_element(item, "pubDate", format_datetime(release_noon))
        add_text_element(item, "description", f"Source: {release.source or 'TMDB / TVmaze'}")

    minimum = max(0, int(config.get("minimum_kodi_items", 3)))
    fillers = [
        "Release calendar: updated twice a day",
        f"Release calendar: showing the next {config.get('days_ahead', 7)} days",
        "Release calendar: sources TMDB and TVmaze",
    ]
    for filler in fillers[:max(0, minimum - len(releases))]:
        item = ET.SubElement(channel, "item")
        add_text_element(item, "title", filler)
        add_text_element(item, "guid", f"kodi-release-rss:{filler}")

    ET.indent(rss, space="  ")
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True) + b"\n"


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def main() -> int:
    config = load_config()
    zone = ZoneInfo(config["timezone"])
    now = datetime.now(zone)
    days = int(config["days_ahead"])
    if days < 1 or days > 31:
        raise ValueError("days_ahead must be between 1 and 31.")
    start_offset = int(config.get("start_offset_days", 0))
    days_to_fetch = [
        now.date() + timedelta(days=start_offset + i) for i in range(days)
    ]
    first_day, last_day = days_to_fetch[0], days_to_fetch[-1]
    delay = float(config.get("request_delay_seconds", 0.5))
    if delay < 0:
        raise ValueError("request_delay_seconds must not be negative.")

    # Fail BEFORE making any external requests if the key is not configured.
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "TMDB_API_KEY is missing. Add a repository secret named "
            "TMDB_API_KEY in GitHub Settings > Secrets and variables > Actions."
        )

    session = build_session()
    movies = fetch_tmdb_movies(
        session, api_key, first_day, last_day,
        str(config.get("movie_region", "US")), delay,
        int(config.get("tmdb_max_pages", 50)),
    )
    series = fetch_tvmaze_premieres(
        session, days_to_fetch, str(config.get("tv_country", "US")), delay
    )
    releases = filter_excluded_platforms(
        [*movies, *series], config.get("excluded_platforms", [])
    )
    if not releases:
        raise RuntimeError(
            "No movie or TV premieres found. Existing docs/releases.xml is unchanged."
        )
    output_path = project_root() / config["output_file"]
    atomic_write(output_path, build_rss(releases, config, now))
    print(f"Wrote {len(releases)} releases to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
