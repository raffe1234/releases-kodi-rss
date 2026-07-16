#!/usr/bin/env python3
"""Generate a compact RSS 2.0 feed for Kodi from Releases.com calendars."""

from __future__ import annotations

import calendar
import json
import os
import re
import sys
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://www.releases.com"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
USER_AGENT_TOKEN = "KodiReleaseRSS"

BADGE_TEXTS = {
    "anticipated",
    "highly anticipated",
    "most anticipated",
    "popular",
    "very anticipated",
    "hot",
    "new",
    "image",
    "upcoming",
    "released",
    "movie",
    "movies",
    "tv series",
    "tv series season",
    "product title goes here",
}

BADGE_PREFIXES = (
    "highly anticipated ",
    "most anticipated ",
    "very anticipated ",
    "anticipated ",
    "popular ",
    "hot ",
    "new ",
)

# Releases.com calls these "versions". The list is deliberately broader than
# the current movie and TV filters so that new network/service cards can still
# be identified without changing the parser immediately.
PLATFORM_DISPLAY_NAMES = {
    name.casefold(): name
    for name in (
        "Cinema",
        "VOD",
        "Streaming",
        "Digital",
        "DVD",
        "Blu-ray",
        "4K Blu-ray",
        "4K Blu-ray (SteelBook)",
        "Netflix",
        "Amazon",
        "Amazon Prime Video",
        "Prime Video",
        "Hulu",
        "Shudder",
        "Lifetime",
        "Paramount+",
        "Disney+",
        "Disney",
        "Max",
        "HBO Max",
        "HBO",
        "PBS",
        "Peacock",
        "Apple TV+",
        "Apple TV",
        "The CW",
        "BET+",
        "Crunchyroll",
        "Crunchy Roll",
        "HIDIVE",
        "FOX",
        "FXX",
        "FX",
        "CBS",
        "NBC",
        "HGTV",
        "ABC",
        "Starz",
        "MGM+",
        "Tubi",
        "Roku",
        "AMC+",
        "Adult Swim",
        "Discovery+",
        "GSN",
        "TPB+",
        "Internet",
        "Nickelodeon",
        "Showtime",
        "BritBox",
        "Acorn TV",
        "YouTube",
        "YouTube Premium",
        "Freevee",
        "Sundance Now",
        "Hallmark+",
        "Hallmark Channel",
        "Syfy",
        "USA Network",
        "BBC",
        "BBC One",
        "BBC Two",
        "BBC iPlayer",
        "ITV",
        "ITVX",
        "Channel 4",
        "Sky",
        "Sky Atlantic",
        "NOW",
    )
}

NON_PLATFORM_TEXTS = BADGE_TEXTS | {
    "all",
    "calendar",
    "filter",
    "versions",
    "tags",
    "region",
    "user's location",
    "usa",
    "uk",
    "favorites",
    "add to favorites",
    "remove from favorites",
    "track",
    "tracking",
    "watch trailer",
    "trailer",
    "details",
    "show more",
    "+more-less",
    "+ more",
    "- less",
    "x",
}

COUNT_PATTERN = re.compile(r"^\d+(?:[.,]\d+)?[KMB]?$", re.I)
TRAILING_COUNT_PATTERN = re.compile(r"\s+\d+(?:[.,]\d+)?[KMB]?$", re.I)


@dataclass(frozen=True)
class Release:
    release_date: date
    kind: str
    title: str
    url: str
    platform: str | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config() -> dict:
    config_path = project_root() / "config.json"
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_session() -> requests.Session:
    repository = os.getenv("GITHUB_REPOSITORY", "local/releases-kodi-rss")
    user_agent = f"{USER_AGENT_TOKEN}/1.0 (+https://github.com/{repository})"

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }
    )

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def date_url(category: str, day: date) -> str:
    month = calendar.month_abbr[day.month].lower()
    return f"{BASE_URL}/calendar/{category}/{day.year}-{month}-{day.day}"


def ensure_robots_allowed(
    session: requests.Session,
    urls: Iterable[str],
    enabled: bool,
) -> None:
    if not enabled:
        print("Warning: the robots.txt check is disabled.", file=sys.stderr)
        return

    response = session.get(ROBOTS_URL, timeout=30)
    if response.status_code == 404:
        print("No robots.txt file was found; continuing.")
        return
    response.raise_for_status()

    parser = RobotFileParser()
    parser.set_url(ROBOTS_URL)
    parser.parse(response.text.splitlines())

    blocked = [url for url in urls if not parser.can_fetch(USER_AGENT_TOKEN, url)]
    if blocked:
        joined = "\n".join(f"- {url}" for url in blocked)
        raise RuntimeError(
            "Releases.com robots.txt does not allow fetching the following URLs:\n"
            f"{joined}"
        )


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    lower = value.casefold()
    for prefix in BADGE_PREFIXES:
        if lower.startswith(prefix):
            value = value[len(prefix) :].strip(" :-–—")
            break
    return value


def title_from_slug(url: str) -> str:
    slug = urlparse(url).path.removeprefix("/p/").strip("/")
    title = slug.replace("-", " ").strip()
    return " ".join(
        word.upper() if word in {"tv", "dvd", "vod"} else word.capitalize()
        for word in title.split()
    )


def is_title_candidate(text: str) -> bool:
    if not text:
        return False
    lower = text.casefold()
    if lower in BADGE_TEXTS:
        return False
    if lower.startswith("image"):
        return False
    if text.isdigit():
        return False
    if len(text) < 2 or len(text) > 180:
        return False
    return any(char.isalpha() for char in text)


def choose_title(candidates: list[str], url: str) -> str:
    cleaned = []
    for candidate in candidates:
        candidate = clean_text(candidate)
        if is_title_candidate(candidate):
            cleaned.append(candidate)

    if not cleaned:
        return title_from_slug(url)

    # Product title anchors are normally the clearest non-badge text.
    # Prefer candidates with season/year markers, then a moderate title length.
    def score(value: str) -> tuple[int, int, int]:
        marker_bonus = 2 if re.search(r"\bSeason\s+\d+\b|\(\d{4}\)", value, re.I) else 0
        word_count = len(value.split())
        reasonable_length = 1 if 1 <= word_count <= 18 else 0
        return marker_bonus, reasonable_length, len(value)

    return max(dict.fromkeys(cleaned), key=score)


def month_shift(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + offset
    return absolute // 12, absolute % 12 + 1


def resolve_heading_date(heading_text: str, reference_day: date) -> date | None:
    """Resolve headings such as '17th 17th Tomorrow' or 'Aug 1st'."""
    text = clean_text(heading_text)
    match = re.match(
        r"^(?:(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+)?(\d{1,2})(?:st|nd|rd|th)\b",
        text,
        re.I,
    )
    if not match:
        return None

    month_text, day_text = match.groups()
    day_number = int(day_text)

    if month_text:
        month_number = next(
            month
            for month in range(1, 13)
            if calendar.month_name[month].casefold().startswith(month_text.casefold())
        )
        candidates = []
        for year in (reference_day.year - 1, reference_day.year, reference_day.year + 1):
            try:
                candidates.append(date(year, month_number, day_number))
            except ValueError:
                pass
    else:
        candidates = []
        for offset in (-1, 0, 1):
            year, month = month_shift(reference_day.year, reference_day.month, offset)
            try:
                candidates.append(date(year, month, day_number))
            except ValueError:
                pass

    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs((candidate - reference_day).days))


def canonical_product_url(node: Tag) -> str | None:
    if node.name != "a":
        return None

    absolute_url = urljoin(BASE_URL, node.get("href", ""))
    parsed = urlparse(absolute_url)
    if parsed.netloc not in {"releases.com", "www.releases.com"}:
        return None
    if not parsed.path.startswith("/p/"):
        return None
    return f"{BASE_URL}{parsed.path.rstrip('/')}"


def platform_parts(value: str) -> list[str]:
    """Split and normalize one or more release channels."""
    value = clean_text(value)
    value = re.sub(r"\s*\+\d+\s*$", "", value)
    value = TRAILING_COUNT_PATTERN.sub("", value).strip()
    if not value:
        return []

    raw_parts = re.split(r"\s*/\s*|\s*\|\s*", value)
    normalized: list[str] = []
    for raw_part in raw_parts:
        part = clean_text(raw_part).strip(" /|,;")
        if not part or part.casefold() in NON_PLATFORM_TEXTS:
            continue
        canonical = PLATFORM_DISPLAY_NAMES.get(part.casefold(), part)
        if canonical.casefold() not in {item.casefold() for item in normalized}:
            normalized.append(canonical)
    return normalized


def is_plausible_platform_text(value: str) -> bool:
    value = clean_text(value)
    lower = value.casefold()
    if not value or lower in NON_PLATFORM_TEXTS:
        return False
    if COUNT_PATTERN.fullmatch(value):
        return False
    if lower.startswith("image"):
        return False
    if re.search(r"\b(today|tomorrow|yesterday|in \d+ days?|days? ago)\b", lower):
        return False
    if re.fullmatch(r"[+\-/|•]+", value):
        return False
    if len(value) > 100 or len(value.split()) > 12:
        return False
    return any(character.isalpha() for character in value)


def extract_platform_after(anchor: Tag, product_url: str) -> str | None:
    """Read the version/platform text that follows a product link.

    Releases.com places the version immediately after the title card. The DOM
    has changed over time, so this intentionally uses document order rather
    than depending on a single CSS class.
    """
    known_parts: list[str] = []
    fallback_parts: list[str] = []
    examined = 0

    for element in anchor.next_elements:
        examined += 1
        if examined > 120:
            break

        if isinstance(element, Tag):
            if element.name in {"h2", "h3", "h4"}:
                break
            other_product_url = canonical_product_url(element)
            if other_product_url is not None and other_product_url != product_url:
                break
            continue

        if not isinstance(element, NavigableString):
            continue

        # Ignore the title/badge text inside all product links, including a
        # second image/title link that points to the same product.
        product_parent = element.find_parent("a")
        if product_parent is not None and canonical_product_url(product_parent) is not None:
            continue

        text = clean_text(str(element))
        if not text:
            continue

        if COUNT_PATTERN.fullmatch(text):
            if known_parts or fallback_parts:
                break
            continue

        if not is_plausible_platform_text(text):
            continue

        parts = platform_parts(text)
        if not parts:
            continue

        all_known = all(part.casefold() in PLATFORM_DISPLAY_NAMES for part in parts)
        target = known_parts if all_known else fallback_parts
        for part in parts:
            if part.casefold() not in {existing.casefold() for existing in target}:
                target.append(part)

    selected = known_parts or fallback_parts
    return " / ".join(selected) if selected else None


def parse_release_page(html: str, reference_day: date, kind: str) -> list[Release]:
    """Parse product links, release dates and channels from a calendar page."""
    soup = BeautifulSoup(html, "html.parser")
    candidates_by_key: dict[tuple[date, str], dict[str, list[str]]] = {}
    current_day: date | None = None

    # Date-specific pages can include dates before and after the requested day.
    for node in soup.find_all(["h2", "h3", "h4", "a"]):
        if node.name in {"h2", "h3", "h4"}:
            resolved = resolve_heading_date(node.get_text(" ", strip=True), reference_day)
            if resolved is not None:
                current_day = resolved
            continue

        if current_day is None:
            continue

        canonical_url = canonical_product_url(node)
        if canonical_url is None:
            continue

        entry = candidates_by_key.setdefault(
            (current_day, canonical_url),
            {"titles": [], "platforms": []},
        )
        entry["titles"].append(node.get_text(" ", strip=True))

        platform = extract_platform_after(node, canonical_url)
        if platform and platform.casefold() not in {
            existing.casefold() for existing in entry["platforms"]
        }:
            entry["platforms"].append(platform)

    releases: list[Release] = []
    for (release_day, url), entry in candidates_by_key.items():
        title = choose_title(entry["titles"], url)
        if title.casefold() == "product title goes here":
            continue

        platforms: list[str | None] = entry["platforms"] or [None]
        for platform in platforms:
            releases.append(Release(release_day, kind, title, url, platform))

    return deduplicate_releases(releases)


def deduplicate_releases(releases: Iterable[Release]) -> list[Release]:
    """Deduplicate overlapping calendar pages while preserving channels."""
    grouped: dict[tuple[date, str, str], dict[str, Release]] = {}

    for release in releases:
        base_key = (release.release_date, release.kind, release.url)
        platform_key = (release.platform or "").casefold()
        grouped.setdefault(base_key, {})[platform_key] = release

    unique: list[Release] = []
    for variants in grouped.values():
        with_platform = [item for key, item in variants.items() if key]
        unique.extend(with_platform or list(variants.values()))

    return sorted(
        unique,
        key=lambda item: (
            item.release_date,
            0 if item.kind == "movie" else 1,
            item.title.casefold(),
            (item.platform or "").casefold(),
        ),
    )


def filter_excluded_platforms(
    releases: Iterable[Release],
    excluded_platforms: Iterable[str],
) -> list[Release]:
    """Remove physical formats while retaining any streaming part on a card."""
    excluded = {clean_text(value).casefold() for value in excluded_platforms}
    filtered: list[Release] = []

    for release in releases:
        if not release.platform:
            filtered.append(release)
            continue

        kept_parts = [
            part
            for part in platform_parts(release.platform)
            if part.casefold() not in excluded
        ]
        if not kept_parts:
            continue

        filtered.append(replace(release, platform=" / ".join(kept_parts)))

    return deduplicate_releases(filtered)


def fetch_releases(
    session: requests.Session,
    urls_and_meta: list[tuple[str, date, str]],
    request_delay_seconds: float,
) -> list[Release]:
    all_releases: list[Release] = []

    for index, (url, day, kind) in enumerate(urls_and_meta):
        print(f"Fetching {url}")
        response = session.get(url, timeout=45)
        response.raise_for_status()

        page_releases = parse_release_page(response.text, day, kind)
        print(f"  Found {len(page_releases)} releases.")
        all_releases.extend(page_releases)

        if request_delay_seconds > 0 and index < len(urls_and_meta) - 1:
            time.sleep(request_delay_seconds)

    return deduplicate_releases(all_releases)


def format_short_date(day: date, configured_format: str) -> str:
    try:
        return day.strftime(configured_format)
    except ValueError:
        # Windows does not support %-d/%-m. This fallback also helps local testing.
        return f"{day.day}/{day.month}"


def display_platform(platform: str) -> str:
    """Use lower case for generic release types and preserve brand casing."""
    replacements = {
        "cinema": "cinema",
        "streaming": "streaming",
        "digital": "digital",
    }
    return " / ".join(
        replacements.get(part.casefold(), part)
        for part in platform_parts(platform)
    )


def add_text_element(parent: ET.Element, tag: str, text: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = text
    return element


def release_guid(release: Release) -> str:
    """Return a stable ID that distinguishes cinema and later streaming dates."""
    platform = release.platform or "unspecified"
    return f"{release.url}|{release.release_date.isoformat()}|{platform}"


def build_rss(releases: list[Release], config: dict, now: datetime) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    add_text_element(channel, "title", config["feed_title"])
    add_text_element(channel, "link", f"{BASE_URL}/calendar/movies")
    add_text_element(channel, "description", config["feed_description"])
    add_text_element(channel, "language", config.get("language", "en-US"))
    add_text_element(channel, "lastBuildDate", format_datetime(now.astimezone(timezone.utc)))
    add_text_element(channel, "generator", "KodiReleaseRSS")

    labels = {
        "movie": config["movie_label"],
        "tv": config["tv_label"],
    }
    include_platform = bool(config.get("include_platform", True))
    local_zone = ZoneInfo(config["timezone"])

    for release in releases:
        item = ET.SubElement(channel, "item")
        short_date = format_short_date(release.release_date, config["date_format"])
        item_label = labels[release.kind]
        if include_platform and release.platform:
            item_label = f"{item_label} ({display_platform(release.platform)})"
        ticker_title = f"{item_label}: {short_date} – {release.title}"

        add_text_element(item, "title", ticker_title)
        add_text_element(item, "link", release.url)
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = release_guid(release)

        release_noon = datetime.combine(
            release.release_date,
            datetime_time(hour=12),
            tzinfo=local_zone,
        )
        add_text_element(item, "pubDate", format_datetime(release_noon))
        add_text_element(item, "description", "Source: Releases.com")

    # Kodi's older documentation says the ticker needs at least three items.
    minimum = max(0, int(config.get("minimum_kodi_items", 3)))
    filler_titles = [
        "Release calendar: updated twice a day",
        "Release calendar: showing the next seven days",
        "Release calendar: source Releases.com",
    ]
    item_count = len(releases)
    for filler in filler_titles[: max(0, minimum - item_count)]:
        item = ET.SubElement(channel, "item")
        add_text_element(item, "title", filler)
        add_text_element(item, "guid", f"kodi-release-rss:{filler}")

    ET.indent(rss, space="  ")
    xml_body = ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    return xml_body + b"\n"


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def main() -> int:
    config = load_config()
    local_zone = ZoneInfo(config["timezone"])
    now = datetime.now(local_zone)
    first_day = now.date() + timedelta(days=int(config.get("start_offset_days", 0)))
    days = int(config["days_ahead"])

    if days < 1 or days > 31:
        raise ValueError("days_ahead must be between 1 and 31.")

    days_to_fetch = [first_day + timedelta(days=offset) for offset in range(days)]
    urls_and_meta: list[tuple[str, date, str]] = []
    for day in days_to_fetch:
        urls_and_meta.append((date_url("movies", day), day, "movie"))
        urls_and_meta.append((date_url("tv-series", day), day, "tv"))

    session = build_session()
    ensure_robots_allowed(
        session,
        (entry[0] for entry in urls_and_meta),
        bool(config.get("check_robots_txt", True)),
    )

    releases = fetch_releases(
        session,
        urls_and_meta,
        float(config.get("request_delay_seconds", 0.5)),
    )

    last_day_exclusive = first_day + timedelta(days=days)
    releases = [
        release
        for release in releases
        if first_day <= release.release_date < last_day_exclusive
    ]

    if not releases:
        raise RuntimeError(
            "No titles were found. The existing RSS file is left unchanged, "
            "because the site HTML structure may have changed."
        )

    platform_count = sum(release.platform is not None for release in releases)
    if platform_count == 0:
        print(
            "Warning: no release channels were detected; using the old title format.",
            file=sys.stderr,
        )
    else:
        print(
            f"Detected release channels for {platform_count}/{len(releases)} releases."
        )

    releases = filter_excluded_platforms(
        releases,
        config.get("excluded_platforms", []),
    )

    output_path = project_root() / config["output_file"]
    content = build_rss(releases, config, now)
    atomic_write(output_path, content)

    print(f"Wrote {len(releases)} releases to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
